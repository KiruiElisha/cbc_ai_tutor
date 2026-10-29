use std::sync::Mutex;

use crate::api::Api;
use crate::error::{AppError, AppResult};
use crate::session::{self, Session};
use crate::store::Store;

/// The server this build talks to. It is fixed at build time and not shown in the app.
/// Override with `CBC_SERVER_URL=https://tutor.example.co.ke` when building.
pub const DEFAULT_SERVER: &str = match option_env!("CBC_SERVER_URL") {
    Some(url) => url,
    None => "https://school.nergaa.cloud",
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
        let url = DEFAULT_SERVER.trim().trim_end_matches('/').to_string();
        if url.is_empty() {
            return Err(AppError::Invalid("This build has no server address.".into()));
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
