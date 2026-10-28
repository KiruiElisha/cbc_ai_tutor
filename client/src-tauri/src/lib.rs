mod api;
mod commands;
mod error;
mod session;
mod state;
mod store;
mod sync;

use std::sync::Mutex;

use tauri::Manager;

fn device_name() -> String {
    for var in ["COMPUTERNAME", "HOSTNAME"] {
        if let Ok(name) = std::env::var(var) {
            if !name.trim().is_empty() {
                return name;
            }
        }
    }
    match std::env::consts::OS {
        "android" => "Android device".into(),
        "ios" => "iPhone or iPad".into(),
        os => os.to_string(),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default();

    #[cfg(desktop)]
    {
        // A second launch (for example from a cbctutor:// link) focuses this window
        // and passes the link on instead of opening another copy.
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }));
    }

    builder
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            #[cfg(all(desktop, any(debug_assertions, target_os = "linux", target_os = "windows")))]
            {
                use tauri_plugin_deep_link::DeepLinkExt;
                let _ = app.deep_link().register_all();
            }

            let dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&dir)?;
            let store = store::Store::open(&dir.join("cbc-tutor.sqlite3"))
                .map_err(|e| Box::<dyn std::error::Error>::from(e.to_string()))?;
            let version = app.package_info().version.to_string();
            let platform = std::env::consts::OS.to_string();
            let active = session::load(&store, session::ACTIVE).unwrap_or(None);
            app.manage(state::AppState {
                api: api::Api::new(&format!("CBCTutor/{version} ({platform})")),
                store,
                session: Mutex::new(active),
                sync_lock: tokio::sync::Mutex::new(()),
                device_name: device_name(),
                platform,
                version,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::app_state,
            commands::set_server,
            commands::login,
            commands::learner_login,
            commands::signup_parent,
            commands::open_learner,
            commands::back_to_parent,
            commands::logout,
            commands::api,
            commands::sync_now,
            commands::learner_status,
            commands::local_list,
            commands::local_get,
            commands::local_quiz,
            commands::mine_list,
            commands::queue_event,
            commands::outbox_list,
            commands::outbox_discard,
            commands::wipe_device,
        ])
        .run(tauri::generate_context!())
        .expect("error while running CBC Tutor");
}
