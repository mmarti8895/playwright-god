//! Audit-log discovery: walks `<repo>/.pg_runs/<ts>/` directories and
//! synthesizes a per-run summary the desktop UI can render as a sortable,
//! filterable table.
//!
//! Each run directory may contain:
//!   - `report.json`                     (Playwright JSON reporter)
//!   - `generated_spec_evaluation.json`  (LLM-generated spec evaluation)
//!   - `coverage_merged.json`            (merged frontend/backend coverage)
//!   - `prompts/*.json`                  (LLM transcripts)
//!   - `desktop_log.txt`                 (output-pane spill, when written)
//!
//! All fields are best-effort: missing files/keys downgrade the row gracefully.

use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunSummary {
    pub run_id: String,
    pub timestamp: String,
    pub run_dir: String,
    /// Playwright run status: "passed" | "failed" | "interrupted" | "unknown".
    pub status: String,
    pub duration_ms: u64,
    pub tests_total: u32,
    pub tests_passed: u32,
    pub tests_failed: u32,
    /// Eval status from `generated_spec_evaluation.json`, if present.
    pub eval_status: Option<String>,
    pub new_nodes: u32,
    pub new_journeys: u32,
    pub new_routes: u32,
    pub coverage_percent: Option<f64>,
    pub has_report: bool,
    pub has_evaluation: bool,
    pub has_coverage: bool,
    pub prompt_count: u32,
}

#[tauri::command]
pub fn list_runs(repo: String) -> Result<Vec<RunSummary>, String> {
    let p = PathBuf::from(&repo);
    if !p.is_dir() {
        return Err(format!("repository not found: {repo}"));
    }
    let runs = p.join(".pg_runs");
    if !runs.is_dir() {
        return Ok(vec![]);
    }
    let mut out: Vec<RunSummary> = Vec::new();
    for entry in fs::read_dir(&runs).map_err(|e| e.to_string())?.flatten() {
        let dir = entry.path();
        if !dir.is_dir() {
            continue;
        }
        let id = entry.file_name().to_string_lossy().into_owned();
        out.push(summarize_run(&id, &dir));
    }
    // Newest first (timestamp prefixes sort lexicographically).
    out.sort_by(|a, b| b.run_id.cmp(&a.run_id));
    Ok(out)
}

fn summarize_run(run_id: &str, dir: &Path) -> RunSummary {
    let report_path = dir.join("report.json");
    let eval_path = dir.join("generated_spec_evaluation.json");
    let coverage_path = dir.join("coverage_merged.json");
    let prompts_dir = dir.join("prompts");

    let mut s = RunSummary {
        run_id: run_id.to_string(),
        timestamp: derive_timestamp(run_id),
        run_dir: dir.to_string_lossy().into_owned(),
        status: "unknown".into(),
        duration_ms: 0,
        tests_total: 0,
        tests_passed: 0,
        tests_failed: 0,
        eval_status: None,
        new_nodes: 0,
        new_journeys: 0,
        new_routes: 0,
        coverage_percent: None,
        has_report: report_path.is_file(),
        has_evaluation: eval_path.is_file(),
        has_coverage: coverage_path.is_file(),
        prompt_count: 0,
    };

    if s.has_report {
        if let Ok(v) = read_json(&report_path) {
            apply_report(&mut s, &v);
        }
    }
    if s.has_evaluation {
        if let Ok(v) = read_json(&eval_path) {
            apply_evaluation(&mut s, &v);
        }
    }
    if s.has_coverage {
        if let Ok(v) = read_json(&coverage_path) {
            apply_coverage(&mut s, &v);
        }
    }
    if prompts_dir.is_dir() {
        if let Ok(rd) = fs::read_dir(&prompts_dir) {
            s.prompt_count = rd
                .flatten()
                .filter(|e| e.path().extension().and_then(|x| x.to_str()) == Some("json"))
                .count() as u32;
        }
    }
    s
}

fn read_json(path: &Path) -> Result<Value, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    serde_json::from_slice(&bytes).map_err(|e| e.to_string())
}

fn derive_timestamp(run_id: &str) -> String {
    // Playwright runner uses `%Y%m%dT%H%M%SZ`; pretty-format if it matches.
    if run_id.len() == 16 && run_id.ends_with('Z') {
        let y = &run_id[0..4];
        let mo = &run_id[4..6];
        let d = &run_id[6..8];
        let h = &run_id[9..11];
        let mi = &run_id[11..13];
        let s = &run_id[13..15];
        return format!("{y}-{mo}-{d}T{h}:{mi}:{s}Z");
    }
    run_id.to_string()
}

