//! Artifact discovery and read helpers (D6).
//!
//! The desktop app never re-implements memory-map / flow-graph / coverage
//! parsing: it just reads the JSON the Python CLI writes. This module is the
//! thin Rust IO layer that surfaces those artifacts to the frontend as
//! pre-parsed `serde_json::Value`s, plus a small helper for the RAG search
//! that shells out to the CLI in dry-run mode (D10).

use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::State;

use crate::pipeline::{PipelineMode, PipelineRegistry};
use crate::settings::{EffectiveSettings, Settings};

// ---------------------------------------------------------------------------
// Common helpers
// ---------------------------------------------------------------------------

fn parse_json(path: &Path) -> Result<Value, String> {
    let bytes = fs::read(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_json::from_slice(&bytes).map_err(|e| format!("parse {}: {e}", path.display()))
}

/// Try a list of candidate paths under `repo`, return the first one that
/// exists as a file.
fn first_existing(repo: &Path, candidates: &[&str]) -> Option<PathBuf> {
    for rel in candidates {
        let p = repo.join(rel);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

/// Lexicographically-largest subdirectory of `<repo>/.pg_runs/` (timestamps
/// sort correctly as strings). Returns `None` if `.pg_runs/` is missing or
/// empty.
pub(crate) fn latest_run_dir(repo: &Path) -> Option<PathBuf> {
    let runs = repo.join(".pg_runs");
    if !runs.is_dir() {
        return None;
    }
    let mut best: Option<PathBuf> = None;
    for entry in fs::read_dir(&runs).ok()?.flatten() {
        let p = entry.path();
        if !p.is_dir() {
            continue;
        }
        if best.as_ref().map(|b| p.file_name() > b.file_name()).unwrap_or(true) {
            best = Some(p);
        }
    }
    best
}

/// Path to `generated.spec.ts` inside the newest `.pg_runs/<run-id>/`
/// directory. Returns `None` if `.pg_runs/` is absent or no run contains
/// the spec file.
pub(crate) fn latest_spec_path(repo: &Path) -> Option<PathBuf> {
    // Walk all run dirs newest-first (lexicographic descending) until we find one
    // that contains the spec file.
    let runs = repo.join(".pg_runs");
    if !runs.is_dir() {
        return None;
    }
    let mut dirs: Vec<PathBuf> = fs::read_dir(&runs)
        .ok()?
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_dir())
        .collect();
    dirs.sort_by(|a, b| b.file_name().cmp(&a.file_name()));
    for dir in dirs {
        let spec = dir.join("generated.spec.ts");
        if spec.is_file() {
            return Some(spec);
        }
    }
    None
}

/// Tauri command: return the path to the most-recent generated spec file, or
/// `null` when none exists.
#[tauri::command]
pub fn read_latest_spec_path(repo: String) -> Result<Option<String>, String> {
    let repo = validate_repo(&repo)?;
    Ok(latest_spec_path(&repo).map(|p| p.to_string_lossy().into_owned()))
}

fn validate_repo(repo: &str) -> Result<PathBuf, String> {
    let p = PathBuf::from(repo);
    if !p.exists() || !p.is_dir() {
        return Err(format!("repository not found: {repo}"));
    }
    Ok(p)
}

fn first_nonempty_dir(repo: &Path, candidates: &[&str]) -> Option<PathBuf> {
    for rel in candidates {
        let p = repo.join(rel);
        if p.is_dir() && fs::read_dir(&p).ok()?.next().is_some() {
            return Some(p);
        }
    }
    None
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexStatus {
    pub has_index: bool,
    pub has_memory_map: bool,
    pub index_dir: Option<String>,
    pub memory_map_path: Option<String>,
    pub active_run_id: Option<String>,
    pub active_run_mode: Option<PipelineMode>,
}

// ---------------------------------------------------------------------------
// Memory map (task 7.1)
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn read_memory_map(repo: String) -> Result<Option<Value>, String> {
    let repo = validate_repo(&repo)?;
    let candidates = [
        ".idx/memory_map.json",
        ".playwright_god_index/memory_map.json",
        "memory_map.json",
    ];
    match first_existing(&repo, &candidates) {
        Some(path) => parse_json(&path).map(Some),
        None => Ok(None),
    }
}

#[tauri::command]
pub fn read_index_status(
    repo: String,
    registry: State<'_, PipelineRegistry>,
) -> Result<IndexStatus, String> {
    let repo = validate_repo(&repo)?;
    let index_dir = first_nonempty_dir(&repo, &[".idx", ".playwright_god_index"]);
    let memory_map_path = first_existing(
        &repo,
        &[
            ".idx/memory_map.json",
            ".playwright_god_index/memory_map.json",
            "memory_map.json",
        ],
    );
    let active = registry.active_for_repo(&repo.to_string_lossy());

    Ok(IndexStatus {
        has_index: index_dir.is_some(),
        has_memory_map: memory_map_path.is_some(),
        index_dir: index_dir.map(|p| p.to_string_lossy().into_owned()),
        memory_map_path: memory_map_path.map(|p| p.to_string_lossy().into_owned()),
        active_run_id: active.as_ref().map(|r| r.run_id.clone()),
        active_run_mode: active.map(|r| r.mode),
    })
}

// ---------------------------------------------------------------------------
// Flow graph (task 8.1)
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn read_flow_graph(repo: String) -> Result<Option<Value>, String> {
    let repo = validate_repo(&repo)?;
    // Prefer a top-level flow_graph.json (the canonical `playwright-god graph
    // extract` output), then fall back to the one embedded in the memory map.
    let candidates = [
        "flow_graph.json",
        ".idx/flow_graph.json",
        ".playwright_god_index/flow_graph.json",
    ];
    if let Some(path) = first_existing(&repo, &candidates) {
        return parse_json(&path).map(Some);
    }
    // Fallback: extract the `flow_graph` field from a memory map if present.
    if let Some(mm) = read_memory_map(repo.to_string_lossy().into_owned())? {
        if let Some(fg) = mm.get("flow_graph").cloned() {
            if !fg.is_null() {
                return Ok(Some(fg));
            }
        }
    }
    Ok(None)
}

// ---------------------------------------------------------------------------
// Coverage (task 9.1)
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn read_coverage(repo: String) -> Result<Option<Value>, String> {
    let repo = validate_repo(&repo)?;
    let Some(run) = latest_run_dir(&repo) else {
        return Ok(None);
    };
    let merged = run.join("coverage_merged.json");
    if merged.is_file() {
        return parse_json(&merged).map(Some);
    }
    Ok(None)
}

// ---------------------------------------------------------------------------
// RAG search (task 10.1)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchHit {
    pub file: String,
    pub line: Option<u32>,
    pub score: f64,
    pub content: String,
}

/// Run a RAG search against the indexed repo.
///
/// Strategy (D10):
///   1. If `python -m playwright_god._search` exists in the user's env, use
///      it (preferred — purpose-built for this).
///   2. Otherwise, fall back to `playwright-god generate --description ...
///      --dry-run --print-context --json` and parse the `context` array.
///
/// For v1 we only implement the fallback path; the dedicated `_search`
/// helper is documented as a follow-up CLI change in design.md D10.
#[tauri::command]
pub async fn rag_search<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    repo: String,
    query: String,
    top_n: Option<u32>,
) -> Result<Vec<SearchHit>, String> {
    use tokio::process::Command;

    let repo_path = validate_repo(&repo)?;
    let top = top_n.unwrap_or(10).max(1).min(50);

    let settings = Settings::load(&app).map_err(|e| e.to_string())?;
    let effective = EffectiveSettings::load_for_repo(&app, &repo_path).map_err(|e| e.to_string())?;
    let cli = settings
        .cli_path
        .clone()
        .unwrap_or_else(|| std::env::var("PLAYWRIGHT_GOD_CLI").unwrap_or_else(|_| "playwright-god".into()));

    let mut cmd = Command::new(&cli);
    cmd.arg("generate")
        .arg(&query)
        .arg("--dry-run")
        .arg("--print-context")
        .arg("--json")
        .arg("--n-context")
        .arg(top.to_string())
        .current_dir(&repo_path)
        .envs(effective.into_env());

    let output = cmd.output().await.map_err(|e| format!("spawn {cli}: {e}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "playwright-god generate --dry-run failed (exit {:?}): {}",
            output.status.code(),
            stderr.lines().take(3).collect::<Vec<_>>().join(" / ")
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    parse_search_hits(&stdout).map(|mut hits| {
        hits.truncate(top as usize);
        hits
    })
}/// Parse the `context` (or top-level `hits`) array out of a JSON dry-run
/// payload. Each entry is best-effort mapped to a [`SearchHit`].
pub fn parse_search_hits(stdout: &str) -> Result<Vec<SearchHit>, String> {
    let v: Value = serde_json::from_str(stdout.trim())
        .map_err(|e| format!("non-JSON dry-run output: {e}"))?;
    let arr = v
        .get("context")
        .or_else(|| v.get("hits"))
        .and_then(|x| x.as_array())
        .cloned()
        .unwrap_or_default();
    Ok(arr.into_iter().map(hit_from_value).collect())
}

fn hit_from_value(v: Value) -> SearchHit {
    let file = v
        .get("file")
        .or_else(|| v.get("path"))
        .or_else(|| v.get("source"))
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .to_string();
    let line = v
        .get("line")
        .or_else(|| v.get("start_line"))
        .and_then(|x| x.as_u64())
        .map(|n| n as u32);
    let score = v
        .get("score")
        .or_else(|| v.get("distance"))
        .and_then(|x| x.as_f64())
        .unwrap_or(0.0);
    let content = v
        .get("content")
        .or_else(|| v.get("text"))
        .or_else(|| v.get("chunk"))
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .to_string();
    SearchHit { file, line, score, content }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_search_hits_reads_context_array() {
        let stdout = r#"{
            "context": [
                {"file": "src/a.py", "line": 10, "score": 0.81, "content": "def foo():"},
                {"path": "src/b.ts", "start_line": 3, "distance": 0.42, "text": "export"}
            ]
        }"#;
        let hits = parse_search_hits(stdout).unwrap();
        assert_eq!(hits.len(), 2);
        assert_eq!(hits[0].file, "src/a.py");
        assert_eq!(hits[0].line, Some(10));
        assert!((hits[0].score - 0.81).abs() < 1e-6);
        assert_eq!(hits[1].file, "src/b.ts");
        assert_eq!(hits[1].line, Some(3));
    }

    #[test]
    fn parse_search_hits_empty_when_no_context() {
        let hits = parse_search_hits(r#"{"foo": "bar"}"#).unwrap();
        assert!(hits.is_empty());
    }

    #[test]
    fn parse_search_hits_errors_on_non_json() {
        assert!(parse_search_hits("not json").is_err());
    }

    #[test]
    fn first_existing_returns_first_match() {
        let tmp = tempfile::tempdir().unwrap();
        let repo = tmp.path();
        std::fs::create_dir_all(repo.join(".idx")).unwrap();
        std::fs::write(repo.join(".idx/memory_map.json"), b"{}").unwrap();
        let found = first_existing(repo, &[".idx/memory_map.json", "memory_map.json"]);
        assert_eq!(found, Some(repo.join(".idx/memory_map.json")));
    }

    #[test]
    fn first_nonempty_dir_returns_first_populated_candidate() {
        let tmp = tempfile::tempdir().unwrap();
        let repo = tmp.path();
        std::fs::create_dir_all(repo.join(".idx")).unwrap();
        std::fs::create_dir_all(repo.join(".playwright_god_index")).unwrap();
        std::fs::write(repo.join(".playwright_god_index/chroma.sqlite3"), b"").unwrap();
        let found = first_nonempty_dir(repo, &[".idx", ".playwright_god_index"]);
        assert_eq!(found, Some(repo.join(".playwright_god_index")));
    }

    #[test]
    fn first_nonempty_dir_ignores_empty_directories() {
        let tmp = tempfile::tempdir().unwrap();
        let repo = tmp.path();
        std::fs::create_dir_all(repo.join(".idx")).unwrap();
        assert!(first_nonempty_dir(repo, &[".idx"]).is_none());
    }

    #[test]
    fn latest_run_dir_picks_lexicographically_largest() {
        let tmp = tempfile::tempdir().unwrap();
        let repo = tmp.path();
        std::fs::create_dir_all(repo.join(".pg_runs/2025-01-01T00-00-00")).unwrap();
        std::fs::create_dir_all(repo.join(".pg_runs/2026-04-22T12-00-00")).unwrap();
        std::fs::create_dir_all(repo.join(".pg_runs/2025-12-31T23-59-59")).unwrap();
        let latest = latest_run_dir(repo).unwrap();
        assert!(latest.ends_with("2026-04-22T12-00-00"));
    }
}
