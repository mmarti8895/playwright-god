//! Dry-run / Inspect viewer backend.
//!
//! Wraps three CLI invocations the desktop UI surfaces:
//!   - `playwright-god inspect --json`           → repo classification.
//!   - `playwright-god discover --json`          → routes, actions, journeys.
//!   - `playwright-god generate "<desc>" --dry-run --print-prompt --json`
//!                                                → assembled-prompt preview.
//!
//! All three return their stdout verbatim (or a parsed `serde_json::Value`)
//! so the UI can render flexible JSON without us reshaping the schema.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::process::Command;

use crate::settings::{EffectiveSettings, Settings};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptPreview {
    pub prompt: String,
    pub raw: Option<Value>,
}

fn validate_repo(repo: &str) -> Result<PathBuf, String> {
    let p = PathBuf::from(repo);
    if !p.is_dir() {
        return Err(format!("repository not found: {repo}"));
    }
    Ok(p)
}

async fn cli_json<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    repo: &PathBuf,
    args: &[&str],
) -> Result<Value, String> {
    let settings = Settings::load(app).map_err(|e| e.to_string())?;
    let effective = EffectiveSettings::load_for_repo(app, repo).map_err(|e| e.to_string())?;
    let cli = settings
        .cli_path
        .clone()
        .unwrap_or_else(|| std::env::var("PLAYWRIGHT_GOD_CLI").unwrap_or_else(|_| "playwright-god".into()));

    let mut cmd = Command::new(&cli);
    for a in args {
        cmd.arg(a);
    }
    cmd.current_dir(repo).envs(effective.into_env());
    let output = cmd.output().await.map_err(|e| format!("spawn {cli}: {e}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "{cli} {} failed (exit {:?}): {}",
            args.join(" "),
            output.status.code(),
            stderr.lines().take(3).collect::<Vec<_>>().join(" / ")
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    serde_json::from_str(stdout.trim())
        .map_err(|e| format!("non-JSON output from `{cli} {}`: {e}", args.join(" ")))
}

#[tauri::command]
pub async fn inspect_repo<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    repo: String,
) -> Result<Value, String> {
    let p = validate_repo(&repo)?;
    cli_json(&app, &p, &["inspect", "--json"]).await
}

#[tauri::command]
pub async fn discover_repo<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    repo: String,
) -> Result<Value, String> {
    let p = validate_repo(&repo)?;
    cli_json(&app, &p, &["discover", "--json"]).await
}

#[tauri::command]
pub async fn preview_prompt<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    repo: String,
    description: String,
) -> Result<PromptPreview, String> {
    let p = validate_repo(&repo)?;
    // Note: `--print-prompt` is documented in tasks.md 13.3 as a follow-up CLI
    // feature. We try it first, then fall back to `--print-context` so the UI
    // still has *some* preview to show against the current Python CLI.
    let attempt = cli_json(
        &app,
        &p,
        &[
            "generate",
            &description,
            "--dry-run",
            "--print-prompt",
            "--json",
        ],
    )
    .await;

    let raw = match attempt {
        Ok(v) => v,
        Err(_) => cli_json(
            &app,
            &p,
            &[
                "generate",
                &description,
                "--dry-run",
                "--print-context",
                "--json",
            ],
        )
        .await?,
    };

    let prompt = raw
        .get("prompt")
        .and_then(|x| x.as_str())
        .map(String::from)
        .or_else(|| {
            raw.get("messages")
                .and_then(|x| x.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|m| m.get("content").and_then(|c| c.as_str()))
                        .collect::<Vec<_>>()
                        .join("\n\n---\n\n")
                })
        })
        .or_else(|| {
            raw.get("context")
                .and_then(|x| x.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|m| {
                            let f = m.get("file").and_then(|x| x.as_str()).unwrap_or("?");
                            let c = m
                                .get("content")
                                .or_else(|| m.get("text"))
                                .and_then(|x| x.as_str())
                                .unwrap_or("");
                            Some(format!("// {f}\n{c}"))
                        })
                        .collect::<Vec<_>>()
                        .join("\n\n")
                })
        })
        .unwrap_or_default();

    Ok(PromptPreview {
        prompt,
        raw: Some(raw),
    })
}
