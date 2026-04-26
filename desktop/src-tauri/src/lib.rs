//! Tauri 2 backend for the Playwright God desktop shell.

mod cli_detect;
mod coverage_run;
mod pipeline;
mod recent_repos;
mod secrets;
mod settings;
mod artifacts;
mod runs;
mod inspect;
mod codegen_stream;

use serde::{Deserialize, Serialize};
#[cfg(target_os = "macos")]
use tauri::Manager;
use tauri::Runtime;
use tauri_plugin_dialog::DialogExt;

use pipeline::PipelineRegistry;
use coverage_run::CoverageRegistry;

#[cfg(target_os = "macos")]
use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial, NSVisualEffectState};

use recent_repos::{add_recent, list_recent, RecentRepo};

const STORE_PATH: &str = "settings.json";
const KEY_OUTPUT_PANE_COLLAPSED: &str = "output_pane_collapsed";

/// Tauri command: open a native folder dialog and return the chosen path.
/// Returns `None` if the user cancels or the path fails validation.
#[tauri::command]
async fn pick_repository<R: Runtime>(app: tauri::AppHandle<R>) -> Result<Option<String>, String> {
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .set_title("Select a repository")
        .pick_folder(move |folder| {
            let _ = tx.send(folder);
        });
    let folder = rx.await.map_err(|e| e.to_string())?;
    let Some(path) = folder else { return Ok(None) };
    let s = path.to_string();
    // Validate the chosen path exists and is a directory.
    let pb = std::path::PathBuf::from(&s);
    if !pb.exists() || !pb.is_dir() {
        return Ok(None);
    }
    Ok(Some(s))
}

/// Tauri command: list the persisted recent repositories.
#[tauri::command]
fn list_recent_repos<R: Runtime>(app: tauri::AppHandle<R>) -> Result<Vec<RecentRepo>, String> {
    list_recent(&app).map_err(|e| e.to_string())
}

/// Tauri command: add a repository to the recent list (MRU, capped at 10).
#[tauri::command]
fn add_recent_repo<R: Runtime>(
    app: tauri::AppHandle<R>,
    path: String,
) -> Result<Vec<RecentRepo>, String> {
    add_recent(&app, &path).map_err(|e| e.to_string())
}

/// Tauri command: read the persisted "output pane collapsed" flag.
#[tauri::command]
fn get_output_pane_collapsed<R: Runtime>(app: tauri::AppHandle<R>) -> Result<bool, String> {
    use tauri_plugin_store::StoreExt;
    let store = app.store(STORE_PATH).map_err(|e| e.to_string())?;
    let v = store
        .get(KEY_OUTPUT_PANE_COLLAPSED)
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    Ok(v)
}

/// Tauri command: persist the "output pane collapsed" flag.
#[tauri::command]
fn set_output_pane_collapsed<R: Runtime>(
    app: tauri::AppHandle<R>,
    collapsed: bool,
) -> Result<(), String> {
    use tauri_plugin_store::StoreExt;
    let store = app.store(STORE_PATH).map_err(|e| e.to_string())?;
    store.set(KEY_OUTPUT_PANE_COLLAPSED, serde_json::Value::Bool(collapsed));
    store.save().map_err(|e| e.to_string())?;
    Ok(())
}

/// Returned to the frontend on first-run / diagnostics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformInfo {
    pub family: String, // "macos" | "linux" | "windows" | "other"
}

#[tauri::command]
fn platform_info() -> PlatformInfo {
    let family = if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else if cfg!(target_os = "windows") {
        "windows"
    } else {
        "other"
    }
    .to_string();
    PlatformInfo { family }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .manage(PipelineRegistry::new())
        .manage(CoverageRegistry::new())
        .setup(|app| {
            // Apply NSVisualEffectView vibrancy on macOS so the sidebar feels native.
            #[cfg(target_os = "macos")]
            if let Some(window) = app.get_webview_window("main") {
                let _ = apply_vibrancy(
                    &window,
                    NSVisualEffectMaterial::Sidebar,
                    Some(NSVisualEffectState::Active),
                    None,
                );
            }
            let _ = app;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            pick_repository,
            list_recent_repos,
            add_recent_repo,
            get_output_pane_collapsed,
            set_output_pane_collapsed,
            platform_info,
            pipeline::run_pipeline,
            pipeline::cancel_pipeline,
            settings::get_settings,
            settings::save_settings,
            settings::reset_settings,
            settings::get_effective_settings_summary,
            secrets::get_secret,
            secrets::set_secret,
            secrets::delete_secret,
            secrets::secrets_health,
            cli_detect::detect_cli,
            artifacts::read_memory_map,
            artifacts::read_index_status,
            artifacts::read_flow_graph,
            artifacts::read_coverage,
            artifacts::read_latest_spec_path,
            artifacts::rag_search,
            runs::list_runs,
            inspect::inspect_repo,
            inspect::discover_repo,
            inspect::preview_prompt,
            codegen_stream::tail_codegen,
            coverage_run::run_coverage,
            coverage_run::cancel_coverage,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
