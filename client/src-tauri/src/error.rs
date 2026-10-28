use serde::Serialize;

/// Errors as the UI sees them. `kind` lets screens react (sign in again, show plans,
/// stay offline) without parsing messages.
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("{0}")]
    Offline(String),
    #[error("{message}")]
    Server {
        status: u16,
        message: String,
        exc_type: Option<String>,
    },
    #[error("{0}")]
    SignedOut(String),
    #[error("{0}")]
    Storage(String),
    #[error("{0}")]
    Invalid(String),
}

impl AppError {
    pub fn kind(&self) -> &'static str {
        match self {
            AppError::Offline(_) => "offline",
            AppError::SignedOut(_) => "signed_out",
            AppError::Storage(_) => "storage",
            AppError::Invalid(_) => "invalid",
            AppError::Server { status, .. } => match status {
                401 => "signed_out",
                402 => "subscription_required",
                403 => "forbidden",
                404 => "not_found",
                409 => "conflict",
                429 => "too_many",
                503 => "unavailable",
                s if *s >= 500 => "server",
                _ => "rejected",
            },
        }
    }

    pub fn status(&self) -> u16 {
        match self {
            AppError::Server { status, .. } => *status,
            AppError::SignedOut(_) => 401,
            _ => 0,
        }
    }
}

impl Serialize for AppError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut st = s.serialize_struct("AppError", 4)?;
        st.serialize_field("kind", self.kind())?;
        st.serialize_field("status", &self.status())?;
        st.serialize_field("message", &self.to_string())?;
        let exc = match self {
            AppError::Server { exc_type, .. } => exc_type.clone(),
            _ => None,
        };
        st.serialize_field("exc_type", &exc)?;
        st.end()
    }
}

impl From<rusqlite::Error> for AppError {
    fn from(e: rusqlite::Error) -> Self {
        AppError::Storage(format!("Local storage error: {e}"))
    }
}

impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::Invalid(format!("Unexpected data: {e}"))
    }
}

pub type AppResult<T> = Result<T, AppError>;
