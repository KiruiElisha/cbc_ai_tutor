use std::sync::Mutex;

use crate::api::Api;
use crate::error::{AppError, AppResult};
use crate::session::{self, Session};
use crate::store::Store;

/// The server the app talks to unless the user changes it (Settings → Server).
/// Set at build time: `CBC_SERVER_URL=https://tutor.example.co.ke npm run tauri build`.
pub const DEFAULT_SERVER: &str = match option_env!("CBC_SERVER_URL") {
    Some(url) => url,
    None => "",
};

pub struct AppState {
    pub store: Store,
    pub api: Api,
    pub session: Mutex<Option<Session>>,
    pub sync_lock: tokio::sync::Mutex<()>,
    pub device_name: String,
    pub platform: String,
    pub version: String,
}

impl AppState {
    pub fn server(&self) -> AppResult<String> {
        let url = self.store.kv_get("server")?.unwrap_or_else(|| DEFAULT_SERVER.to_string());
        if url.is_empty() {
            return Err(AppError::Invalid("Set the server address in Settings first.".into()));
        }
        Ok(url)
    }

    pub fn active(&self) -> AppResult<Session> {
        self.session
            .lock()
            .expect("session lock")
            .clone()
            .ok_or_else(|| AppError::SignedOut("Please sign in.".into()))
    }

    pub fn set_active(&self, s: Option<Session>) -> AppResult<()> {
        match &s {
            Some(s) => session::save(&self.store, session::ACTIVE, s)?,
            None => session::clear(&self.store, session::ACTIVE)?,
        }
        *self.session.lock().expect("session lock") = s;
        Ok(())
    }

    pub fn device_args(&self) -> serde_json::Value {
        serde_json::json!({
            "device_name": self.device_name,
            "platform": self.platform,
            "app_version": self.version,
        })
    }
}
