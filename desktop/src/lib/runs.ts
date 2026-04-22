import { Channel } from "@tauri-apps/api/core";
import { invokeCommand, inTauri } from "@/lib/tauri";

export interface RunSummary {
  run_id: string;
  timestamp: string;
  run_dir: string;
  status: string;
  duration_ms: number;
  tests_total: number;
  tests_passed: number;
  tests_failed: number;
  eval_status?: string | null;
  new_nodes: number;
  new_journeys: number;
  new_routes: number;
  coverage_percent?: number | null;
  has_report: boolean;
  has_evaluation: boolean;
  has_coverage: boolean;
  prompt_count: number;
}

export interface PromptPreview {
  prompt: string;
  raw?: unknown;
}

export type CodegenEvent =
  | {
      type: "prompt";
      run_id: string;
      seq: number;
      filename: string;
      body: unknown;
    }
  | { type: "stdout-line"; line: string }
  | { type: "tick" }
  | { type: "stopped" };

export async function listRuns(repo: string): Promise<RunSummary[]> {
  return invokeCommand<RunSummary[]>("list_runs", { repo });
}

export async function inspectRepo(repo: string): Promise<unknown> {
  return invokeCommand<unknown>("inspect_repo", { repo });
}

export async function discoverRepo(repo: string): Promise<unknown> {
  return invokeCommand<unknown>("discover_repo", { repo });
}

export async function previewPrompt(
  repo: string,
  description: string,
): Promise<PromptPreview> {
  return invokeCommand<PromptPreview>("preview_prompt", {
    repo,
    description,
  });
}

export function tailCodegen(
  repo: string,
  runId: string,
  onEvent: (event: CodegenEvent) => void,
): { stop: () => void } {
  if (!inTauri()) {
    return { stop: () => onEvent({ type: "stopped" }) };
  }

  let active = true;
  let stopped = false;
  const emitStopped = () => {
    if (stopped) return;
    stopped = true;
    onEvent({ type: "stopped" });
  };

  const channel = new Channel<CodegenEvent>();
  channel.onmessage = (event) => {
    if (!active) return;
    onEvent(event);
  };

  void invokeCommand<void>("tail_codegen", {
    repo,
    runId,
    onEvent: channel,
  }).catch(() => {
    if (active) emitStopped();
  });

  return {
    stop: () => {
      active = false;
      channel.onmessage = () => {};
      emitStopped();
    },
  };
}
