//! Pipeline orchestration: spawns the `playwright-god` CLI as subprocesses,
//! forwards stdout/stderr to the frontend over a typed [`tauri::ipc::Channel`],
//! supports cancellation, env-var injection, and a concurrency lock so only
//! one run is active at a time.
//!
//! ## Step DAG (D5)
//!
//! Sequential: `index → memory-map → flow-graph → plan → generate → run`.
//!
//! Note: `memory-map` remains a virtual artifact step because it is produced as
//! a side-effect of `index --memory-map`, while `flow-graph` now shells out to
//! `playwright-god graph extract`. The UI still sees a stable six-step pipeline.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;

use chrono::Utc;
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, Runtime, State};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::Notify;
use tokio_util::sync::CancellationToken;

use crate::settings::{EffectiveSettings, Settings};

/// Maximum lines forwarded into a single channel before older lines are
/// spilled to `<repo>/.pg_runs/<run_id>/desktop_log.txt` (D12).
pub const MAX_LINES_IN_MEMORY: usize = 50_000;

/// Identifier for a single pipeline run (timestamp-based, sortable).
pub type RunId = String;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "kebab-case")]
pub enum PipelineMode {
    #[default]
    Full,
    IndexOnly,
}

const FULL_PIPELINE_STEPS: [PipelineStep; 6] = [
    PipelineStep::Index,
    PipelineStep::MemoryMap,
    PipelineStep::FlowGraph,
    PipelineStep::Plan,
    PipelineStep::Generate,
    PipelineStep::Run,
];

const INDEX_ONLY_STEPS: [PipelineStep; 1] = [PipelineStep::Index];

/// Logical pipeline step. Wire format = kebab-case so the TS union matches
/// the design.md D4 schema directly.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum PipelineStep {
    Index,
    MemoryMap,
    FlowGraph,
    Plan,
    Generate,
    Run,
}

impl PipelineStep {
    pub fn label(self) -> &'static str {
        match self {
            PipelineStep::Index => "index",
            PipelineStep::MemoryMap => "memory-map",
            PipelineStep::FlowGraph => "flow-graph",
            PipelineStep::Plan => "plan",
            PipelineStep::Generate => "generate",
            PipelineStep::Run => "run",
        }
    }
}

#[derive(Debug, Clone)]
struct PipelinePaths {
    repo: PathBuf,
    persist_dir: PathBuf,
    memory_map_path: PathBuf,
    flow_graph_path: PathBuf,
    run_artifact_dir: PathBuf,
    run_root: PathBuf,
    plan_path: PathBuf,
    generated_spec_path: PathBuf,
}

