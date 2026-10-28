//! The on-device SQLite store.
//!
//! Content (lessons, quizzes …) and a learner's own records are kept per learner
//! ("scope" = Student id), so siblings sharing a tablet each keep their own copy.
//! The outbox holds events made offline until the server has accepted them.

use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection, OptionalExtension, Transaction};
use serde_json::Value;

use crate::error::AppResult;

const SCHEMA_VERSION: i64 = 1;

pub struct Store {
    conn: Mutex<Connection>,
}

pub fn now() -> String {
    chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
}

impl Store {
    pub fn open(path: &Path) -> AppResult<Self> {
        let conn = Connection::open(path)?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.busy_timeout(std::time::Duration::from_secs(5))?;
        migrate(&conn)?;
        Ok(Store { conn: Mutex::new(conn) })
    }

    #[cfg(test)]
    pub fn memory() -> Self {
        let conn = Connection::open_in_memory().unwrap();
        migrate(&conn).unwrap();
        Store { conn: Mutex::new(conn) }
    }

    pub fn with_tx<T>(&self, f: impl FnOnce(&Transaction) -> AppResult<T>) -> AppResult<T> {
        let mut conn = self.conn.lock().expect("store lock");
        let tx = conn.transaction()?;
        let out = f(&tx)?;
        tx.commit()?;
        Ok(out)
    }

    fn with<T>(&self, f: impl FnOnce(&Connection) -> AppResult<T>) -> AppResult<T> {
        let conn = self.conn.lock().expect("store lock");
        f(&conn)
    }

    // ---- key/value -------------------------------------------------------

    pub fn kv_get(&self, key: &str) -> AppResult<Option<String>> {
        self.with(|c| {
            Ok(c.query_row("select value from kv where key = ?1", [key], |r| r.get(0))
                .optional()?)
        })
    }

    pub fn kv_set(&self, key: &str, value: &str) -> AppResult<()> {
        self.with(|c| {
            c.execute(
                "insert into kv(key, value) values(?1, ?2) on conflict(key) do update set value = excluded.value",
                params![key, value],
            )?;
            Ok(())
        })
    }

    pub fn kv_del(&self, key: &str) -> AppResult<()> {
        self.with(|c| {
            c.execute("delete from kv where key = ?1", [key])?;
            Ok(())
        })
    }

    pub fn kv_json(&self, key: &str) -> AppResult<Value> {
        Ok(self
            .kv_get(key)?
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or(Value::Null))
    }

    // ---- content ---------------------------------------------------------

    pub fn content_list(&self, scope: &str, kind: &str, parent: Option<&str>) -> AppResult<Vec<Value>> {
        self.with(|c| {
            let mut rows = Vec::new();
            let mut push = |data: String| {
                if let Ok(v) = serde_json::from_str(&data) {
                    rows.push(v);
                }
            };
            match parent {
                Some(p) => {
                    let mut st = c.prepare(
                        "select data from content where scope = ?1 and kind = ?2 and parent = ?3 order by sort, name",
                    )?;
                    for r in st.query_map(params![scope, kind, p], |r| r.get::<_, String>(0))? {
                        push(r?);
                    }
                }
                None => {
                    let mut st = c.prepare(
                        "select data from content where scope = ?1 and kind = ?2 order by sort, name",
                    )?;
                    for r in st.query_map(params![scope, kind], |r| r.get::<_, String>(0))? {
                        push(r?);
                    }
                }
            }
            Ok(rows)
        })
    }

    pub fn content_get(&self, scope: &str, kind: &str, name: &str) -> AppResult<Value> {
        self.with(|c| {
            let data: Option<String> = c
                .query_row(
                    "select data from content where scope = ?1 and kind = ?2 and name = ?3",
                    params![scope, kind, name],
                    |r| r.get(0),
                )
                .optional()?;
            Ok(data.and_then(|d| serde_json::from_str(&d).ok()).unwrap_or(Value::Null))
        })
    }

    pub fn content_count(&self, scope: &str, kind: &str) -> AppResult<i64> {
        self.with(|c| {
            Ok(c.query_row(
                "select count(*) from content where scope = ?1 and kind = ?2",
                params![scope, kind],
                |r| r.get(0),
            )?)
        })
    }

    // ---- the learner's own records ----------------------------------------

