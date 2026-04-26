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

use crate::settings::{EffectiveSettings, SettingValueSource, Settings};

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
    playwright_target_dir: Option<&str>,
    retry_max: u32,
    retry_delay_s: f64,
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
                "--retry-max".into(),
                retry_max.to_string(),
                "--retry-delay".into(),
                retry_delay_s.to_string(),
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
                "--retry-max".into(),
                retry_max.to_string(),
                "--retry-delay".into(),
                retry_delay_s.to_string(),
            ],
        },
        PipelineStep::Run => StepExecution::Spawn {
            cwd: paths.repo.clone(),
            args: vec![
                "run".into(),
                generated_spec_path,
                "--target-dir".into(),
                playwright_target_dir.unwrap_or(repo.as_str()).to_string(),
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
    Diagnostic {
        step: &'static str,
        category: String,
        message: String,
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
    /// Emitted when an LLM call is retried after a transient error.
    RetryAttempt {
        step: String,
        attempt: u32,
        max: u32,
        delay_s: f64,
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

    /// Returns `true` when a pipeline run is currently active for the given
    /// repository. Used by `coverage_run` to prevent overlapping runs.
    pub fn is_busy_for_repo(&self, repo: &str) -> bool {
        self.active_for_repo(repo).is_some()
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
    let effective = EffectiveSettings::load_for_repo(&app, &pb)
        .or_else(|_| EffectiveSettings::load(&app))
        .unwrap_or_default();
    let settings = Settings::load(&app).unwrap_or_default();
    let cli_path = settings
        .cli_path
        .clone()
        .or_else(|| std::env::var("PLAYWRIGHT_GOD_CLI").ok())
        .unwrap_or_else(|| "playwright-god".into());
    let playwright_target_dir = settings.playwright_target_dir.clone();
    let retry_max = settings.llm_retry_max;
    let retry_delay_s = settings.llm_retry_delay_s;

    // Drop the State guard before spawning so the lock isn't held across
    // .await points.
    drop(registry_arc);

    tauri::async_runtime::spawn(async move {
        let result = run_pipeline_inner(
            &app_clone,
            &repo_clone,
            &run_id_clone,
            &cli_path,
            effective,
            mode,
            description.clone(),
            playwright_target_dir.as_deref(),
            retry_max,
            retry_delay_s,
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
    effective: EffectiveSettings,
    mode: PipelineMode,
    description: Option<String>,
    playwright_target_dir: Option<&str>,
    retry_max: u32,
    retry_delay_s: f64,
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

        if let Err(message) = emit_llm_preflight(step, &effective, &channel) {
            let _ = channel.send(PipelineEvent::Failed {
                step: step.label(),
                exit_code: -2,
                message,
            });
            return Ok(());
        }

        let execution = build_step_execution(step, &paths, &description, playwright_target_dir, retry_max, retry_delay_s);
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
        cmd.envs(effective.clone().into_env());
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
        let mut stderr_tail: Vec<String> = Vec::new();

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
                                if let Some(ev) = parse_retry_attempt(&l, step_label) {
                                    let _ = channel.send(ev);
                                }
                                push_stderr_tail(&mut stderr_tail, &l);
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
                        if let Some(ev) = parse_retry_attempt(&l, step_label) {
                            let _ = channel.send(ev);
                        }
                        push_stderr_tail(&mut stderr_tail, &l);
                        forward_line(&channel, &mut forwarded, &mut spill, &spill_path, step_label, true, l).await;
                    }
                }
            }
        };

        if exit_code != 0 {
            if let Some((category, message)) = classify_llm_failure(step, &effective, &stderr_tail, exit_code) {
                let _ = channel.send(PipelineEvent::Diagnostic {
                    step: step.label(),
                    category,
                    message,
                });
            }
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

fn is_llm_step(step: PipelineStep) -> bool {
    matches!(step, PipelineStep::Plan | PipelineStep::Generate)
}

fn source_label(source: SettingValueSource) -> &'static str {
    match source {
        SettingValueSource::Settings => "settings",
        SettingValueSource::RepoDotenv => "repo-dotenv",
        SettingValueSource::ProcessEnv => "process-env",
        SettingValueSource::Missing => "missing",
    }
}

fn required_provider_key_env(provider: &str) -> Option<&'static str> {
    match provider {
        "openai" => Some("OPENAI_API_KEY"),
        "anthropic" => Some("ANTHROPIC_API_KEY"),
        "gemini" => Some("GOOGLE_API_KEY"),
        _ => None,
    }
}

fn selected_key_present(effective: &EffectiveSettings) -> bool {
    match effective.meta.selected_api_key_env.as_deref() {
        Some("OPENAI_API_KEY") => effective.openai_api_key.is_some(),
        Some("ANTHROPIC_API_KEY") => effective.anthropic_api_key.is_some(),
        Some("GOOGLE_API_KEY") => effective.google_api_key.is_some(),
        _ => false,
    }
}

fn emit_llm_preflight(
    step: PipelineStep,
    effective: &EffectiveSettings,
    channel: &Channel<PipelineEvent>,
) -> Result<(), String> {
    if !is_llm_step(step) {
        return Ok(());
    }

    let provider = effective
        .provider
        .clone()
        .unwrap_or_else(|| "openai".to_string());
    let model = effective.model.clone().unwrap_or_else(|| "<default>".to_string());
    let key_source = source_label(effective.meta.selected_api_key_source);
    let provider_source = source_label(effective.meta.provider_source);
    let model_source = source_label(effective.meta.model_source);
    let key_env = effective
        .meta
        .selected_api_key_env
        .clone()
        .unwrap_or_else(|| "<none>".to_string());

    let _ = channel.send(PipelineEvent::Diagnostic {
        step: step.label(),
        category: "preflight".to_string(),
        message: format!(
            "provider={provider} ({provider_source}), model={model} ({model_source}), key={key_env} ({key_source})"
        ),
    });
    ensure_provider_key_present(&provider, effective)
}

fn ensure_provider_key_present(provider: &str, effective: &EffectiveSettings) -> Result<(), String> {
    if let Some(required_env) = required_provider_key_env(provider) {
        if !selected_key_present(effective) {
            return Err(format!(
                "Missing required {required_env} for provider '{provider}'. Save the key in Settings, add it to <repo>/.env, or set it in the process environment."
            ));
        }
    }
    Ok(())
}

fn push_stderr_tail(stderr_tail: &mut Vec<String>, line: &str) {
    const MAX_TAIL: usize = 25;
    stderr_tail.push(line.to_string());
    if stderr_tail.len() > MAX_TAIL {
        let drop_n = stderr_tail.len() - MAX_TAIL;
        stderr_tail.drain(0..drop_n);
    }
}

fn classify_llm_failure(
    step: PipelineStep,
    effective: &EffectiveSettings,
    stderr_tail: &[String],
    exit_code: i32,
) -> Option<(String, String)> {
    if !is_llm_step(step) {
        return None;
    }

    let provider = effective
        .provider
        .as_deref()
        .unwrap_or("openai")
        .to_ascii_lowercase();
    let merged = stderr_tail
        .iter()
        .map(|line| line.to_ascii_lowercase())
        .collect::<Vec<_>>()
        .join("\n");

    if matches_any(&merged, &["invalid api key", "authentication", "unauthorized", "permission", "401"]) {
        return Some((
            "upstream-auth".to_string(),
            format!(
                "{provider} authentication failed during {} (exit {exit_code}). Verify API key validity and account permissions.",
                step.label()
            ),
        ));
    }

    if matches_any(&merged, &["quota", "rate limit", "429", "insufficient_quota", "billing"]) {
        return Some((
            "upstream-quota".to_string(),
            format!(
                "{provider} quota or rate limit error during {} (exit {exit_code}). Check billing and retry window.",
                step.label()
            ),
        ));
    }

    if matches_any(&merged, &["timeout", "timed out", "network", "connection", "dns", "503", "502", "504"]) {
        return Some((
            "upstream-network".to_string(),
            format!(
                "{provider} network/API connectivity issue during {} (exit {exit_code}). Check network/VPN/proxy and provider status.",
                step.label()
            ),
        ));
    }

    Some((
        "upstream-api".to_string(),
        format!(
            "{} failed with provider '{provider}' (exit {exit_code}). Review recent stderr output for provider response details.",
            step.label()
        ),
    ))
}

fn matches_any(haystack: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| haystack.contains(needle))
}

/// Parse a `[pg:retry] attempt=N/M delay=S.S` stderr line into a
/// [`PipelineEvent::RetryAttempt`]. Returns `None` for any other line format.
fn parse_retry_attempt(line: &str, step: &str) -> Option<PipelineEvent> {
    let rest = line.strip_prefix("[pg:retry] attempt=")?;
    let (attempt_part, delay_part) = rest.split_once(" delay=")?;
    let (attempt_str, max_str) = attempt_part.split_once('/')?;
    let attempt: u32 = attempt_str.trim().parse().ok()?;
    let max: u32 = max_str.trim().parse().ok()?;
    let delay_s: f64 = delay_part.trim().parse().ok()?;
    Some(PipelineEvent::RetryAttempt {
        step: step.to_string(),
        attempt,
        max,
        delay_s,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::{EffectiveSettingsMeta, SettingValueSource};

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
    fn pipeline_event_diagnostic_serializes() {
        let ev = PipelineEvent::Diagnostic {
            step: "plan",
            category: "preflight".to_string(),
            message: "provider=openai".to_string(),
        };
        let v: serde_json::Value = serde_json::to_value(ev).unwrap();
        assert_eq!(v["type"], "diagnostic");
        assert_eq!(v["step"], "plan");
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
        let execution = build_step_execution(PipelineStep::Index, &paths, "", None, 3, 2.0);
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

        let flow_graph = build_step_execution(PipelineStep::FlowGraph, &paths, "", None, 3, 2.0);
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

        let plan = build_step_execution(PipelineStep::Plan, &paths, "", None, 3, 2.0);
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
                "--retry-max".to_string(),
                "3".to_string(),
                "--retry-delay".to_string(),
                "2".to_string(),
            ]
        );

        let generate = build_step_execution(PipelineStep::Generate, &paths, "login flow", None, 3, 2.0);
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
                "--retry-max".to_string(),
                "3".to_string(),
                "--retry-delay".to_string(),
                "2".to_string(),
            ]
        );

        let run = build_step_execution(PipelineStep::Run, &paths, "", None, 3, 2.0);
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

        // With an explicit playwright_target_dir override.
        let run_override =
            build_step_execution(PipelineStep::Run, &paths, "", Some("/repo/frontend"), 3, 2.0);
        let StepExecution::Spawn {
            args: run_override_args,
            ..
        } = run_override
        else {
            panic!("expected spawned run step");
        };
        assert_eq!(
            run_override_args[run_override_args.iter().position(|a| a == "--target-dir").unwrap()
                + 1],
            "/repo/frontend"
        );
    }

    #[test]
    fn retry_flags_appear_in_plan_and_generate_but_not_index() {
        let paths = PipelinePaths::new("/repo", "run-1");

        let index_exec = build_step_execution(PipelineStep::Index, &paths, "", None, 5, 1.5);
        let StepExecution::Spawn { args: index_args, .. } = index_exec else {
            panic!("expected spawn");
        };
        assert!(!index_args.contains(&"--retry-max".to_string()));
        assert!(!index_args.contains(&"--retry-delay".to_string()));

        let plan_exec = build_step_execution(PipelineStep::Plan, &paths, "", None, 5, 1.5);
        let StepExecution::Spawn { args: plan_args, .. } = plan_exec else {
            panic!("expected spawn");
        };
        let rm_pos = plan_args.iter().position(|a| a == "--retry-max").unwrap();
        assert_eq!(plan_args[rm_pos + 1], "5");
        let rd_pos = plan_args.iter().position(|a| a == "--retry-delay").unwrap();
        assert_eq!(plan_args[rd_pos + 1], "1.5");

        let gen_exec = build_step_execution(PipelineStep::Generate, &paths, "x", None, 5, 1.5);
        let StepExecution::Spawn { args: gen_args, .. } = gen_exec else {
            panic!("expected spawn");
        };
        let rm_pos = gen_args.iter().position(|a| a == "--retry-max").unwrap();
        assert_eq!(gen_args[rm_pos + 1], "5");
    }

    #[test]
    fn parse_retry_attempt_parses_valid_line() {
        let ev = parse_retry_attempt("[pg:retry] attempt=2/3 delay=4.0", "plan").unwrap();
        let PipelineEvent::RetryAttempt { step, attempt, max, delay_s } = ev else {
            panic!("wrong variant");
        };
        assert_eq!(step, "plan");
        assert_eq!(attempt, 2);
        assert_eq!(max, 3);
        assert!((delay_s - 4.0).abs() < 1e-6);
    }

    #[test]
    fn parse_retry_attempt_returns_none_for_other_lines() {
        assert!(parse_retry_attempt("some other line", "plan").is_none());
        assert!(parse_retry_attempt("[pg:retry] exhausted attempts=3", "plan").is_none());
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

    #[test]
    fn preflight_fails_when_openai_key_missing() {
        let effective = EffectiveSettings {
            provider: Some("openai".into()),
            model: Some("gpt-5.4".into()),
            meta: EffectiveSettingsMeta {
                provider_source: SettingValueSource::Settings,
                model_source: SettingValueSource::Settings,
                openai_api_key_source: SettingValueSource::Missing,
                anthropic_api_key_source: SettingValueSource::Missing,
                google_api_key_source: SettingValueSource::Missing,
                selected_api_key_env: Some("OPENAI_API_KEY".into()),
                selected_api_key_source: SettingValueSource::Missing,
            },
            ..Default::default()
        };
        let result = ensure_provider_key_present("openai", &effective);
        assert!(result.is_err());
    }

    #[test]
    fn classify_llm_failure_detects_auth_errors() {
        let effective = EffectiveSettings {
            provider: Some("openai".into()),
            meta: EffectiveSettingsMeta {
                selected_api_key_env: Some("OPENAI_API_KEY".into()),
                selected_api_key_source: SettingValueSource::Settings,
                ..Default::default()
            },
            ..Default::default()
        };
        let failure = classify_llm_failure(
            PipelineStep::Plan,
            &effective,
            &["Authentication failed: invalid api key".into()],
            1,
        )
        .unwrap();
        assert_eq!(failure.0, "upstream-auth");
    }
}
