//! On-demand coverage run: spawns `playwright-god run <spec> --coverage`,
//! streams stdout/stderr to the frontend via a [`Channel<CoverageEvent>`],
//! and supports cancellation through a [`CancellationToken`].
//!
//! Intentionally separate from the main pipeline (see design.md D1) so that
//! coverage re-runs can be triggered independently of the full pipeline DAG.

use std::path::PathBuf;
use std::process::Stdio;

use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, Runtime, State};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio_util::sync::CancellationToken;

use crate::artifacts::latest_spec_path;
use crate::pipeline::PipelineRegistry;
use crate::settings::Settings;

// ---------------------------------------------------------------------------
// Event schema (design.md D2)
// ---------------------------------------------------------------------------

/// Events emitted to the frontend during a coverage run.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "kebab-case")]
pub enum CoverageEvent {
    /// The run has started. `spec_path` is the resolved spec file.
    RunStarted { spec_path: String },
    /// A line of output from the subprocess.
    LogLine { stream: LogStream, line: String },
    /// The subprocess exited successfully (exit code 0).
    Finished { exit_code: i32 },
    /// The run was cancelled by the user.
    Cancelled,
    /// The subprocess exited with a non-zero code or could not be spawned.
    Failed { message: String },
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum LogStream {
    Stdout,
    Stderr,
}

// ---------------------------------------------------------------------------
// Registry (design.md D1)
// ---------------------------------------------------------------------------

struct ActiveCoverageRun {
    cancel: CancellationToken,
}

/// Process-wide singleton: at most one coverage run active at a time.
#[derive(Default)]
pub struct CoverageRegistry {
    active: Mutex<Option<ActiveCoverageRun>>,
}

impl CoverageRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    fn try_start(&self) -> Option<CancellationToken> {
        let mut guard = self.active.lock();
        if guard.is_some() {
            return None; // already running
        }
        let cancel = CancellationToken::new();
        *guard = Some(ActiveCoverageRun {
            cancel: cancel.clone(),
        });
        Some(cancel)
    }

    fn finish(&self) {
        self.active.lock().take();
    }

