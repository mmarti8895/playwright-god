// Generation section: kicks off the pipeline against the active repository,
// streams events into the OutputPane, drives the progress bar + status badge,
// and supports cancellation.
import { useEffect, useState } from "react";
import clsx from "clsx";

import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import {
  computeProgress,
  usePipelineStore,
  type PipelineStatus,
} from "@/state/pipeline";
import { cancelPipeline } from "@/lib/pipeline";
import { runManagedPipeline } from "@/lib/pipeline-run";

const BADGE: Record<PipelineStatus, { label: string; cls: string }> = {
  idle: { label: "Idle", cls: "bg-ink-100 text-ink-600" },
  running: { label: "Running", cls: "bg-accent/15 text-accent" },
  succeeded: { label: "Succeeded", cls: "bg-emerald-100 text-emerald-700" },
  failed: { label: "Failed", cls: "bg-rose-100 text-rose-700" },
  cancelled: { label: "Cancelled", cls: "bg-amber-100 text-amber-700" },
};

function formatElapsed(ms: number): string {
  if (ms <= 0) return "0.0s";
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = s - m * 60;
  return `${m}m ${rem.toFixed(0)}s`;
}

export function Generation() {
  const repo = useUIStore((s) => s.activeRepo);
  const generationPrompt = useUIStore((s) => s.generationPrompt);
  const setGenerationPrompt = useUIStore((s) => s.setGenerationPrompt);

  const status = usePipelineStore((s) => s.status);
  const completed = usePipelineStore((s) => s.completedSteps);
  const total = usePipelineStore((s) => s.totalSteps);
  const stepFraction = usePipelineStore((s) => s.stepFraction);
  const currentStep = usePipelineStore((s) => s.currentStep);
  const startedAt = usePipelineStore((s) => s.startedAt);
  const finishedAt = usePipelineStore((s) => s.finishedAt);
  const errorMessage = usePipelineStore((s) => s.errorMessage);
  const runId = usePipelineStore((s) => s.runId);

  const [description, setDescription] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);

  // Prefill from cross-section prompts (e.g. "Generate test for this gap"
  // from the Coverage viewer). Consumes-and-clears so it only fires once.
  useEffect(() => {
    if (generationPrompt) {
      setDescription(generationPrompt);
      setGenerationPrompt("");
    }
  }, [generationPrompt, setGenerationPrompt]);

  useEffect(() => {
    if (!startedAt || finishedAt) {
      setElapsedMs(finishedAt && startedAt ? finishedAt - startedAt : 0);
      return;
    }
    setElapsedMs(Date.now() - startedAt);
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 250);
    return () => window.clearInterval(id);
  }, [startedAt, finishedAt]);

  const isRunning = status === "running";
  const progress = computeProgress({
    completedSteps: completed,
    totalSteps: total,
    stepFraction,
  });
  const badge = BADGE[status];

  const handleRun = async () => {
    if (!repo || isRunning) return;
    await runManagedPipeline(repo, "full", description.trim());
  };

  const handleCancel = async () => {
    if (!isRunning) return;
    await cancelPipeline(runId ?? undefined);
  };

  return (
    <div className="flex flex-col gap-4">
      <Panel>
        <div className="flex flex-col gap-4 p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="text-[15px] font-semibold text-ink-900">Pipeline</h2>
              <span
                className={clsx(
                  "rounded-full px-2 py-0.5 text-[11px] font-medium",
                  badge.cls,
                )}
                aria-live="polite"
              >
                {badge.label}
              </span>
            </div>
            <div className="text-[11px] tabular-nums text-ink-500">
              {formatElapsed(elapsedMs)}
            </div>
          </div>

          {!repo && (
            <div className="rounded-md border border-amber-200 bg-amber-50/80 px-3 py-2 text-[12px] text-amber-800">
              Select a repository in the <strong>Repository</strong> section to enable the pipeline.
            </div>
          )}

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-ink-700">
              Description (optional)
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="What should the next generated test cover?"
              className="resize-none rounded-md border border-ink-200 bg-white/70 px-3 py-2 text-[13px] text-ink-900 placeholder:text-ink-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
              disabled={isRunning}
            />
          </label>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRun}
              disabled={!repo || isRunning}
              className={clsx(
                "rounded-md px-3 py-1.5 text-[12px] font-medium",
                !repo || isRunning
                  ? "bg-ink-100 text-ink-400"
                  : "bg-accent text-white shadow-soft hover:bg-accent/90",
              )}
            >
              {isRunning ? "Running..." : "Run Pipeline"}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={!isRunning}
              className={clsx(
                "rounded-md px-3 py-1.5 text-[12px] font-medium",
                !isRunning
                  ? "bg-ink-100 text-ink-400"
                  : "bg-white text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50",
              )}
            >
              Cancel
            </button>
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-[11px] text-ink-500">
              <span>
                {currentStep
                  ? `${currentStep} (${completed}/${total})`
                  : `${completed}/${total} steps`}
              </span>
              <span className="tabular-nums">{Math.round(progress * 100)}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
              <div
                className={clsx(
                  "h-full rounded-full transition-[width] duration-200",
                  status === "failed"
                    ? "bg-rose-500"
                    : status === "cancelled"
                      ? "bg-amber-500"
                      : "bg-accent",
                )}
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
            {errorMessage && (
              <div className="mt-1 text-[11px] text-rose-700">{errorMessage}</div>
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}
