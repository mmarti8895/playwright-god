// Pipeline status store: tracks run id, current step, status badge, progress,
// and elapsed time. Driven by events forwarded from the Tauri channel.

import { create } from "zustand";
import { PIPELINE_STEPS, type PipelineEvent, type PipelineStep } from "@/lib/pipeline";

export type PipelineStatus =
  | "idle"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

interface PipelineState {
  status: PipelineStatus;
  runId: string | null;
  currentStep: PipelineStep | null;
  completedSteps: number;
  totalSteps: number;
  stepFraction: number;
  startedAt: number | null;
  finishedAt: number | null;
  errorMessage: string | null;

  begin: (runId: string, steps: PipelineStep[]) => void;
  apply: (event: PipelineEvent) => void;
  reset: () => void;
}

const initial = {
  status: "idle" as PipelineStatus,
  runId: null,
  currentStep: null,
  completedSteps: 0,
  totalSteps: PIPELINE_STEPS.length,
  stepFraction: 0,
  startedAt: null,
  finishedAt: null,
  errorMessage: null,
};

export const usePipelineStore = create<PipelineState>((set) => ({
  ...initial,

  begin: (runId, steps) =>
    set({
      ...initial,
      status: "running",
      runId,
      totalSteps: steps.length,
      startedAt: Date.now(),
    }),

  apply: (event) =>
    set((s) => {
      switch (event.type) {
        case "run-started":
          return {
            ...initial,
            status: "running",
            runId: event.run_id,
            totalSteps: event.steps.length,
            startedAt: Date.now(),
          };
        case "started":
          return { currentStep: event.step, stepFraction: 0 };
        case "progress":
          return event.step === s.currentStep
            ? { stepFraction: event.fraction }
            : {};
        case "finished":
          return {
            currentStep: null,
            completedSteps: s.completedSteps + 1,
            stepFraction: 0,
          };
        case "run-finished":
          return {
            status: "succeeded" as PipelineStatus,
            currentStep: null,
            stepFraction: 1,
            finishedAt: Date.now(),
          };
        case "cancelled":
          return {
            status: "cancelled" as PipelineStatus,
            currentStep: null,
            finishedAt: Date.now(),
          };
        case "failed":
          return {
            status: "failed" as PipelineStatus,
            currentStep: event.step,
            errorMessage: event.message,
            finishedAt: Date.now(),
          };
        default:
          return {};
      }
    }),

  reset: () => set({ ...initial }),
}));

export function computeProgress(s: {
  completedSteps: number;
  totalSteps: number;
  stepFraction: number;
}): number {
  if (s.totalSteps <= 0) return 0;
  const base = s.completedSteps / s.totalSteps;
  const partial = s.stepFraction / s.totalSteps;
  return Math.min(1, base + partial);
}
