import { beforeEach, describe, expect, it } from "vitest";
import { useUIStore } from "@/state/ui";

describe("coverageRun Zustand slice", () => {
  beforeEach(() => {
    useUIStore.getState().clearCoverageRun();
  });

  it("starts in idle state with empty log and no error", () => {
    const s = useUIStore.getState().coverageRun;
    expect(s.status).toBe("idle");
    expect(s.logLines).toHaveLength(0);
    expect(s.errorMessage).toBeNull();
  });

  it("setCoverageRunStatus transitions status", () => {
    useUIStore.getState().setCoverageRunStatus("running");
    expect(useUIStore.getState().coverageRun.status).toBe("running");

    useUIStore.getState().setCoverageRunStatus("done");
    expect(useUIStore.getState().coverageRun.status).toBe("done");

    useUIStore.getState().setCoverageRunStatus("error");
    expect(useUIStore.getState().coverageRun.status).toBe("error");
  });

  it("setCoverageRunStatus to idle clears errorMessage", () => {
    // Manually set an error message by patching state
    useUIStore.setState((s) => ({
      coverageRun: { ...s.coverageRun, status: "error", errorMessage: "oops" },
    }));
    expect(useUIStore.getState().coverageRun.errorMessage).toBe("oops");

    useUIStore.getState().setCoverageRunStatus("idle");
    expect(useUIStore.getState().coverageRun.errorMessage).toBeNull();
  });

  it("appendCoverageLogLine adds lines", () => {
    useUIStore.getState().appendCoverageLogLine("line one");
    useUIStore.getState().appendCoverageLogLine("line two");
    const { logLines } = useUIStore.getState().coverageRun;
    expect(logLines).toEqual(["line one", "line two"]);
  });

  it("appendCoverageLogLine respects 500-line ring buffer cap", () => {
    for (let i = 0; i < 502; i++) {
      useUIStore.getState().appendCoverageLogLine(`line ${i}`);
    }
    const { logLines } = useUIStore.getState().coverageRun;
    expect(logLines).toHaveLength(500);
    // oldest lines should have been dropped; last line should be line 501
    expect(logLines.at(-1)).toBe("line 501");
    expect(logLines[0]).toBe("line 2");
  });

  it("clearCoverageRun resets to idle with empty log and no error", () => {
    useUIStore.getState().setCoverageRunStatus("done");
    useUIStore.getState().appendCoverageLogLine("some log");
    useUIStore.setState((s) => ({
      coverageRun: { ...s.coverageRun, errorMessage: "err" },
    }));

    useUIStore.getState().clearCoverageRun();

    const s = useUIStore.getState().coverageRun;
    expect(s.status).toBe("idle");
    expect(s.logLines).toHaveLength(0);
    expect(s.errorMessage).toBeNull();
  });
});
