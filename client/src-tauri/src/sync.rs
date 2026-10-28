//! Offline-first sync for a learner: push the outbox, then pull what changed.

use std::collections::HashSet;

use serde_json::{json, Map, Value};

use crate::error::{AppError, AppResult};
use crate::state::AppState;
use crate::store::{self, now};

const BATCH: i64 = 100;
const MAX_BATCHES: usize = 10;
const MAX_ATTEMPTS: i64 = 8;

/// Content kinds in the local store, and the parent each is listed under.
const CONTENT: &[(&str, &str, &str)] = &[
    // (pull key, local kind, parent field)
    ("strands", "strand", "course"),
    ("sub_strands", "sub_strand", "strand"),
    ("outcomes", "outcome", "sub_strand"),
    ("lessons", "lesson", "course"),
    ("quizzes", "quiz", ""),
    ("questions", "question", ""),
];

fn kind_for_doctype(doctype: &str) -> Option<&'static str> {
    Some(match doctype {
        "Lesson" => "lesson",
        "Strand" => "strand",
        "Sub-strand" => "sub_strand",
        "Learning Outcome" => "outcome",
        "Quiz" => "quiz",
        "Question" => "question",
        _ => return None,
    })
}

pub async fn sync_now(state: &AppState) -> AppResult<Value> {
    let _guard = state.sync_lock.lock().await;
    let session = state.active()?;
    let scope = session
        .scope()
        .ok_or_else(|| AppError::Invalid("Only learner profiles sync lessons.".into()))?
        .to_string();
    let token = session.token.clone();
    let server = state.server()?;

    let (pushed, rejected) = push(state, &server, &token, &scope).await?;
    let pulled = pull(state, &server, &token, &scope).await?;

    state.store.kv_set(&format!("last_sync:{scope}"), &now())?;
    Ok(json!({
        "pushed": pushed,
        "rejected": rejected,
        "full": pulled.0,
        "changes": pulled.1,
        "pending": state.store.outbox_count(&scope)?,
        "last_sync": now(),
    }))
}

async fn push(state: &AppState, server: &str, token: &str, scope: &str) -> AppResult<(usize, usize)> {
    let (mut pushed, mut rejected) = (0usize, 0usize);
    for _ in 0..MAX_BATCHES {
        let rows = state.store.outbox_pending(scope, BATCH)?;
        if rows.is_empty() {
            break;
        }
        let mut events = Vec::with_capacity(rows.len());
        for row in &rows {
            let mut payload = row.payload.clone();
            if row.kind == "assignment_submission" {
                match upload_attachment(state, server, token, &row.uuid, &mut payload).await {
                    Ok(()) => {}
                    Err(e @ AppError::Server { .. }) => {
                        state.store.outbox_reject(&row.uuid, &e.to_string())?;
                        mark_rejected(state, scope, &row.kind, &row.uuid, &row.payload, &e.to_string())?;
                        rejected += 1;
                        continue;
                    }
                    Err(e) => return Err(e),
                }
            }
            events.push(json!({"uuid": row.uuid, "type": row.kind, "at": row.at, "payload": payload}));
        }
        if events.is_empty() {
            continue;
        }

        let resp = state
            .api
            .call(server, "POST", "sync.push", &json!({"events": events}), Some(token))
            .await?;
        let results = resp.get("results").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        for result in results {
            let uuid = result.get("uuid").and_then(|v| v.as_str()).unwrap_or_default();
            let Some(row) = rows.iter().find(|r| r.uuid == uuid) else { continue };
            if result.get("ok").and_then(|v| v.as_i64()) == Some(1) {
                apply_result(state, scope, &row.kind, uuid, result.get("result").unwrap_or(&Value::Null))?;
                state.store.outbox_done(uuid)?;
                pushed += 1;
            } else {
                let code = result.get("error").and_then(|v| v.as_str()).unwrap_or("rejected");
                let message = result.get("message").and_then(|v| v.as_str()).unwrap_or(code);
                let retry = result.get("retry").and_then(|v| v.as_i64()) == Some(1);
                if retry && row.attempts + 1 < MAX_ATTEMPTS {
                    state.store.outbox_retry_later(uuid, message)?;
                } else {
                    state.store.outbox_reject(uuid, message)?;
                    mark_rejected(state, scope, &row.kind, uuid, &row.payload, message)?;
                    rejected += 1;
                }
            }
        }
        if (rows.len() as i64) < BATCH {
            break;
        }
    }
    Ok((pushed, rejected))
}

