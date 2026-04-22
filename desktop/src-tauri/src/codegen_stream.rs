//! Codegen-stream tail (task 12.1).
//!
//! For an existing run directory, scans `<run_dir>/prompts/*.json` and emits
//! one [`CodegenEvent`] per file (sorted lexicographically by filename, which
//! matches LLM-call order in the Python refinement loop). Subsequent files
//! that appear during the tail interval are also picked up.
//!
//! This is a *batch* tail rather than a live `tail -f` because the Python
//! pipeline writes prompts atomically as JSON files (no partial writes);
//! polling at 1Hz is sufficient and avoids platform-specific inotify code.

use std::collections::HashSet;
use std::path::PathBuf;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::ipc::Channel;
use tokio::fs;
use tokio_util::sync::CancellationToken;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "kebab-case")]
pub enum CodegenEvent {
    Prompt {
        run_id: String,
        seq: u32,
        filename: String,
        body: serde_json::Value,
    },
    /// Codegen subprocess line (when applicable). Stream is currently
    /// surfaced via the main pipeline output pane; this enum variant is
    /// kept for future direct integration.
    StdoutLine {
        line: String,
    },
    Tick,
    Stopped,
}

#[tauri::command]
pub async fn tail_codegen(
    repo: String,
    run_id: String,
    on_event: Channel<CodegenEvent>,
) -> Result<(), String> {
    let repo = PathBuf::from(&repo);
    if !repo.is_dir() {
        return Err(format!("repository not found: {}", repo.display()));
    }
    let prompts_dir = repo.join(".pg_runs").join(&run_id).join("prompts");

    // Tail token: the frontend cancels by dropping the channel which causes
    // future `send`s to fail; we exit on the first send error or after a
    // generous overall wall-clock cap.
    let cancel = CancellationToken::new();
    let mut seen: HashSet<String> = HashSet::new();
    let mut seq: u32 = 0;
    let max_iterations = 60 * 30; // ~30 minutes at 1Hz.

    for _ in 0..max_iterations {
        if cancel.is_cancelled() {
            break;
        }
        if let Ok(mut rd) = fs::read_dir(&prompts_dir).await {
            let mut files: Vec<PathBuf> = Vec::new();
            while let Ok(Some(e)) = rd.next_entry().await {
                let p = e.path();
                if p.extension().and_then(|x| x.to_str()) == Some("json") {
                    files.push(p);
                }
            }
            files.sort();
            for f in files {
                let name = f.file_name().unwrap().to_string_lossy().into_owned();
                if seen.contains(&name) {
                    continue;
                }
                seen.insert(name.clone());
                let body = match fs::read(&f).await {
                    Ok(bytes) => serde_json::from_slice::<serde_json::Value>(&bytes)
                        .unwrap_or(serde_json::Value::String(
                            String::from_utf8_lossy(&bytes).into_owned(),
                        )),
                    Err(_) => continue,
                };
                seq += 1;
                let evt = CodegenEvent::Prompt {
                    run_id: run_id.clone(),
                    seq,
                    filename: name,
                    body,
                };
                if on_event.send(evt).is_err() {
                    return Ok(());
                }
            }
        }
        if on_event.send(CodegenEvent::Tick).is_err() {
            return Ok(());
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
    let _ = on_event.send(CodegenEvent::Stopped);
    Ok(())
}
