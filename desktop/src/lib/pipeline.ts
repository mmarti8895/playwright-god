import { Channel } from "@tauri-apps/api/core";
import { invokeCommand, inTauri } from "@/lib/tauri";

export type PipelineStep =
  | "index"
  | "memory-map"
  | "flow-graph"
  | "plan"
  | "generate"
  | "run";

export type PipelineMode = "full" | "index-only";

export const PIPELINE_STEPS: PipelineStep[] = [
  "index",
  "memory-map",
  "flow-graph",
  "plan",
  "generate",
  "run",
];

export type PipelineEvent =
  | { type: "run-started"; run_id: string; steps: PipelineStep[] }
  | { type: "started"; step: PipelineStep }
  | { type: "stdout-line"; step: PipelineStep; line: string }
  | { type: "stderr-line"; step: PipelineStep; line: string }
  | { type: "progress"; step: PipelineStep; fraction: number }
  | { type: "finished"; step: PipelineStep; exit_code: number }
  | { type: "cancelled"; run_id: string }
  | { type: "failed"; step: PipelineStep; exit_code: number; message: string }
  | { type: "run-finished"; run_id: string };

export async function startPipeline(
  repo: string,
  onEvent: (event: PipelineEvent) => void,
  mode: PipelineMode = "full",
  description?: string,
): Promise<string> {
  if (!inTauri()) {
    throw new Error("Desktop pipeline commands are only available inside Tauri.");
  }
  const channel = new Channel<PipelineEvent>();
  channel.onmessage = onEvent;
  return invokeCommand<string>("run_pipeline", {
    repo,
    mode,
    description: description ?? null,
    onEvent: channel,
  });
}

export async function cancelPipeline(runId?: string): Promise<boolean> {
  if (!inTauri()) return false;
  return invokeCommand<boolean>("cancel_pipeline", {
    runId: runId ?? null,
  });
}
