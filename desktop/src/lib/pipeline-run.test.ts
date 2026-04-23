import { beforeEach, describe, expect, it, vi } from "vitest";
import { useOutputStore } from "@/state/output";
import { usePipelineStore } from "@/state/pipeline";
import { useUIStore } from "@/state/ui";

vi.mock("@/lib/pipeline", async () => {
  const actual = await vi.importActual<typeof import("@/lib/pipeline")>(
    "@/lib/pipeline",
  );
  return {
    ...actual,
    startPipeline: vi.fn(),
  };
});

import { startPipeline } from "@/lib/pipeline";
import { runIndex, runManagedPipeline } from "@/lib/pipeline-run";

describe("runManagedPipeline", () => {
  beforeEach(() => {
    vi.mocked(startPipeline).mockReset();
    useOutputStore.setState({ lines: [] });
    usePipelineStore.getState().reset();
    useUIStore.setState({ artifactsVersion: 0 });
  });

  it("applies streamed events and bumps artifact version on success", async () => {
    vi.mocked(startPipeline).mockImplementation(async (_repo, onEvent) => {
      onEvent({ type: "run-started", run_id: "run-1", steps: ["index"] });
      onEvent({ type: "started", step: "index" });
      onEvent({ type: "stdout-line", step: "index", line: "indexing…" });
      onEvent({ type: "finished", step: "index", exit_code: 0 });
      onEvent({ type: "run-finished", run_id: "run-1" });
      return "run-1";
    });

    await expect(runManagedPipeline("/repo", "index-only")).resolves.toBe("run-1");
    expect(usePipelineStore.getState().status).toBe("succeeded");
    expect(useUIStore.getState().artifactsVersion).toBe(1);
    expect(useOutputStore.getState().lines.map((line) => line.text)).toEqual(
      expect.arrayContaining([
        "--- Pipeline run-1 started ---",
        "> index",
        "[index] indexing…",
        "OK index",
        "Pipeline finished",
      ]),
    );
  });

  it("logs startup failures and returns null", async () => {
    vi.mocked(startPipeline).mockRejectedValue(new Error("busy"));

    await expect(runManagedPipeline("/repo", "index-only")).resolves.toBeNull();
    expect(useOutputStore.getState().lines.at(-1)?.text).toBe(
      "Failed to start index run: busy",
    );
  });

  it("records stderr and failed events for full pipeline runs", async () => {
    vi.mocked(startPipeline).mockImplementation(async (_repo, onEvent) => {
      onEvent({ type: "run-started", run_id: "run-2", steps: ["generate", "run"] });
      onEvent({ type: "started", step: "generate" });
      onEvent({ type: "stderr-line", step: "generate", line: "broken prompt" });
      onEvent({ type: "failed", step: "generate", exit_code: 1, message: "exploded" });
      return "run-2";
    });

    await expect(runManagedPipeline("/repo", "full", "login flow")).resolves.toBe("run-2");
    expect(usePipelineStore.getState().status).toBe("failed");
    expect(vi.mocked(startPipeline)).toHaveBeenCalledWith(
      "/repo",
      expect.any(Function),
      "full",
      "login flow",
    );
    expect(useOutputStore.getState().lines.map((line) => line.text)).toEqual(
      expect.arrayContaining([
        "[generate] broken prompt",
        "FAIL generate: exploded",
      ]),
    );
  });

  it("records cancelled events and runIndex delegates to index-only mode", async () => {
    vi.mocked(startPipeline).mockImplementationOnce(async (_repo, onEvent) => {
      onEvent({ type: "run-started", run_id: "run-3", steps: ["index"] });
      onEvent({ type: "cancelled", run_id: "run-3" });
      return "run-3";
    });

    await expect(runManagedPipeline("/repo", "index-only")).resolves.toBe("run-3");
    expect(usePipelineStore.getState().status).toBe("cancelled");
    expect(useOutputStore.getState().lines.at(-1)?.text).toBe("Pipeline cancelled");

    vi.mocked(startPipeline).mockResolvedValueOnce("run-4");
    await expect(runIndex("/repo")).resolves.toBe("run-4");
    expect(vi.mocked(startPipeline)).toHaveBeenLastCalledWith(
      "/repo",
      expect.any(Function),
      "index-only",
      undefined,
    );
  });

  it("uses the full-pipeline failure label when startup fails", async () => {
    vi.mocked(startPipeline).mockRejectedValue("offline");

    await expect(runManagedPipeline("/repo")).resolves.toBeNull();
    expect(useOutputStore.getState().lines.at(-1)?.text).toBe(
      "Failed to start pipeline: offline",
    );
  });
});
