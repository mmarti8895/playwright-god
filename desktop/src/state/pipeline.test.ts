import { beforeEach, describe, expect, it } from "vitest";
import { computeProgress, usePipelineStore } from "@/state/pipeline";

describe("pipeline store", () => {
  beforeEach(() => {
    usePipelineStore.getState().reset();
  });

  it("applies the run lifecycle including failure and cancellation states", () => {
    const store = usePipelineStore.getState();

    store.begin("run-1", ["index"]);
    expect(usePipelineStore.getState().status).toBe("running");
    expect(usePipelineStore.getState().runId).toBe("run-1");

    store.apply({ type: "started", step: "index" });
    expect(usePipelineStore.getState().currentStep).toBe("index");

    store.apply({ type: "progress", step: "index", fraction: 0.5 });
    expect(usePipelineStore.getState().stepFraction).toBe(0.5);

    store.apply({ type: "finished", step: "index", exit_code: 0 });
    expect(usePipelineStore.getState().completedSteps).toBe(1);
    expect(usePipelineStore.getState().currentStep).toBeNull();

    store.apply({ type: "run-finished", run_id: "run-1" });
    expect(usePipelineStore.getState().status).toBe("succeeded");

    store.apply({ type: "failed", step: "generate", exit_code: 1, message: "boom" });
    expect(usePipelineStore.getState().status).toBe("failed");
    expect(usePipelineStore.getState().errorMessage).toBe("boom");

    store.apply({ type: "cancelled", run_id: "run-1" });
    expect(usePipelineStore.getState().status).toBe("cancelled");
  });

  it("ignores progress for non-current steps and computes progress safely", () => {
    const store = usePipelineStore.getState();
    store.apply({ type: "run-started", run_id: "run-2", steps: ["index", "plan"] });
    store.apply({ type: "started", step: "index" });
    store.apply({ type: "progress", step: "plan", fraction: 0.9 });
    expect(usePipelineStore.getState().stepFraction).toBe(0);

    expect(computeProgress({ completedSteps: 1, totalSteps: 2, stepFraction: 0.5 })).toBe(0.75);
    expect(computeProgress({ completedSteps: 0, totalSteps: 0, stepFraction: 1 })).toBe(0);
  });

  it("sets retrying=true on retry-attempt and clears it on finished", () => {
    const store = usePipelineStore.getState();
    store.begin("run-3", ["plan"]);
    store.apply({ type: "started", step: "plan" });
    expect(usePipelineStore.getState().retrying).toBe(false);

    store.apply({ type: "retry-attempt", step: "plan", attempt: 1, max: 3, delay_s: 2.0 });
    expect(usePipelineStore.getState().retrying).toBe(true);

    store.apply({ type: "finished", step: "plan", exit_code: 0 });
    expect(usePipelineStore.getState().retrying).toBe(false);
  });

  it("clears retrying on failed and cancelled", () => {
    const store = usePipelineStore.getState();
    store.begin("run-4", ["generate"]);
    store.apply({ type: "started", step: "generate" });
    store.apply({ type: "retry-attempt", step: "generate", attempt: 1, max: 3, delay_s: 2.0 });
    expect(usePipelineStore.getState().retrying).toBe(true);

    store.apply({ type: "failed", step: "generate", exit_code: 1, message: "exhausted" });
    expect(usePipelineStore.getState().retrying).toBe(false);
    expect(usePipelineStore.getState().status).toBe("failed");
  });
});