impl PipelinePaths {
    fn new(repo: &str, run_id: &str) -> Self {
        let repo = PathBuf::from(repo);
        let persist_dir = repo.join(".idx");
        let run_artifact_dir = repo.join(".pg_runs");
        let run_root = run_artifact_dir.join(run_id);
        Self {
            repo,
            persist_dir: persist_dir.clone(),
            memory_map_path: persist_dir.join("memory_map.json"),
            flow_graph_path: persist_dir.join("flow_graph.json"),
            run_artifact_dir,
            run_root: run_root.clone(),
            plan_path: run_root.join("plan.md"),
            generated_spec_path: run_root.join("generated.spec.ts"),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum StepExecution {
    Virtual,
    Spawn { cwd: PathBuf, args: Vec<String> },
}

fn path_arg(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn build_step_execution(
    step: PipelineStep,
    paths: &PipelinePaths,
    description: &str,
) -> StepExecution {
    let repo = path_arg(&paths.repo);
    let persist_dir = path_arg(&paths.persist_dir);
    let memory_map_path = path_arg(&paths.memory_map_path);
    let flow_graph_path = path_arg(&paths.flow_graph_path);
    let plan_path = path_arg(&paths.plan_path);
    let generated_spec_path = path_arg(&paths.generated_spec_path);
    let run_artifact_dir = path_arg(&paths.run_artifact_dir);

    match step {
        PipelineStep::Index => StepExecution::Spawn {
            cwd: paths.repo.clone(),
            args: vec![
                "index".into(),
                repo,
                "--persist-dir".into(),
                persist_dir,
                "--memory-map".into(),
                memory_map_path,
            ],
        },
        PipelineStep::MemoryMap => StepExecution::Virtual,
        PipelineStep::FlowGraph => StepExecution::Spawn {
            cwd: paths.repo.clone(),
            args: vec![
                "graph".into(),
                "extract".into(),
                repo,
                "--output".into(),
                flow_graph_path,
                "--persist-dir".into(),
                persist_dir,
            ],
        },
        PipelineStep::Plan => StepExecution::Spawn {
            cwd: paths.repo.clone(),
            args: vec![
                "plan".into(),
                "--persist-dir".into(),
                persist_dir,
                "--memory-map".into(),
                memory_map_path,
                "--flow-graph".into(),
                flow_graph_path,
                "-o".into(),
                plan_path,
            ],
        },
        PipelineStep::Generate => StepExecution::Spawn {
            cwd: paths.repo.clone(),
            args: vec![
                "generate".into(),
                description.into(),
                "--persist-dir".into(),
                persist_dir,
                "--memory-map".into(),
                memory_map_path,
                "-o".into(),
                generated_spec_path,
            ],
        },
        PipelineStep::Run => StepExecution::Spawn {
            cwd: paths.repo.clone(),
            args: vec![
                "run".into(),
                generated_spec_path,
                "--target-dir".into(),
                repo,
                "--artifact-dir".into(),
                run_artifact_dir,
            ],
        },
    }
}

impl PipelineMode {
    pub fn steps(self) -> &'static [PipelineStep] {
        match self {
            PipelineMode::Full => &FULL_PIPELINE_STEPS,
            PipelineMode::IndexOnly => &INDEX_ONLY_STEPS,
        }
    }
}

/// Frontend-bound pipeline event (D4 schema).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "kebab-case")]
pub enum PipelineEvent {
    /// A new pipeline run has begun. Sent once at the start.
    RunStarted {
        run_id: RunId,
        steps: Vec<&'static str>,
    },
    Started {
        step: &'static str,
    },
    StdoutLine {
        step: &'static str,
        line: String,
    },
    StderrLine {
        step: &'static str,
        line: String,
    },
    Progress {
        step: &'static str,
        fraction: f32,
    },
    /// A single step finished successfully.
    Finished {
        step: &'static str,
        exit_code: i32,
    },
    /// The whole run was cancelled by the user.
    Cancelled {
        run_id: RunId,
    },
    /// A step failed; downstream steps are skipped.
    Failed {
        step: &'static str,
        exit_code: i32,
        message: String,
    },
    /// The whole run completed successfully (after every step finished).
    RunFinished {
        run_id: RunId,
    },
}

/// Errors returned by [`run_pipeline`].
#[derive(Debug, thiserror::Error)]
pub enum PipelineError {
    #[error("a pipeline run is already active")]
    Busy,
    #[error("repository path does not exist or is not a directory: {0}")]
    BadRepo(String),
    #[error("io error: {0}")]
    Io(String),
}

impl serde::Serialize for PipelineError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// Per-run live handle: exposes the cancellation token and the run id so
/// `cancel_pipeline` can find and stop the active subprocess.
struct ActiveRun {
    run_id: RunId,
    repo: String,
    mode: PipelineMode,
    cancel: CancellationToken,
    /// Notified when the run finishes (success / fail / cancelled).
    done: Arc<Notify>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ActiveRunSnapshot {
    pub run_id: RunId,
    pub repo: String,
    pub mode: PipelineMode,
}

/// Process-wide state: at most one active run.
#[derive(Default)]
pub struct PipelineRegistry {
    active: Mutex<Option<ActiveRun>>,
}

impl PipelineRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    fn try_start(
        &self,
        run_id: RunId,
        repo: String,
        mode: PipelineMode,
    ) -> Result<(CancellationToken, Arc<Notify>), PipelineError> {
        let mut guard = self.active.lock();
        if guard.is_some() {
            return Err(PipelineError::Busy);
        }
        let cancel = CancellationToken::new();
        let done = Arc::new(Notify::new());
        *guard = Some(ActiveRun {
            run_id,
            repo,
            mode,
            cancel: cancel.clone(),
            done: done.clone(),
        });
        Ok((cancel, done))
    }

    fn finish(&self) {
        let active = self.active.lock().take();
        if let Some(a) = active {
            a.done.notify_waiters();
        }
    }

    fn cancel(&self, run_id: Option<&str>) -> bool {
        let guard = self.active.lock();
        match guard.as_ref() {
            Some(active) if run_id.map(|r| r == active.run_id).unwrap_or(true) => {
                active.cancel.cancel();
                true
            }
            _ => false,
        }
    }

    pub fn active_for_repo(&self, repo: &str) -> Option<ActiveRunSnapshot> {
        let guard = self.active.lock();
        guard.as_ref().and_then(|active| {
            if active.repo != repo {
                return None;
            }
            Some(ActiveRunSnapshot {
                run_id: active.run_id.clone(),
                repo: active.repo.clone(),
                mode: active.mode,
            })
        })
    }
}

/// Tauri command wrapper for [`run_pipeline_inner`].
#[tauri::command]
pub async fn run_pipeline<R: Runtime>(
    app: AppHandle<R>,
    registry: State<'_, PipelineRegistry>,
    repo: String,
    on_event: Channel<PipelineEvent>,
    mode: Option<PipelineMode>,
    description: Option<String>,
) -> Result<RunId, PipelineError> {
    let pb = PathBuf::from(&repo);
    if !pb.exists() || !pb.is_dir() {
        return Err(PipelineError::BadRepo(repo));
    }

    let mode = mode.unwrap_or_default();
    let run_id = new_run_id();
    let (cancel, _done) = registry.try_start(run_id.clone(), repo.clone(), mode)?;
    let registry_arc: tauri::State<PipelineRegistry> = registry;
    // Clone what we need into the spawned task; the registry is process state.
    let app_clone = app.clone();
    let repo_clone = repo.clone();
    let run_id_clone = run_id.clone();

    // The settings env (D8). Read here so failure surfaces synchronously.
    let env = EffectiveSettings::load(&app).map(|s| s.into_env()).unwrap_or_default();
    let cli_path = Settings::load(&app)
        .ok()
        .and_then(|s| s.cli_path)
        .or_else(|| std::env::var("PLAYWRIGHT_GOD_CLI").ok())
        .unwrap_or_else(|| "playwright-god".into());

    // Drop the State guard before spawning so the lock isn't held across
    // .await points.
    drop(registry_arc);

    tauri::async_runtime::spawn(async move {
        let result = run_pipeline_inner(
            &app_clone,
            &repo_clone,
            &run_id_clone,
            &cli_path,
            env,
            mode,
            description.clone(),
            cancel.clone(),
            on_event,
        )
        .await;
        // Always release the active-run slot.
        if let Some(reg) = app_clone.try_state::<PipelineRegistry>() {
            reg.finish();
        }
        // Errors are already surfaced as channel events; nothing else to do.
        let _ = result;
    });

    Ok(run_id)
}

/// Tauri command: cancel the active pipeline run (if any).
#[tauri::command]
pub fn cancel_pipeline<R: Runtime>(
    _app: AppHandle<R>,
    registry: State<'_, PipelineRegistry>,
    run_id: Option<String>,
) -> bool {
    registry.cancel(run_id.as_deref())
}

/// Generate a new sortable run id (UTC RFC3339 with millis, ':' replaced
/// for filesystem-friendliness).
pub fn new_run_id() -> RunId {
    Utc::now()
        .format("%Y%m%dT%H%M%S%.3fZ")
        .to_string()
}

async fn run_pipeline_inner<R: Runtime>(
    _app: &AppHandle<R>,
    repo: &str,
    run_id: &str,
    cli_path: &str,
    env: HashMap<String, String>,
    mode: PipelineMode,
    description: Option<String>,
    cancel: CancellationToken,
    channel: Channel<PipelineEvent>,
) -> Result<(), PipelineError> {
    let steps = mode.steps();
    let paths = PipelinePaths::new(repo, run_id);
    let _ = channel.send(PipelineEvent::RunStarted {
        run_id: run_id.to_string(),
        steps: steps.iter().map(|s| s.label()).collect(),
    });

    // Per-run line counter / spill file (D12).
    let spill_path = paths.run_root.join("desktop_log.txt");
    let _ = tokio::fs::create_dir_all(spill_path.parent().unwrap()).await;
    let mut forwarded: usize = 0;
    let mut spill: Option<tokio::fs::File> = None;
    let description = description.unwrap_or_default();

    for step in steps.iter().copied() {
        if cancel.is_cancelled() {
            let _ = channel.send(PipelineEvent::Cancelled {
                run_id: run_id.to_string(),
            });
            return Ok(());
        }
        let _ = channel.send(PipelineEvent::Started { step: step.label() });

        let execution = build_step_execution(step, &paths, &description);
        let StepExecution::Spawn { cwd, args } = execution else {
            let _ = channel.send(PipelineEvent::Finished {
                step: step.label(),
                exit_code: 0,
            });
            continue;
        };

        let mut cmd = Command::new(cli_path);
        cmd.args(&args);
        cmd.current_dir(cwd);
        cmd.envs(env.iter());
        cmd.stdin(Stdio::null());
        cmd.stdout(Stdio::piped());
        cmd.stderr(Stdio::piped());

        let mut child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                let _ = channel.send(PipelineEvent::Failed {
                    step: step.label(),
                    exit_code: -1,
                    message: format!("failed to spawn `{cli_path} {}`: {e}", args.join(" ")),
                });
                return Ok(());
            }
        };

        let stdout = child.stdout.take().expect("piped");
        let stderr = child.stderr.take().expect("piped");
        let mut stdout = BufReader::new(stdout).lines();
        let mut stderr = BufReader::new(stderr).lines();

        let step_label = step.label();
        let exit_code = loop {
            tokio::select! {
                _ = cancel.cancelled() => {
                    // Best-effort kill, then emit cancelled and bail.
                    let _ = child.kill().await;
                    let _ = channel.send(PipelineEvent::Cancelled { run_id: run_id.to_string() });
                    return Ok(());
                }
                line = stdout.next_line() => {
                    match line {
                        Ok(Some(l)) => {
                            forward_line(&channel, &mut forwarded, &mut spill, &spill_path, step_label, false, l).await;
                        }
                        Ok(None) => {
                            // stdout closed; drain stderr fully then wait for exit.
                            while let Ok(Some(l)) = stderr.next_line().await {
                                forward_line(&channel, &mut forwarded, &mut spill, &spill_path, step_label, true, l).await;
                            }
                            let status = child.wait().await.map_err(|e| PipelineError::Io(e.to_string()))?;
                            break status.code().unwrap_or(-1);
                        }
                        Err(e) => {
                            return Err(PipelineError::Io(e.to_string()));
                        }
                    }
                }
                line = stderr.next_line() => {
                    if let Ok(Some(l)) = line {
                        forward_line(&channel, &mut forwarded, &mut spill, &spill_path, step_label, true, l).await;
                    }
                }
            }
        };

        if exit_code != 0 {
            let _ = channel.send(PipelineEvent::Failed {
                step: step.label(),
                exit_code,
                message: format!("step `{}` exited with code {exit_code}", step.label()),
            });
            return Ok(());
        }

        let _ = channel.send(PipelineEvent::Finished {
            step: step.label(),
            exit_code,
        });
    }

    let _ = channel.send(PipelineEvent::RunFinished {
        run_id: run_id.to_string(),
    });
    Ok(())
}

async fn forward_line(
    channel: &Channel<PipelineEvent>,
    forwarded: &mut usize,
    spill: &mut Option<tokio::fs::File>,
    spill_path: &std::path::Path,
    step: &'static str,
    is_stderr: bool,
    line: String,
) {
    if *forwarded < MAX_LINES_IN_MEMORY {
        let _ = if is_stderr {
            channel.send(PipelineEvent::StderrLine {
                step,
                line: line.clone(),
            })
        } else {
            channel.send(PipelineEvent::StdoutLine {
                step,
                line: line.clone(),
            })
        };
        *forwarded += 1;
    } else {
        // Spill to disk; lazily open the file on first overflow.
        if spill.is_none() {
            if let Ok(f) = tokio::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(spill_path)
                .await
            {
                *spill = Some(f);
            }
        }
        if let Some(f) = spill.as_mut() {
            use tokio::io::AsyncWriteExt;
            let stream = if is_stderr { "ERR" } else { "OUT" };
            let _ = f
                .write_all(format!("[{step}][{stream}] {line}\n").as_bytes())
                .await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pipeline_event_serializes_to_kebab_tagged_union() {
        let ev = PipelineEvent::Started { step: "index" };
        let s = serde_json::to_string(&ev).unwrap();
        assert!(s.contains("\"type\":\"started\""), "got: {s}");
        assert!(s.contains("\"step\":\"index\""), "got: {s}");
    }

    #[test]
    fn pipeline_event_progress_carries_fraction() {
        let ev = PipelineEvent::Progress {
            step: "generate",
            fraction: 0.5,
        };
        let v: serde_json::Value = serde_json::to_value(ev).unwrap();
        assert_eq!(v["type"], "progress");
        assert_eq!(v["step"], "generate");
        assert!((v["fraction"].as_f64().unwrap() - 0.5).abs() < 1e-6);
    }

    #[test]
    fn pipeline_step_labels_are_stable() {
        let labels: Vec<&'static str> =
            FULL_PIPELINE_STEPS.iter().map(|s| s.label()).collect();
        assert_eq!(
            labels,
            vec!["index", "memory-map", "flow-graph", "plan", "generate", "run"]
        );
    }

    #[test]
    fn pipeline_mode_index_only_has_single_step() {
        let labels: Vec<&'static str> = PipelineMode::IndexOnly
            .steps()
            .iter()
            .map(|s| s.label())
            .collect();
        assert_eq!(labels, vec!["index"]);
    }

    #[test]
    fn pipeline_paths_use_idx_and_pg_runs_layout() {
        let paths = PipelinePaths::new("/repo", "run-1");
        assert_eq!(paths.persist_dir, PathBuf::from("/repo/.idx"));
        assert_eq!(paths.memory_map_path, PathBuf::from("/repo/.idx/memory_map.json"));
        assert_eq!(paths.flow_graph_path, PathBuf::from("/repo/.idx/flow_graph.json"));
        assert_eq!(paths.plan_path, PathBuf::from("/repo/.pg_runs/run-1/plan.md"));
        assert_eq!(
            paths.generated_spec_path,
            PathBuf::from("/repo/.pg_runs/run-1/generated.spec.ts")
        );
    }

    #[test]
    fn index_step_builds_persist_and_memory_map_args() {
        let paths = PipelinePaths::new("/repo", "run-1");
        let execution = build_step_execution(PipelineStep::Index, &paths, "");
        let StepExecution::Spawn { args, .. } = execution else {
            panic!("expected spawned index step");
        };
        assert_eq!(
            args,
            vec![
                "index".to_string(),
                path_arg(&paths.repo),
                "--persist-dir".to_string(),
                path_arg(&paths.persist_dir),
                "--memory-map".to_string(),
                path_arg(&paths.memory_map_path),
            ]
        );
    }

    #[test]
    fn full_pipeline_steps_match_cli_contract() {
        let paths = PipelinePaths::new("/repo", "run-1");

        let flow_graph = build_step_execution(PipelineStep::FlowGraph, &paths, "");
        let StepExecution::Spawn { args: flow_args, .. } = flow_graph else {
            panic!("expected spawned flow-graph step");
        };
        assert_eq!(
            flow_args,
            vec![
                "graph".to_string(),
                "extract".to_string(),
                path_arg(&paths.repo),
                "--output".to_string(),
                path_arg(&paths.flow_graph_path),
                "--persist-dir".to_string(),
                path_arg(&paths.persist_dir),
            ]
        );

        let plan = build_step_execution(PipelineStep::Plan, &paths, "");
        let StepExecution::Spawn { args: plan_args, .. } = plan else {
            panic!("expected spawned plan step");
        };
        assert_eq!(
            plan_args,
            vec![
                "plan".to_string(),
                "--persist-dir".to_string(),
                path_arg(&paths.persist_dir),
                "--memory-map".to_string(),
                path_arg(&paths.memory_map_path),
                "--flow-graph".to_string(),
                path_arg(&paths.flow_graph_path),
                "-o".to_string(),
                path_arg(&paths.plan_path),
            ]
        );

        let generate = build_step_execution(PipelineStep::Generate, &paths, "login flow");
        let StepExecution::Spawn {
            args: generate_args, ..
        } = generate
        else {
            panic!("expected spawned generate step");
        };
        assert_eq!(
            generate_args,
            vec![
                "generate".to_string(),
                "login flow".to_string(),
                "--persist-dir".to_string(),
                path_arg(&paths.persist_dir),
                "--memory-map".to_string(),
                path_arg(&paths.memory_map_path),
                "-o".to_string(),
                path_arg(&paths.generated_spec_path),
            ]
        );

        let run = build_step_execution(PipelineStep::Run, &paths, "");
        let StepExecution::Spawn { args: run_args, .. } = run else {
            panic!("expected spawned run step");
        };
        assert_eq!(
            run_args,
            vec![
                "run".to_string(),
                path_arg(&paths.generated_spec_path),
                "--target-dir".to_string(),
                path_arg(&paths.repo),
                "--artifact-dir".to_string(),
                path_arg(&paths.run_artifact_dir),
            ]
        );
    }

    #[test]
    fn pipeline_registry_rejects_concurrent_runs() {
        let reg = PipelineRegistry::new();
        let _ = reg
            .try_start("r1".into(), "/repo".into(), PipelineMode::Full)
            .unwrap();
        match reg.try_start("r2".into(), "/repo".into(), PipelineMode::Full) {
            Err(PipelineError::Busy) => {}
            other => panic!("expected Busy, got {other:?}"),
        }
        reg.finish();
        // After finish the next start succeeds.
        let _ = reg
            .try_start("r3".into(), "/repo".into(), PipelineMode::Full)
            .unwrap();
    }

    #[test]
    fn pipeline_registry_cancel_only_when_id_matches() {
        let reg = PipelineRegistry::new();
        let _ = reg
            .try_start("r1".into(), "/repo".into(), PipelineMode::Full)
            .unwrap();
        assert!(!reg.cancel(Some("other")));
        assert!(reg.cancel(Some("r1")));
    }

    #[test]
    fn pipeline_registry_exposes_active_run_snapshot_for_repo() {
        let reg = PipelineRegistry::new();
        let _ = reg
            .try_start("r1".into(), "/repo".into(), PipelineMode::IndexOnly)
            .unwrap();
        let snapshot = reg.active_for_repo("/repo").unwrap();
        assert_eq!(snapshot.run_id, "r1");
        assert_eq!(snapshot.mode, PipelineMode::IndexOnly);
        assert!(reg.active_for_repo("/other").is_none());
    }
}
