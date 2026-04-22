//! Detect whether the `playwright-god` CLI is reachable. Used at startup
//! (task 6.6) to surface a "CLI not found" callout in Settings.

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Runtime};

use crate::settings::Settings;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CliStatus {
    pub found: bool,
    pub path: Option<String>,
    pub source: &'static str, // "settings" | "PATH" | "missing"
}

#[tauri::command]
pub fn detect_cli<R: Runtime>(app: AppHandle<R>) -> CliStatus {
    let settings = Settings::load(&app).unwrap_or_default();

    if let Some(p) = settings.cli_path.as_ref() {
        let pb = std::path::PathBuf::from(p);
        if pb.is_file() {
            return CliStatus {
                found: true,
                path: Some(p.clone()),
                source: "settings",
            };
        }
    }

    match which::which("playwright-god") {
        Ok(p) => CliStatus {
            found: true,
            path: Some(p.to_string_lossy().to_string()),
            source: "PATH",
        },
        Err(_) => CliStatus {
            found: false,
            path: None,
            source: "missing",
        },
    }
}