    fn cancel(&self) -> bool {
        let guard = self.active.lock();
        if let Some(run) = guard.as_ref() {
            run.cancel.cancel();
            true
        } else {
            false
        }
    }
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

/// Errors returned by [`run_coverage`].
#[derive(Debug, thiserror::Error)]
pub enum CoverageError {
    #[error("a coverage run is already active")]
    Busy,
    #[error("pipeline run is active for this repository — wait for it to finish")]
    PipelineBusy,
    #[error("no generated spec found in .pg_runs/ — run the full pipeline first")]
    NoSpec,
    #[error("repository path does not exist or is not a directory: {0}")]
    BadRepo(String),
}

impl serde::Serialize for CoverageError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// Tauri command: start a coverage run for `repo`.
///
/// Resolves the most-recent `generated.spec.ts` from `.pg_runs/`, spawns
/// `playwright-god run <spec> --target-dir <repo> --artifact-dir <runs-dir>
/// --coverage`, and streams events through `on_event`.
///
/// Returns an error if another coverage run or the main pipeline is already
/// active, or if no spec file can be found.
#[tauri::command]
pub async fn run_coverage<R: Runtime>(
    app: AppHandle<R>,
    cov_registry: State<'_, CoverageRegistry>,
    pipeline_registry: State<'_, PipelineRegistry>,
    repo: String,
    on_event: Channel<CoverageEvent>,
) -> Result<(), CoverageError> {
    let repo_path = {
        let p = PathBuf::from(&repo);
        if !p.exists() || !p.is_dir() {
            return Err(CoverageError::BadRepo(repo));
        }
        p
    };

    // Block when the main pipeline is running on this repo.
    if pipeline_registry.is_busy_for_repo(&repo) {
        return Err(CoverageError::PipelineBusy);
    }

    // Resolve the spec file before acquiring the lock.
    let spec_path = latest_spec_path(&repo_path).ok_or(CoverageError::NoSpec)?;
    let spec_path_str = spec_path.to_string_lossy().into_owned();
    let runs_dir = repo_path.join(".pg_runs").to_string_lossy().into_owned();

    // Use playwright_target_dir from settings if set, otherwise fall back to repo.
    let effective_target_dir = Settings::load(&app)
        .ok()
        .and_then(|s| s.playwright_target_dir)
        .unwrap_or_else(|| repo.clone());

    // Acquire the coverage lock.
    let cancel = cov_registry.try_start().ok_or(CoverageError::Busy)?;

    // Resolve CLI path (same logic as pipeline.rs).
    let cli_path = Settings::load(&app)
        .ok()
        .and_then(|s| s.cli_path)
        .or_else(|| std::env::var("PLAYWRIGHT_GOD_CLI").ok())
        .unwrap_or_else(|| "playwright-god".into());

    // Clone what we need before moving into the spawn.
    let app_clone = app.clone();
    let repo_clone = repo.clone();
    let channel = on_event.clone();
    let spec_path_clone = spec_path_str.clone();

    tauri::async_runtime::spawn(async move {
        run_coverage_inner(
            effective_target_dir,
            repo_clone,
            spec_path_clone,
            runs_dir,
            cli_path,
            cancel,
            channel,
        )
        .await;

        // Always release the lock when done.
        if let Some(reg) = app_clone.try_state::<CoverageRegistry>() {
            reg.finish();
        }
    });

    // Emit RunStarted synchronously so the frontend sees the spec path.
    let _ = on_event.send(CoverageEvent::RunStarted {
        spec_path: spec_path_str,
    });

    Ok(())
}

/// Tauri command: cancel the active coverage run (if any).
/// Returns `true` if a run was cancelled, `false` if nothing was running.
#[tauri::command]
pub fn cancel_coverage(registry: State<'_, CoverageRegistry>) -> bool {
    registry.cancel()
}

// ---------------------------------------------------------------------------
// Inner async runner
// ---------------------------------------------------------------------------

async fn run_coverage_inner(
    target_dir: String,
    repo: String,
    spec_path: String,
    runs_dir: String,
    cli_path: String,
    cancel: CancellationToken,
    channel: Channel<CoverageEvent>,
) {
    let mut cmd = Command::new(&cli_path);
    cmd.args([
        "run",
        &spec_path,
        "--target-dir",
        &target_dir,
        "--artifact-dir",
        &runs_dir,
        "--coverage",
    ]);
    cmd.current_dir(&repo);
    cmd.stdin(Stdio::null());
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            let _ = channel.send(CoverageEvent::Failed {
                message: format!("failed to spawn `{cli_path} run`: {e}"),
            });
            return;
        }
    };

    let stdout = child.stdout.take().expect("piped");
    let stderr = child.stderr.take().expect("piped");
    let mut stdout_lines = BufReader::new(stdout).lines();
    let mut stderr_lines = BufReader::new(stderr).lines();

    let exit_code = loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                let _ = child.kill().await;
                let _ = channel.send(CoverageEvent::Cancelled);
                return;
            }
            line = stdout_lines.next_line() => {
                match line {
                    Ok(Some(l)) => {
                        let _ = channel.send(CoverageEvent::LogLine {
                            stream: LogStream::Stdout,
                            line: l,
                        });
                    }
                    Ok(None) => {
                        // stdout closed; drain stderr then wait.
                        while let Ok(Some(l)) = stderr_lines.next_line().await {
                            let _ = channel.send(CoverageEvent::LogLine {
                                stream: LogStream::Stderr,
                                line: l,
                            });
                        }
                        let status = match child.wait().await {
                            Ok(s) => s,
                            Err(e) => {
                                let _ = channel.send(CoverageEvent::Failed {
                                    message: format!("wait error: {e}"),
                                });
                                return;
                            }
                        };
                        break status.code().unwrap_or(-1);
                    }
                    Err(e) => {
                        let _ = channel.send(CoverageEvent::Failed {
                            message: format!("io error reading stdout: {e}"),
                        });
                        return;
                    }
                }
            }
            line = stderr_lines.next_line() => {
                if let Ok(Some(l)) = line {
                    let _ = channel.send(CoverageEvent::LogLine {
                        stream: LogStream::Stderr,
                        line: l,
                    });
                }
            }
        }
    };

    if exit_code == 0 {
        let _ = channel.send(CoverageEvent::Finished { exit_code });
    } else {
        let _ = channel.send(CoverageEvent::Failed {
            message: format!("coverage run exited with code {exit_code}"),
        });
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn latest_spec_path_returns_none_when_pg_runs_absent() {
        let dir = TempDir::new().unwrap();
        assert!(latest_spec_path(dir.path()).is_none());
    }

    #[test]
    fn latest_spec_path_returns_spec_from_newest_run() {
        let dir = TempDir::new().unwrap();
        let runs = dir.path().join(".pg_runs");
        fs::create_dir_all(&runs).unwrap();

        // older run — no spec
        let old_run = runs.join("20260101T000000.000Z");
        fs::create_dir_all(&old_run).unwrap();

        // newer run — has spec
        let new_run = runs.join("20260424T120000.000Z");
        fs::create_dir_all(&new_run).unwrap();
        fs::write(new_run.join("generated.spec.ts"), "// spec").unwrap();

        let result = latest_spec_path(dir.path());
        assert!(result.is_some());
        assert!(result
            .unwrap()
            .to_string_lossy()
            .contains("20260424T120000.000Z"));
    }

    #[test]
    fn latest_spec_path_skips_runs_without_spec() {
        let dir = TempDir::new().unwrap();
        let runs = dir.path().join(".pg_runs");
        fs::create_dir_all(&runs).unwrap();

        // newest run — no spec
        let new_run = runs.join("20260424T120000.000Z");
        fs::create_dir_all(&new_run).unwrap();

        // older run — has spec
        let old_run = runs.join("20260101T000000.000Z");
        fs::create_dir_all(&old_run).unwrap();
        fs::write(old_run.join("generated.spec.ts"), "// spec").unwrap();

        let result = latest_spec_path(dir.path());
        assert!(result.is_some());
        assert!(result
            .unwrap()
            .to_string_lossy()
            .contains("20260101T000000.000Z"));
    }
}