fn apply_report(s: &mut RunSummary, v: &Value) {
    // Playwright JSON reporter exposes top-level `stats` and `suites`.
    if let Some(stats) = v.get("stats") {
        if let Some(d) = stats.get("duration").and_then(|x| x.as_u64()) {
            s.duration_ms = d;
        }
        let exp = stats.get("expected").and_then(|x| x.as_u64()).unwrap_or(0);
        let unx = stats.get("unexpected").and_then(|x| x.as_u64()).unwrap_or(0);
        let flaky = stats.get("flaky").and_then(|x| x.as_u64()).unwrap_or(0);
        let skipped = stats.get("skipped").and_then(|x| x.as_u64()).unwrap_or(0);
        s.tests_total = (exp + unx + flaky + skipped) as u32;
        s.tests_passed = exp as u32;
        s.tests_failed = unx as u32;
        s.status = if unx > 0 { "failed".into() } else { "passed".into() };
    }
    if let Some(status) = v.get("status").and_then(|x| x.as_str()) {
        s.status = status.to_string();
    }
}

fn apply_evaluation(s: &mut RunSummary, v: &Value) {
    s.eval_status = v.get("status").and_then(|x| x.as_str()).map(String::from);
    s.new_nodes = v
        .get("newly_covered_nodes")
        .and_then(|x| x.as_array())
        .map(|a| a.len() as u32)
        .unwrap_or(0);
    s.new_journeys = v
        .get("newly_covered_journeys")
        .and_then(|x| x.as_array())
        .map(|a| a.len() as u32)
        .unwrap_or(0);
    s.new_routes = v
        .get("route_delta")
        .and_then(|x| x.get("newly_covered"))
        .and_then(|x| x.as_array())
        .map(|a| a.len() as u32)
        .unwrap_or(0);
}

fn apply_coverage(s: &mut RunSummary, v: &Value) {
    s.coverage_percent = v
        .get("totals")
        .and_then(|x| x.get("percent"))
        .and_then(|x| x.as_f64());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn derive_timestamp_pretty_prints_runner_format() {
        assert_eq!(derive_timestamp("20260422T120000Z"), "2026-04-22T12:00:00Z");
        assert_eq!(derive_timestamp("custom-id"), "custom-id");
    }

    #[test]
    fn apply_report_extracts_stats() {
        let mut s = sample();
        let v: Value = serde_json::from_str(
            r#"{"stats":{"duration":1234,"expected":3,"unexpected":1,"flaky":0,"skipped":2}}"#,
        )
        .unwrap();
        apply_report(&mut s, &v);
        assert_eq!(s.duration_ms, 1234);
        assert_eq!(s.tests_total, 6);
        assert_eq!(s.tests_passed, 3);
        assert_eq!(s.tests_failed, 1);
        assert_eq!(s.status, "failed");
    }

    #[test]
    fn apply_evaluation_counts_arrays() {
        let mut s = sample();
        let v: Value = serde_json::from_str(
            r#"{"status":"generated_green","newly_covered_nodes":["a","b"],
                "newly_covered_journeys":["x"],
                "route_delta":{"newly_covered":["r1","r2","r3"]}}"#,
        )
        .unwrap();
        apply_evaluation(&mut s, &v);
        assert_eq!(s.eval_status.as_deref(), Some("generated_green"));
        assert_eq!(s.new_nodes, 2);
        assert_eq!(s.new_journeys, 1);
        assert_eq!(s.new_routes, 3);
    }

    #[test]
    fn list_runs_sorts_newest_first_and_counts_artifacts() {
        let tmp = tempfile::tempdir().unwrap();
        let repo = tmp.path();
        let runs = repo.join(".pg_runs");
        for id in ["20260101T000000Z", "20260422T120000Z", "20260315T060000Z"] {
            let d = runs.join(id);
            fs::create_dir_all(&d).unwrap();
            fs::write(d.join("report.json"), br#"{"stats":{"duration":1,"expected":1,"unexpected":0,"flaky":0,"skipped":0}}"#).unwrap();
        }
        let prompts = runs.join("20260422T120000Z/prompts");
        fs::create_dir_all(&prompts).unwrap();
        fs::write(prompts.join("a.json"), b"{}").unwrap();
        fs::write(prompts.join("b.json"), b"{}").unwrap();

        let out = list_runs(repo.to_string_lossy().into_owned()).unwrap();
        assert_eq!(out.len(), 3);
        assert_eq!(out[0].run_id, "20260422T120000Z");
        assert_eq!(out[0].prompt_count, 2);
        assert!(out[0].has_report);
        assert_eq!(out[2].run_id, "20260101T000000Z");
    }

    fn sample() -> RunSummary {
        RunSummary {
            run_id: "x".into(),
            timestamp: "x".into(),
            run_dir: "x".into(),
            status: "unknown".into(),
            duration_ms: 0,
            tests_total: 0,
            tests_passed: 0,
            tests_failed: 0,
            eval_status: None,
            new_nodes: 0,
            new_journeys: 0,
            new_routes: 0,
            coverage_percent: None,
            has_report: false,
            has_evaluation: false,
            has_coverage: false,
            prompt_count: 0,
        }
    }
}
