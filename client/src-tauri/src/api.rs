//! The HTTP side: calls `cbc_ai_tutor.api.*` methods on the Frappe server.
//!
//! Requests go out from Rust, not the web view, so there is no CORS to configure
//! on the server and the device token never reaches JavaScript.

use std::time::Duration;

use serde_json::{Map, Value};

use crate::error::{AppError, AppResult};

const METHOD_PREFIX: &str = "/api/method/cbc_ai_tutor.api.";

#[derive(Clone)]
pub struct Api {
    http: reqwest::Client,
}

impl Api {
    pub fn new(user_agent: &str) -> Self {
        let http = reqwest::Client::builder()
            .user_agent(user_agent)
            .connect_timeout(Duration::from_secs(10))
            .timeout(Duration::from_secs(90))
            .build()
            .expect("HTTP client");
        Api { http }
    }

    /// `path` is relative to `cbc_ai_tutor.api.`, e.g. `sync.pull`.
    pub async fn call(
        &self,
        server: &str,
        http_method: &str,
        path: &str,
        args: &Value,
        token: Option<&str>,
    ) -> AppResult<Value> {
        if server.is_empty() {
            return Err(AppError::Invalid("This build has no school address.".into()));
        }
        if !path.chars().all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '_') {
            return Err(AppError::Invalid("Bad API path.".into()));
        }
        let url = format!("{}{}{}", server.trim_end_matches('/'), METHOD_PREFIX, path);
        let mut req = if http_method.eq_ignore_ascii_case("GET") {
            self.http.get(&url).query(&query_pairs(args))
        } else {
            self.http.post(&url).json(args)
        };
        req = req.header("Accept", "application/json");
        if let Some(t) = token {
            req = req.bearer_auth(t);
        }

        let resp = req.send().await.map_err(|e| {
            if e.is_timeout() {
                AppError::Offline("The server took too long to answer.".into())
            } else {
                AppError::Offline("No connection to the server.".into())
            }
        })?;
        let status = resp.status().as_u16();
        let text = resp.text().await.unwrap_or_default();
        let body: Value = serde_json::from_str(&text).unwrap_or(Value::Null);

        if (200..300).contains(&status) {
            return Ok(body.get("message").cloned().unwrap_or(Value::Null));
        }
        let message = server_message(&body).unwrap_or_else(|| match status {
            401 => "Please sign in again.".into(),
            404 => "The server does not have this feature. Is the app up to date?".into(),
            502..=504 => "The server is not reachable right now.".into(),
            _ => format!("The server could not do that (error {status})."),
        });
        if status == 401 {
            return Err(AppError::SignedOut(message));
        }
        Err(AppError::Server {
            status,
            message,
            exc_type: body.get("exc_type").and_then(|v| v.as_str()).map(String::from),
        })
    }
}

/// GET arguments: scalars as-is, everything else JSON-encoded (how Frappe reads them).
fn query_pairs(args: &Value) -> Vec<(String, String)> {
    let mut out = Vec::new();
    if let Value::Object(map) = args {
        for (k, v) in map {
            match v {
                Value::Null => {}
                Value::String(s) => out.push((k.clone(), s.clone())),
                Value::Bool(b) => out.push((k.clone(), if *b { "1".into() } else { "0".into() })),
                Value::Number(n) => out.push((k.clone(), n.to_string())),
                other => out.push((k.clone(), other.to_string())),
            }
        }
    }
    out
}

/// The human message out of a Frappe error response.
fn server_message(body: &Value) -> Option<String> {
    if let Some(raw) = body.get("_server_messages").and_then(|v| v.as_str()) {
        if let Ok(list) = serde_json::from_str::<Vec<String>>(raw) {
            for item in list.iter().rev() {
                let msg = serde_json::from_str::<Map<String, Value>>(item)
                    .ok()
                    .and_then(|m| m.get("message").and_then(|v| v.as_str()).map(String::from))
                    .unwrap_or_else(|| item.clone());
                let msg = strip_tags(&msg);
                if !msg.trim().is_empty() {
                    return Some(msg.trim().to_string());
                }
            }
        }
    }
    if let Some(exc) = body.get("exception").and_then(|v| v.as_str()) {
        let msg = exc.split_once(": ").map(|(_, m)| m).unwrap_or(exc);
        return Some(strip_tags(msg).trim().to_string());
    }
    body.get("message").and_then(|v| v.as_str()).map(|s| strip_tags(s))
}

fn strip_tags(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut in_tag = false;
    for c in s.chars() {
        match c {
            '<' => in_tag = true,
            '>' if in_tag => in_tag = false,
            _ if !in_tag => out.push(c),
            _ => {}
        }
    }
    out.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn reads_frappe_server_messages() {
        let body = json!({
            "exc_type": "ValidationError",
            "_server_messages": "[\"{\\\"message\\\": \\\"A PIN is <b>4 to 8</b> digits.\\\"}\"]"
        });
        assert_eq!(server_message(&body).unwrap(), "A PIN is 4 to 8 digits.");
    }

    #[test]
    fn falls_back_to_exception_text() {
        let body = json!({"exception": "frappe.exceptions.ValidationError: Order By has invalid notation"});
        assert_eq!(server_message(&body).unwrap(), "Order By has invalid notation");
    }

    #[test]
    fn encodes_query_values() {
        let pairs = query_pairs(&json!({"since": "2026-01-01", "entitled": true, "limit": 5, "x": null, "events": [1]}));
        assert!(pairs.contains(&("entitled".into(), "1".into())));
        assert!(pairs.contains(&("limit".into(), "5".into())));
        assert!(pairs.contains(&("events".into(), "[1]".into())));
        assert!(!pairs.iter().any(|(k, _)| k == "x"));
    }
}