    pub fn mine_list(&self, scope: &str, kind: &str) -> AppResult<Vec<Value>> {
        self.with(|c| {
            let mut st = c.prepare(
                "select data, local from mine where scope = ?1 and kind = ?2 order by updated desc",
            )?;
            let mut rows = Vec::new();
            for r in st.query_map(params![scope, kind], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)))? {
                let (data, local) = r?;
                if let Ok(mut v) = serde_json::from_str::<Value>(&data) {
                    if let Value::Object(m) = &mut v {
                        m.insert("_local".into(), Value::from(local));
                    }
                    rows.push(v);
                }
            }
            Ok(rows)
        })
    }

    pub fn mine_put(&self, scope: &str, kind: &str, key: &str, data: &Value, local: bool) -> AppResult<()> {
        self.with(|c| mine_put(c, scope, kind, key, data, local))
    }

    pub fn mine_get(&self, scope: &str, kind: &str, key: &str) -> AppResult<Value> {
        self.with(|c| {
            let data: Option<String> = c
                .query_row(
                    "select data from mine where scope = ?1 and kind = ?2 and key = ?3",
                    params![scope, kind, key],
                    |r| r.get(0),
                )
                .optional()?;
            Ok(data.and_then(|d| serde_json::from_str(&d).ok()).unwrap_or(Value::Null))
        })
    }

    // ---- outbox ----------------------------------------------------------

    pub fn outbox_add(&self, scope: &str, kind: &str, payload: &Value) -> AppResult<String> {
        let id = uuid::Uuid::new_v4().to_string();
        self.with(|c| {
            c.execute(
                "insert into outbox(uuid, scope, type, payload, at, created) values(?1, ?2, ?3, ?4, ?5, ?5)",
                params![id, scope, kind, payload.to_string(), now()],
            )?;
            Ok(())
        })?;
        Ok(id)
    }

    /// Events waiting to go, oldest first. Rejected ones stay for the learner to see.
    pub fn outbox_pending(&self, scope: &str, limit: i64) -> AppResult<Vec<OutboxRow>> {
        self.with(|c| {
            let mut st = c.prepare(
                "select uuid, type, payload, at, attempts from outbox
                 where scope = ?1 and state = 'pending' order by created, rowid limit ?2",
            )?;
            let rows = st
                .query_map(params![scope, limit], |r| {
                    Ok(OutboxRow {
                        uuid: r.get(0)?,
                        kind: r.get(1)?,
                        payload: serde_json::from_str(&r.get::<_, String>(2)?).unwrap_or(Value::Null),
                        at: r.get(3)?,
                        attempts: r.get(4)?,
                    })
                })?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
    }

    pub fn outbox_list(&self, scope: &str) -> AppResult<Vec<Value>> {
        self.with(|c| {
            let mut st = c.prepare(
                "select uuid, type, payload, at, attempts, state, error from outbox where scope = ?1 order by created desc",
            )?;
            let rows = st
                .query_map([scope], |r| {
                    let mut payload: Value = serde_json::from_str(&r.get::<_, String>(2)?).unwrap_or(Value::Null);
                    if let Value::Object(m) = &mut payload {
                        m.remove("attachment_data");
                    }
                    Ok(serde_json::json!({
                        "uuid": r.get::<_, String>(0)?,
                        "type": r.get::<_, String>(1)?,
                        "payload": payload,
                        "at": r.get::<_, String>(3)?,
                        "attempts": r.get::<_, i64>(4)?,
                        "state": r.get::<_, String>(5)?,
                        "error": r.get::<_, Option<String>>(6)?,
                    }))
                })?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
    }

    pub fn outbox_count(&self, scope: &str) -> AppResult<i64> {
        self.with(|c| {
            Ok(c.query_row(
                "select count(*) from outbox where scope = ?1 and state = 'pending'",
                [scope],
                |r| r.get(0),
            )?)
        })
    }

    pub fn outbox_set_payload(&self, uuid: &str, payload: &Value) -> AppResult<()> {
        self.with(|c| {
            c.execute("update outbox set payload = ?2 where uuid = ?1", params![uuid, payload.to_string()])?;
            Ok(())
        })
    }

    pub fn outbox_done(&self, uuid: &str) -> AppResult<()> {
        self.with(|c| {
            c.execute("delete from outbox where uuid = ?1", [uuid])?;
            Ok(())
        })
    }

    pub fn outbox_retry_later(&self, uuid: &str, error: &str) -> AppResult<()> {
        self.with(|c| {
            c.execute(
                "update outbox set attempts = attempts + 1, error = ?2 where uuid = ?1",
                params![uuid, error],
            )?;
            Ok(())
        })
    }

    pub fn outbox_reject(&self, uuid: &str, error: &str) -> AppResult<()> {
        self.with(|c| {
            c.execute(
                "update outbox set state = 'rejected', attempts = attempts + 1, error = ?2 where uuid = ?1",
                params![uuid, error],
            )?;
            Ok(())
        })
    }

    // ---- cached online screens --------------------------------------------

    pub fn cache_put(&self, key: &str, data: &Value) -> AppResult<()> {
        self.with(|c| {
            c.execute(
                "insert into cache(key, data, saved) values(?1, ?2, ?3)
                 on conflict(key) do update set data = excluded.data, saved = excluded.saved",
                params![key, data.to_string(), now()],
            )?;
            Ok(())
        })
    }

    pub fn cache_get(&self, key: &str) -> AppResult<Value> {
        self.with(|c| {
            let row: Option<(String, String)> = c
                .query_row("select data, saved from cache where key = ?1", [key], |r| Ok((r.get(0)?, r.get(1)?)))
                .optional()?;
            Ok(match row {
                Some((data, saved)) => serde_json::json!({
                    "data": serde_json::from_str::<Value>(&data).unwrap_or(Value::Null),
                    "saved": saved,
                }),
                None => Value::Null,
            })
        })
    }

    /// Everything on the device, for "remove my data from this device".
    pub fn wipe(&self) -> AppResult<()> {
        self.with(|c| {
            c.execute_batch(
                "delete from content; delete from mine; delete from outbox; delete from cache; delete from kv;",
            )?;
            Ok(())
        })
    }
}

pub struct OutboxRow {
    pub uuid: String,
    pub kind: String,
    pub payload: Value,
    pub at: String,
    pub attempts: i64,
}

pub fn mine_put(c: &Connection, scope: &str, kind: &str, key: &str, data: &Value, local: bool) -> AppResult<()> {
    c.execute(
        "insert into mine(scope, kind, key, data, local, updated) values(?1, ?2, ?3, ?4, ?5, ?6)
         on conflict(scope, kind, key) do update set data = excluded.data, local = excluded.local, updated = excluded.updated",
        params![scope, kind, key, data.to_string(), local as i64, now()],
    )?;
    Ok(())
}

fn migrate(c: &Connection) -> AppResult<()> {
    let version: i64 = c.query_row("pragma user_version", [], |r| r.get(0))?;
    if version < 1 {
        c.execute_batch(
            "
            create table if not exists kv (key text primary key, value text not null);
            create table if not exists content (
                scope text not null, kind text not null, name text not null,
                parent text, sort integer not null default 0, data text not null,
                primary key (scope, kind, name)
            );
            create index if not exists content_parent on content(scope, kind, parent);
            create table if not exists mine (
                scope text not null, kind text not null, key text not null,
                data text not null, local integer not null default 0, updated text not null,
                primary key (scope, kind, key)
            );
            create table if not exists outbox (
                uuid text primary key, scope text not null, type text not null,
                payload text not null, at text not null, attempts integer not null default 0,
                state text not null default 'pending', error text, created text not null
            );
            create index if not exists outbox_scope on outbox(scope, state, created);
            create table if not exists cache (key text primary key, data text not null, saved text not null);
            ",
        )?;
    }
    c.pragma_update(None, "user_version", SCHEMA_VERSION)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn outbox_round_trip() {
        let s = Store::memory();
        let id = s.outbox_add("S1", "lesson_progress", &json!({"lesson": "L1"})).unwrap();
        assert_eq!(s.outbox_count("S1").unwrap(), 1);
        assert_eq!(s.outbox_count("S2").unwrap(), 0);
        s.outbox_retry_later(&id, "offline").unwrap();
        assert_eq!(s.outbox_pending("S1", 10).unwrap()[0].attempts, 1);
        s.outbox_reject(&id, "max_attempts").unwrap();
        assert_eq!(s.outbox_count("S1").unwrap(), 0);
        assert_eq!(s.outbox_list("S1").unwrap()[0]["state"], "rejected");
    }

    #[test]
    fn mine_is_per_learner() {
        let s = Store::memory();
        s.mine_put("S1", "lesson_progress", "L1", &json!({"lesson": "L1", "progress": 50}), true).unwrap();
        assert_eq!(s.mine_list("S1", "lesson_progress").unwrap()[0]["_local"], 1);
        assert!(s.mine_list("S2", "lesson_progress").unwrap().is_empty());
    }
}
