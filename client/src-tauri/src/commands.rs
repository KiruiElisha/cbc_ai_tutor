//! Commands the Svelte UI calls with `invoke`.

use serde_json::{json, Map, Value};
use tauri::State;

use crate::error::{AppError, AppResult};
use crate::session::{self, Session};
use crate::state::AppState;
use crate::sync;

/// Endpoints that hand out device tokens. Only the dedicated commands below call
/// them, so tokens stay in Rust.
const TOKEN_ENDPOINTS: &[&str] = &[
    "auth.login",
    "auth.learner_login",
    "auth.signup_parent",
    "auth.open_learner",
    "signin.confirm_email_code",
    "signin.exchange",
];

fn merge(mut args: Value, extra: Value) -> Value {
    if let (Value::Object(a), Value::Object(b)) = (&mut args, extra) {
        for (k, v) in b {
            a.insert(k, v);
        }
    }
    args
}

fn public(session: &Option<Session>) -> Value {
    session.as_ref().map(|s| serde_json::to_value(s).unwrap_or(Value::Null)).unwrap_or(Value::Null)
}

#[tauri::command]
pub fn app_state(state: State<'_, AppState>) -> AppResult<Value> {
    let session = state.session.lock().expect("session lock").clone();
    let scope = session.as_ref().and_then(|s| s.scope().map(String::from));
    let (pending, last_sync) = match &scope {
        Some(sc) => (state.store.outbox_count(sc)?, state.store.kv_get(&format!("last_sync:{sc}"))?),
        None => (0, None),
    };
    Ok(json!({
        "server": state.server()?,
        "session": public(&session),
        "parent_waiting": session::load(&state.store, session::PARENT)?.is_some(),
        "pending": pending,
        "last_sync": last_sync,
        "version": state.version,
        "platform": state.platform,
    }))
}

async fn sign_in(state: &AppState, path: &str, args: Value) -> AppResult<Value> {
    let server = state.server()?;
    let resp = state.api.call(&server, "POST", path, &merge(args, state.device_args()), None).await?;
    let session = Session::from_login(&resp)?;
    session::clear(&state.store, session::PARENT)?;
    state.set_active(Some(session.clone()))?;
    Ok(public(&Some(session)))
}

#[tauri::command]
pub async fn login(state: State<'_, AppState>, login: String, password: String, role: Option<String>) -> AppResult<Value> {
    sign_in(&state, "auth.login", json!({"login": login, "password": password, "role": role})).await
}

#[tauri::command]
pub async fn learner_login(state: State<'_, AppState>, code: String, pin: String) -> AppResult<Value> {
    sign_in(&state, "auth.learner_login", json!({"code": code, "pin": pin})).await
}

fn signed_in_or_pending(state: &AppState, resp: &Value) -> AppResult<Value> {
    if resp.get("needs_profile").and_then(|v| v.as_bool()).unwrap_or(false) {
        return Ok(resp.clone());
    }
    let session = Session::from_login(resp)?;
    session::clear(&state.store, session::PARENT)?;
    state.set_active(Some(session.clone()))?;
    Ok(public(&Some(session)))
}

/// Email a 6-digit code. No session yet.
#[tauri::command]
pub async fn request_email_code(state: State<'_, AppState>, email: String, role: String) -> AppResult<Value> {
    let server = state.server()?;
    state
        .api
        .call(&server, "POST", "signin.request_email_code", &json!({"email": email, "role": role}), None)
        .await
}

/// Check the code. A new parent comes back with `needs_profile` until name and phone are sent.
#[tauri::command]
pub async fn confirm_email_code(
    state: State<'_, AppState>,
    email: String,
    code: String,
    role: String,
    full_name: Option<String>,
    phone: Option<String>,
) -> AppResult<Value> {
    let server = state.server()?;
    let mut args = json!({"email": email, "code": code, "role": role});
    if let Some(name) = full_name.filter(|s| !s.trim().is_empty()) {
        args["full_name"] = json!(name);
    }
    if let Some(number) = phone.filter(|s| !s.trim().is_empty()) {
        args["phone"] = json!(number);
    }
    let resp = state
        .api
        .call(&server, "POST", "signin.confirm_email_code", &merge(args, state.device_args()), None)
        .await?;
    signed_in_or_pending(&state, &resp)
}

