//! Who is signed in on this device.
//!
//! The device token is kept in the OS credential store on Windows and macOS. On
//! Android, iOS and Linux it is kept in the app's private SQLite file, which only
//! this app can read.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::error::{AppError, AppResult};
use crate::store::Store;

#[cfg(any(target_os = "windows", target_os = "macos"))]
const KEYRING_SERVICE: &str = "ke.cbctutor.app";

/// `active` is the session in use. `parent` holds a parent's session while their
/// child uses the device, so the parent can switch back without signing in again.
pub const ACTIVE: &str = "active";
pub const PARENT: &str = "parent";

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Session {
    #[serde(skip_serializing, default)]
    pub token: String,
    pub role: String,
    pub user: String,
    pub student: Option<String>,
    pub profile: Value,
}

impl Session {
    pub fn from_login(resp: &Value) -> AppResult<Session> {
        let token = resp
            .get("token")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::Invalid("The server did not return a session.".into()))?;
        let profile = resp.get("profile").cloned().unwrap_or(Value::Null);
        Ok(Session {
            token: token.to_string(),
            role: resp.get("role").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            user: profile.get("user").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            student: profile
                .get("learner")
                .and_then(|l| l.get("student"))
                .and_then(|v| v.as_str())
                .map(String::from),
            profile,
        })
    }

    /// The scope offline data is stored under.
    pub fn scope(&self) -> Option<&str> {
        if self.role == "Learner" {
            self.student.as_deref()
        } else {
            None
        }
    }
}

pub fn save(store: &Store, slot: &str, session: &Session) -> AppResult<()> {
    secret_set(store, slot, &session.token)?;
    store.kv_set(&format!("session:{slot}"), &serde_json::to_string(session)?)
}

pub fn load(store: &Store, slot: &str) -> AppResult<Option<Session>> {
    let Some(raw) = store.kv_get(&format!("session:{slot}"))? else {
        return Ok(None);
    };
    let mut session: Session = serde_json::from_str(&raw)?;
    match secret_get(store, slot)? {
        Some(token) => {
            session.token = token;
            Ok(Some(session))
        }
        None => Ok(None),
    }
}

pub fn clear(store: &Store, slot: &str) -> AppResult<()> {
    secret_del(store, slot)?;
    store.kv_del(&format!("session:{slot}"))
}

#[cfg(any(target_os = "windows", target_os = "macos"))]
fn entry(slot: &str) -> AppResult<keyring::Entry> {
    keyring::Entry::new(KEYRING_SERVICE, &format!("session-{slot}"))
        .map_err(|e| AppError::Storage(format!("Credential store: {e}")))
}

#[cfg(any(target_os = "windows", target_os = "macos"))]
fn secret_set(_store: &Store, slot: &str, token: &str) -> AppResult<()> {
    entry(slot)?
        .set_password(token)
        .map_err(|e| AppError::Storage(format!("Could not save the sign-in: {e}")))
}

#[cfg(any(target_os = "windows", target_os = "macos"))]
fn secret_get(_store: &Store, slot: &str) -> AppResult<Option<String>> {
    match entry(slot)?.get_password() {
        Ok(t) => Ok(Some(t)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(AppError::Storage(format!("Could not read the sign-in: {e}"))),
    }
}

#[cfg(any(target_os = "windows", target_os = "macos"))]
fn secret_del(_store: &Store, slot: &str) -> AppResult<()> {
    match entry(slot)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(AppError::Storage(format!("Could not remove the sign-in: {e}"))),
    }
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
fn secret_set(store: &Store, slot: &str, token: &str) -> AppResult<()> {
    store.kv_set(&format!("token:{slot}"), token)
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
fn secret_get(store: &Store, slot: &str) -> AppResult<Option<String>> {
    store.kv_get(&format!("token:{slot}"))
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
fn secret_del(store: &Store, slot: &str) -> AppResult<()> {
    store.kv_del(&format!("token:{slot}"))
}