/// Files attached offline are uploaded first; the event then carries the file URL.
async fn upload_attachment(state: &AppState, server: &str, token: &str, uuid: &str, payload: &mut Value) -> AppResult<()> {
    let Some(data) = payload.get("attachment_data").and_then(|v| v.as_str()).map(String::from) else {
        return Ok(());
    };
    let name = payload.get("attachment_name").and_then(|v| v.as_str()).unwrap_or("work.jpg").to_string();
    let resp = state
        .api
        .call(server, "POST", "sync.upload", &json!({"filename": name, "content": data}), Some(token))
        .await?;
    let url = resp.get("file_url").and_then(|v| v.as_str()).unwrap_or_default().to_string();
    if let Value::Object(m) = payload {
        m.remove("attachment_data");
        m.insert("attachment".into(), Value::from(url));
    }
    state.store.outbox_set_payload(uuid, payload)
}

fn apply_result(state: &AppState, scope: &str, kind: &str, uuid: &str, result: &Value) -> AppResult<()> {
    match kind {
        "quiz_attempt" => {
            let mut row = state.store.mine_get(scope, "quiz_attempt", uuid)?;
            if let (Value::Object(m), Value::Object(r)) = (&mut row, result) {
                for key in ["name", "score", "status", "attempt_number", "answers"] {
                    if let Some(v) = r.get(key) {
                        m.insert(key.into(), v.clone());
                    }
                }
                m.insert("client_uuid".into(), Value::from(uuid));
            }
            state.store.mine_put(scope, "quiz_attempt", uuid, &row, false)
        }
        "assignment_submission" => {
            let assignment = state.store.with_tx(|tx| {
                Ok(tx
                    .query_row(
                        "select key from mine where scope = ?1 and kind = 'submission' and json_extract(data, '$.client_uuid') = ?2",
                        rusqlite::params![scope, uuid],
                        |r| r.get::<_, String>(0),
                    )
                    .ok())
            })?;
            if let Some(a) = assignment {
                let mut row = state.store.mine_get(scope, "submission", &a)?;
                if let Value::Object(m) = &mut row {
                    if let Some(s) = result.get("status") {
                        m.insert("status".into(), s.clone());
                    }
                    if let Some(n) = result.get("name") {
                        m.insert("name".into(), n.clone());
                    }
                }
                state.store.mine_put(scope, "submission", &a, &row, false)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn mark_rejected(state: &AppState, scope: &str, kind: &str, uuid: &str, payload: &Value, message: &str) -> AppResult<()> {
    let (mine_kind, key) = match kind {
        "quiz_attempt" => ("quiz_attempt", uuid.to_string()),
        "assignment_submission" => (
            "submission",
            payload.get("assignment").and_then(|v| v.as_str()).unwrap_or_default().to_string(),
        ),
        _ => return Ok(()),
    };
    let mut row = state.store.mine_get(scope, mine_kind, &key)?;
    if let Value::Object(m) = &mut row {
        m.insert("status".into(), Value::from("Not accepted"));
        m.insert("sync_error".into(), Value::from(message));
        state.store.mine_put(scope, mine_kind, &key, &row, true)?;
    }
    Ok(())
}

async fn pull(state: &AppState, server: &str, token: &str, scope: &str) -> AppResult<(bool, usize)> {
    let since = state.store.kv_get(&format!("cursor:{scope}"))?;
    let grade = state.store.kv_get(&format!("grade:{scope}"))?;
    let entitled = state.store.kv_get(&format!("entitled:{scope}"))?;
    let mut args = Map::new();
    if let Some(s) = &since {
        args.insert("since".into(), Value::from(s.clone()));
        if let Some(g) = &grade {
            args.insert("grade".into(), Value::from(g.clone()));
        }
        if let Some(e) = &entitled {
            args.insert("entitled".into(), Value::from(e.clone()));
        }
    }
    let data = state
        .api
        .call(server, "GET", "sync.pull", &Value::Object(args), Some(token))
        .await?;
    let pending_lessons: HashSet<String> = state
        .store
        .outbox_pending(scope, 1000)?
        .into_iter()
        .filter(|r| r.kind == "lesson_progress")
        .filter_map(|r| r.payload.get("lesson").and_then(|v| v.as_str()).map(String::from))
        .collect();
    state.store.with_tx(|tx| apply_pull(tx, scope, &data, &pending_lessons))
}

/// Write one pull response into the store. Returns (full resend?, rows changed).
pub fn apply_pull(
    tx: &rusqlite::Transaction,
    scope: &str,
    data: &Value,
    pending_lessons: &HashSet<String>,
) -> AppResult<(bool, usize)> {
    let full = data.get("full").and_then(|v| v.as_i64()) == Some(1);
    let mut changes = 0usize;
    if full {
        tx.execute("delete from content where scope = ?1", [scope])?;
        tx.execute("delete from mine where scope = ?1 and local = 0", [scope])?;
    }

    tx.execute("delete from content where scope = ?1 and kind = 'area'", [scope])?;
    for area in arr(data, "learning_areas") {
        put_content(tx, scope, "area", &area, None)?;
    }

    for (key, kind, parent_field) in CONTENT {
        for row in arr(data, key) {
            let parent = if parent_field.is_empty() { None } else { row.get(*parent_field).and_then(|v| v.as_str()) };
            put_content(tx, scope, kind, &row, parent)?;
            changes += 1;
        }
    }

    if let Some(Value::Object(deleted)) = data.get("deleted") {
        for (doctype, names) in deleted {
            let Some(kind) = kind_for_doctype(doctype) else { continue };
            for name in names.as_array().into_iter().flatten().filter_map(|v| v.as_str()) {
                tx.execute(
                    "delete from content where scope = ?1 and kind = ?2 and name = ?3",
                    rusqlite::params![scope, kind, name],
                )?;
                changes += 1;
            }
        }
    }

    let mine = data.get("mine").cloned().unwrap_or(Value::Null);
    for row in arr(&mine, "lesson_progress") {
        let lesson = str_of(&row, "lesson");
        if !pending_lessons.contains(&lesson) {
            store::mine_put(tx, scope, "lesson_progress", &lesson, &row, false)?;
        }
    }
    for row in arr(&mine, "quiz_attempts") {
        let key = row
            .get("client_uuid")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(String::from)
            .unwrap_or_else(|| str_of(&row, "name"));
        store::mine_put(tx, scope, "quiz_attempt", &key, &row, false)?;
    }
    if full {
        tx.execute("delete from mine where scope = ?1 and kind = 'assignment'", [scope])?;
    }
    for row in arr(&mine, "assignments") {
        store::mine_put(tx, scope, "assignment", &str_of(&row, "name"), &row, false)?;
    }
    for row in arr(&mine, "submissions") {
        store::mine_put(tx, scope, "submission", &str_of(&row, "assignment"), &row, false)?;
    }
    for row in arr(&mine, "competencies") {
        store::mine_put(tx, scope, "competency", &str_of(&row, "name"), &row, false)?;
    }

    let set = |key: &str, value: String| -> AppResult<()> {
        tx.execute(
            "insert into kv(key, value) values(?1, ?2) on conflict(key) do update set value = excluded.value",
            rusqlite::params![key, value],
        )?;
        Ok(())
    };
    if let Some(cursor) = data.get("cursor").and_then(|v| v.as_str()) {
        set(&format!("cursor:{scope}"), cursor.to_string())?;
    }
    let learner = data.get("learner").cloned().unwrap_or(Value::Null);
    if let Some(g) = learner.get("grade").and_then(|v| v.as_str()) {
        set(&format!("grade:{scope}"), g.to_string())?;
    }
    let ent = data.get("entitlement").cloned().unwrap_or(Value::Null);
    let active = ent.get("active").and_then(|v| v.as_i64()).unwrap_or(0);
    set(&format!("entitled:{scope}"), active.to_string())?;
    set(&format!("learner:{scope}"), learner.to_string())?;
    set(&format!("entitlement:{scope}"), ent.to_string())?;
    if let Some(q) = mine.get("ai_quota") {
        set(&format!("ai_quota:{scope}"), q.to_string())?;
    }
    Ok((full, changes))
}

fn put_content(tx: &rusqlite::Transaction, scope: &str, kind: &str, row: &Value, parent: Option<&str>) -> AppResult<()> {
    let name = str_of(row, "name");
    if name.is_empty() {
        return Ok(());
    }
    let sort = row.get("order").and_then(|v| v.as_i64()).unwrap_or(0);
    tx.execute(
        "insert into content(scope, kind, name, parent, sort, data) values(?1, ?2, ?3, ?4, ?5, ?6)
         on conflict(scope, kind, name) do update set parent = excluded.parent, sort = excluded.sort, data = excluded.data",
        rusqlite::params![scope, kind, name, parent, sort, row.to_string()],
    )?;
    Ok(())
}

fn arr(v: &Value, key: &str) -> Vec<Value> {
    v.get(key).and_then(|x| x.as_array()).cloned().unwrap_or_default()
}

fn str_of(v: &Value, key: &str) -> String {
    v.get(key).and_then(|x| x.as_str()).unwrap_or_default().to_string()
}

/// Record an offline action and show its effect straight away.
pub fn queue(state: &AppState, scope: &str, kind: &str, payload: Value) -> AppResult<Value> {
    const KINDS: &[&str] = &["lesson_progress", "quiz_attempt", "assignment_submission", "practice_answers", "ai_feedback"];
    if !KINDS.contains(&kind) {
        return Err(AppError::Invalid(format!("Unknown event {kind}.")));
    }
    if let Some(data) = payload.get("attachment_data").and_then(|v| v.as_str()) {
        if data.len() > 11 * 1024 * 1024 {
            return Err(AppError::Invalid("Files can be up to 8 MB.".into()));
        }
    }
    let uuid = state.store.outbox_add(scope, kind, &payload)?;
    let store = &state.store;
    match kind {
        "lesson_progress" => {
            let lesson = str_of(&payload, "lesson");
            let mut row = store.mine_get(scope, "lesson_progress", &lesson)?;
            if !row.is_object() {
                row = json!({"lesson": lesson, "status": "Started", "progress": 0, "time_spent": 0});
            }
            let progress = payload.get("progress").and_then(|v| v.as_f64()).unwrap_or(0.0);
            let completed = payload.get("completed").and_then(|v| v.as_i64()) == Some(1) || progress >= 100.0;
            let delta = payload.get("time_spent_delta").and_then(|v| v.as_i64()).unwrap_or(0).max(0);
            if let Value::Object(m) = &mut row {
                let old = m.get("progress").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let new = if completed { 100.0 } else { old.max(progress) };
                m.insert("progress".into(), Value::from(new));
                let spent = m.get("time_spent").and_then(|v| v.as_i64()).unwrap_or(0) + delta;
                m.insert("time_spent".into(), Value::from(spent));
                m.insert("last_opened".into(), Value::from(now()));
                if completed {
                    m.insert("status".into(), Value::from("Completed"));
                    m.entry("completed_on").or_insert(Value::from(now()));
                }
            }
            store.mine_put(scope, "lesson_progress", &lesson, &row, true)?;
        }
        "quiz_attempt" => {
            let row = json!({
                "client_uuid": uuid,
                "quiz": payload.get("quiz"),
                "lesson": payload.get("lesson"),
                "score": payload.get("score"),
                "status": "Waiting to send",
                "time_completed": now(),
            });
            store.mine_put(scope, "quiz_attempt", &uuid, &row, true)?;
        }
        "assignment_submission" => {
            let assignment = str_of(&payload, "assignment");
            let row = json!({
                "assignment": assignment,
                "client_uuid": uuid,
                "status": "Waiting to send",
                "answer_text": payload.get("answer_text"),
                "attachment_name": payload.get("attachment_name"),
                "submission_date": now(),
            });
            store.mine_put(scope, "submission", &assignment, &row, true)?;
        }
        _ => {}
    }
    Ok(json!({"uuid": uuid, "pending": store.outbox_count(scope)?}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::Store;

    fn sample(full: i64) -> Value {
        json!({
            "cursor": "2026-10-28 10:00:00",
            "full": full,
            "learner": {"student": "S1", "grade": "Grade 4"},
            "entitlement": {"active": 1, "status": "Trial"},
            "learning_areas": [{"name": "Grade 4 Mathematics", "title": "Mathematics", "order": 1}],
            "strands": [{"name": "Numbers-0001", "course": "Grade 4 Mathematics", "order": 1, "active": 1}],
            "sub_strands": [{"name": "SS1", "strand": "Numbers-0001", "order": 1, "active": 1}],
            "outcomes": [],
            "lessons": [{"name": "L1", "course": "Grade 4 Mathematics", "order": 2}, {"name": "L2", "course": "Grade 4 Mathematics", "order": 1}],
            "quizzes": [], "questions": [],
            "deleted": {},
            "mine": {"lesson_progress": [{"lesson": "L1", "progress": 100, "status": "Completed"}], "ai_quota": {"limit": 20}}
        })
    }

    #[test]
    fn full_then_incremental_pull() {
        let s = Store::memory();
        s.with_tx(|tx| apply_pull(tx, "S1", &sample(1), &HashSet::new())).unwrap();
        let lessons = s.content_list("S1", "lesson", Some("Grade 4 Mathematics")).unwrap();
        assert_eq!(lessons.iter().map(|l| l["name"].as_str().unwrap()).collect::<Vec<_>>(), vec!["L2", "L1"]);
        assert_eq!(s.kv_get("grade:S1").unwrap().as_deref(), Some("Grade 4"));

        let mut inc = sample(0);
        inc["lessons"] = json!([]);
        inc["deleted"] = json!({"Lesson": ["L2"]});
        s.with_tx(|tx| apply_pull(tx, "S1", &inc, &HashSet::new())).unwrap();
        assert_eq!(s.content_count("S1", "lesson").unwrap(), 1);
    }

    #[test]
    fn pending_progress_is_not_overwritten() {
        let s = Store::memory();
        s.mine_put("S1", "lesson_progress", "L1", &json!({"lesson": "L1", "progress": 40}), true).unwrap();
        let pending: HashSet<String> = ["L1".to_string()].into();
        let mut data = sample(0);
        data["mine"]["lesson_progress"] = json!([{"lesson": "L1", "progress": 10}]);
        s.with_tx(|tx| apply_pull(tx, "S1", &data, &pending)).unwrap();
        assert_eq!(s.mine_get("S1", "lesson_progress", "L1").unwrap()["progress"], 40);
    }
}