/// The Google page to open in the browser. The app finishes when it receives cbctutor://auth?code=
#[tauri::command]
pub async fn google_signin_url(state: State<'_, AppState>, role: String) -> AppResult<Value> {
    let server = state.server()?;
    state
        .api
        .call(
            &server,
            "GET",
            "signin.google_url",
            &merge(json!({"role": role}), state.device_args()),
            None,
        )
        .await
}

/// Turn the one-time code from the browser into a device session.
#[tauri::command]
pub async fn finish_signin(state: State<'_, AppState>, code: String) -> AppResult<Value> {
    let server = state.server()?;
    let resp = state.api.call(&server, "POST", "signin.exchange", &json!({"code": code}), None).await?;
    signed_in_or_pending(&state, &resp)
}

#[tauri::command]
pub async fn signup_parent(
    state: State<'_, AppState>,
    full_name: String,
    email: String,
    phone: String,
    password: String,
) -> AppResult<Value> {
    sign_in(
        &state,
        "auth.signup_parent",
        json!({"full_name": full_name, "email": email, "phone": phone, "password": password}),
    )
    .await
}

/// A parent hands the device to a child. The parent's session waits in the background.
#[tauri::command]
pub async fn open_learner(state: State<'_, AppState>, student: String) -> AppResult<Value> {
    let parent = state.active()?;
    if parent.role != "Parent" {
        return Err(AppError::Invalid("Only a parent can open a learner profile.".into()));
    }
    let server = state.server()?;
    let args = merge(json!({"student": student}), state.device_args());
    let resp = state.api.call(&server, "POST", "auth.open_learner", &args, Some(&parent.token)).await?;
    let learner = Session::from_login(&resp)?;
    session::save(&state.store, session::PARENT, &parent)?;
    state.set_active(Some(learner.clone()))?;
    Ok(public(&Some(learner)))
}

#[tauri::command]
pub async fn back_to_parent(state: State<'_, AppState>) -> AppResult<Value> {
    let parent = session::load(&state.store, session::PARENT)?
        .ok_or_else(|| AppError::SignedOut("Sign in as the parent again.".into()))?;
    if let (Ok(current), Ok(server)) = (state.active(), state.server()) {
        let _ = state.api.call(&server, "POST", "auth.logout", &json!({}), Some(&current.token)).await;
    }
    session::clear(&state.store, session::PARENT)?;
    state.set_active(Some(parent.clone()))?;
    Ok(public(&Some(parent)))
}

#[tauri::command]
pub async fn logout(state: State<'_, AppState>) -> AppResult<()> {
    if let (Ok(current), Ok(server)) = (state.active(), state.server()) {
        let _ = state.api.call(&server, "POST", "auth.logout", &json!({}), Some(&current.token)).await;
    }
    if let Some(parent) = session::load(&state.store, session::PARENT)? {
        if let Ok(server) = state.server() {
            let _ = state.api.call(&server, "POST", "auth.logout", &json!({}), Some(&parent.token)).await;
        }
        session::clear(&state.store, session::PARENT)?;
    }
    state.set_active(None)
}

/// Any other API call, made with the signed-in device's token. With `cache_key`,
/// the answer is kept so the screen still shows something when offline.
#[tauri::command]
pub async fn api(
    state: State<'_, AppState>,
    method: String,
    path: String,
    args: Option<Value>,
    cache_key: Option<String>,
    guest: Option<bool>,
) -> AppResult<Value> {
    if TOKEN_ENDPOINTS.contains(&path.as_str()) {
        return Err(AppError::Invalid("Use the sign-in screen for that.".into()));
    }
    let server = state.server()?;
    let token = if guest.unwrap_or(false) { None } else { Some(state.active()?.token) };
    let args = args.unwrap_or_else(|| Value::Object(Map::new()));
    let key = cache_key.map(|k| {
        let user = state.active().map(|s| format!("{}:{}", s.user, s.student.unwrap_or_default())).unwrap_or_default();
        format!("{user}:{k}")
    });

    match state.api.call(&server, &method, &path, &args, token.as_deref()).await {
        Ok(data) => {
            if let Some(k) = &key {
                state.store.cache_put(k, &data)?;
            }
            Ok(json!({"data": data, "cached": false}))
        }
        Err(AppError::Offline(msg)) => match &key {
            Some(k) => {
                let cached = state.store.cache_get(k)?;
                if cached.is_null() {
                    Err(AppError::Offline(msg))
                } else {
                    Ok(json!({"data": cached["data"], "cached": true, "saved": cached["saved"]}))
                }
            }
            None => Err(AppError::Offline(msg)),
        },
        Err(AppError::SignedOut(msg)) => {
            state.set_active(None)?;
            Err(AppError::SignedOut(msg))
        }
        Err(e) => Err(e),
    }
}

