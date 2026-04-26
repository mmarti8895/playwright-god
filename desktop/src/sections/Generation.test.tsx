import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Generation } from "@/sections/Generation";
import { usePipelineStore } from "@/state/pipeline";
import { useUIStore } from "@/state/ui";

vi.mock("@/lib/pipeline-run", () => ({
  runManagedPipeline: vi.fn(),
}));

vi.mock("@/lib/pipeline", async () => {
  const actual = await vi.importActual<typeof import("@/lib/pipeline")>("@/lib/pipeline");
  return {
    ...actual,
    cancelPipeline: vi.fn(),
  };
});

import { runManagedPipeline } from "@/lib/pipeline-run";
import { cancelPipeline } from "@/lib/pipeline";

describe("Generation", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.mocked(runManagedPipeline).mockReset();
    vi.mocked(cancelPipeline).mockReset();
    usePipelineStore.getState().reset();
    useUIStore.setState({
      activeRepo: "/tmp/repo",
      generationPrompt: "prefill",
    });
  });

  it("prefills from the UI store and starts the full pipeline", async () => {
    render(<Generation />);

    const textarea = screen.getByPlaceholderText("What should the next generated test cover?");
    await waitFor(() => expect(textarea).toHaveValue("prefill"));
    expect(useUIStore.getState().generationPrompt).toBe("");

    fireEvent.click(screen.getByRole("button", { name: "Run Pipeline" }));
    expect(runManagedPipeline).toHaveBeenCalledWith("/tmp/repo", "full", "prefill");
  });

  it("passes the typed description into the full pipeline", () => {
    useUIStore.setState({ activeRepo: "/tmp/repo", generationPrompt: "" });

    render(<Generation />);
    fireEvent.change(screen.getByPlaceholderText("What should the next generated test cover?"), {
      target: { value: "checkout edge case" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Pipeline" }));

    expect(runManagedPipeline).toHaveBeenCalledWith(
      "/tmp/repo",
      "full",
      "checkout edge case",
    );
  });

  it("shows the repo warning and cancels the active run", async () => {
    useUIStore.setState({ activeRepo: null, generationPrompt: "" });
    usePipelineStore.setState({
      status: "running",
      runId: "run-9",
      totalSteps: 1,
      completedSteps: 0,
      currentStep: "index",
      startedAt: Date.now(),
    });

    render(<Generation />);

    expect(screen.getByText(/Select a repository/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cancelPipeline).toHaveBeenCalledWith("run-9");
  });

  it("renders failed and cancelled pipeline states", () => {
    const now = new Date("2026-04-22T12:00:00Z").valueOf();

    usePipelineStore.setState({
      status: "failed",
      runId: "run-10",
      totalSteps: 2,
      completedSteps: 1,
      stepFraction: 0,
      currentStep: "generate",
      startedAt: now - 2000,
      finishedAt: now,
      errorMessage: "prompt failed",
    });

    const { container, rerender } = render(<Generation />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("prompt failed")).toBeInTheDocument();
    expect(screen.getByText("2.0s")).toBeInTheDocument();
    expect(container.querySelector(".bg-rose-500")).not.toBeNull();

    act(() => {
      usePipelineStore.setState({
        status: "cancelled",
        runId: "run-11",
        totalSteps: 2,
        completedSteps: 1,
        stepFraction: 0,
        currentStep: null,
        startedAt: now - 3000,
        finishedAt: now,
        errorMessage: null,
      });
    });
    rerender(<Generation />);
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    expect(container.querySelector(".bg-amber-500")).not.toBeNull();
  });

  it("updates elapsed time while the pipeline is running", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-22T12:00:00Z"));
    usePipelineStore.setState({
      status: "running",
      runId: "run-12",
      totalSteps: 2,
      completedSteps: 0,
      stepFraction: 0,
      currentStep: "index",
      startedAt: new Date("2026-04-22T11:59:58Z").valueOf(),
      finishedAt: null,
      errorMessage: null,
    });

    render(<Generation />);
    expect(screen.getByText("2.0s")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("3.0s")).toBeInTheDocument();
  });

  it("formats elapsed time in minutes for longer finished runs", () => {
    const now = new Date("2026-04-22T12:05:00Z").valueOf();
    usePipelineStore.setState({
      status: "succeeded",
      runId: "run-13",
      totalSteps: 2,
      completedSteps: 2,
      stepFraction: 1,
      currentStep: null,
      startedAt: now - 65000,
      finishedAt: now,
      errorMessage: null,
    });

    render(<Generation />);
    expect(screen.getByText("1m 5s")).toBeInTheDocument();
  });
});
