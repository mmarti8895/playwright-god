import type { PipelineEvent, PipelineMode } from "@/lib/pipeline";
import { errorMessage } from "@/lib/tauri";
import { startPipeline } from "@/lib/pipeline";
import { useOutputStore } from "@/state/output";
import { usePipelineStore } from "@/state/pipeline";
import { useUIStore } from "@/state/ui";

function applyPipelineEvent(event: PipelineEvent) {
  const append = useOutputStore.getState().append;
  usePipelineStore.getState().apply(event);

  switch (event.type) {
    case "run-started":
      append("info", `--- Pipeline ${event.run_id} started ---`);
      break;
    case "started":
      append("info", `> ${event.step}`);
      break;
    case "stdout-line":
      append("stdout", `[${event.step}] ${event.line}`);
      break;
    case "stderr-line":
      append("stderr", `[${event.step}] ${event.line}`);
      break;
    case "finished":
      append("info", `OK ${event.step}`);
      break;
    case "failed":
      append("stderr", `FAIL ${event.step}: ${event.message}`);
      break;
    case "cancelled":
      append("info", "Pipeline cancelled");
      break;
    case "run-finished":
      append("info", "Pipeline finished");
      useUIStore.getState().bumpArtifactsVersion();
      break;
  }
}

export async function runManagedPipeline(
  repo: string,
  mode: PipelineMode = "full",
): Promise<string | null> {
  try {
    return await startPipeline(repo, applyPipelineEvent, mode);
  } catch (error) {
    const label = mode === "index-only" ? "index run" : "pipeline";
    useOutputStore
      .getState()
      .append("stderr", `Failed to start ${label}: ${errorMessage(error)}`);
    return null;
  }
}

export async function runIndex(repo: string): Promise<string | null> {
  return runManagedPipeline(repo, "index-only");
}