fn learner_scope(state: &AppState) -> AppResult<String> {
    let s = state.active()?;
    s.scope()
        .map(String::from)
        .ok_or_else(|| AppError::Invalid("Open a learner profile first.".into()))
}

#[tauri::command]
pub async fn sync_now(state: State<'_, AppState>) -> AppResult<Value> {
    match sync::sync_now(&state).await {
        Err(AppError::SignedOut(msg)) => {
            state.set_active(None)?;
            Err(AppError::SignedOut(msg))
        }
        other => other,
    }
}

#[tauri::command]
pub fn learner_status(state: State<'_, AppState>) -> AppResult<Value> {
    let scope = learner_scope(&state)?;
    let st = &state.store;
    Ok(json!({
        "learner": st.kv_json(&format!("learner:{scope}"))?,
        "entitlement": st.kv_json(&format!("entitlement:{scope}"))?,
        "ai_quota": st.kv_json(&format!("ai_quota:{scope}"))?,
        "last_sync": st.kv_get(&format!("last_sync:{scope}"))?,
        "has_content": st.content_count(&scope, "area")? > 0,
        "pending": st.outbox_count(&scope)?,
    }))
}

#[tauri::command]
pub fn local_list(state: State<'_, AppState>, kind: String, parent: Option<String>) -> AppResult<Vec<Value>> {
    let scope = learner_scope(&state)?;
    state.store.content_list(&scope, &kind, parent.as_deref())
}

#[tauri::command]
pub fn local_get(state: State<'_, AppState>, kind: String, name: String) -> AppResult<Value> {
    let scope = learner_scope(&state)?;
    state.store.content_get(&scope, &kind, &name)
}

/// A quiz with its questions, ready to take offline.
#[tauri::command]
pub fn local_quiz(state: State<'_, AppState>, name: String) -> AppResult<Value> {
    let scope = learner_scope(&state)?;
    let mut quiz = state.store.content_get(&scope, "quiz", &name)?;
    if quiz.is_null() {
        return Err(AppError::Invalid("This quiz is not on the device yet. Sync first.".into()));
    }
    let names: Vec<String> = quiz["questions"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|v| v.as_str().map(String::from))
        .collect();
    let mut questions = Vec::new();
    for n in names {
        let q = state.store.content_get(&scope, "question", &n)?;
        if !q.is_null() {
            questions.push(q);
        }
    }
    quiz["question_rows"] = Value::Array(questions);
    Ok(quiz)
}

#[tauri::command]
pub fn mine_list(state: State<'_, AppState>, kind: String) -> AppResult<Vec<Value>> {
    let scope = learner_scope(&state)?;
    state.store.mine_list(&scope, &kind)
}

#[tauri::command]
pub fn queue_event(state: State<'_, AppState>, kind: String, payload: Value) -> AppResult<Value> {
    let scope = learner_scope(&state)?;
    sync::queue(&state, &scope, &kind, payload)
}

#[tauri::command]
pub fn outbox_list(state: State<'_, AppState>) -> AppResult<Vec<Value>> {
    let scope = learner_scope(&state)?;
    state.store.outbox_list(&scope)
}

#[tauri::command]
pub fn outbox_discard(state: State<'_, AppState>, uuid: String) -> AppResult<()> {
    state.store.outbox_done(&uuid)
}

/// "Remove everything from this device": signs out and deletes offline data.
#[tauri::command]
pub async fn wipe_device(state: State<'_, AppState>) -> AppResult<()> {
    let _ = logout(state.clone()).await;
    state.store.wipe()?;
    Ok(())
}
