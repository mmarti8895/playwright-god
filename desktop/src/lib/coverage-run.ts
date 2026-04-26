import { Channel } from "@tauri-apps/api/core";
import { invokeCommand, inTauri } from "@/lib/tauri";

// ---------------------------------------------------------------------------
// Event types (mirrors coverage_run.rs CoverageEvent)
// ---------------------------------------------------------------------------

export type LogStream = "stdout" | "stderr";

export type CoverageEvent =
  | { type: "run-started"; spec_path: string }
  | { type: "log-line"; stream: LogStream; line: string }
  | { type: "finished"; exit_code: number }
  | { type: "cancelled" }
  | { type: "failed"; message: string };

// ---------------------------------------------------------------------------
// IPC wrappers
// ---------------------------------------------------------------------------

/**
 * Start a coverage run for the given repository.
 * Resolves the most-recent generated.spec.ts from .pg_runs/ server-side and
 * invokes `playwright-god run <spec> --coverage`.
 *
 * @param repo       Absolute path to the target repository.
 * @param onEvent    Callback invoked for each streamed CoverageEvent.
 */
export async function runCoverage(
  repo: string,
  onEvent: (event: CoverageEvent) => void,
): Promise<void> {
  if (!inTauri()) {
    throw new Error("runCoverage is only available inside Tauri.");
  }
  const channel = new Channel<CoverageEvent>();
  channel.onmessage = onEvent;
  return invokeCommand<void>("run_coverage", { repo, onEvent: channel });
}

/** Cancel the active coverage run. Returns true if a run was cancelled. */
export async function cancelCoverage(): Promise<boolean> {
  if (!inTauri()) return false;
  return invokeCommand<boolean>("cancel_coverage");
}

/**
 * Return the path to the most-recent generated.spec.ts, or null when none
 * exists in the repository's .pg_runs/ directory.
 */
export async function readLatestSpecPath(repo: string): Promise<string | null> {
  if (!inTauri()) return null;
  return invokeCommand<string | null>("read_latest_spec_path", { repo });
}
