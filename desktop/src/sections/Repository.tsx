import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import { usePipelineStore } from "@/state/pipeline";
import {
  addRecentRepo,
  pickRepository,
} from "@/lib/commands";
import { readIndexStatus, type IndexStatus } from "@/lib/artifacts";
import { runIndex, runManagedPipeline } from "@/lib/pipeline-run";

export function Repository() {
  const activeRepo = useUIStore((s) => s.activeRepo);
  const setActiveRepo = useUIStore((s) => s.setActiveRepo);
  const recent = useUIStore((s) => s.recentRepos);
  const setRecentRepos = useUIStore((s) => s.setRecentRepos);
  const version = useUIStore((s) => s.artifactsVersion);
  const pipelineStatus = usePipelineStore((s) => s.status);
  const pipelineTotalSteps = usePipelineStore((s) => s.totalSteps);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const open = async () => {
    const path = await pickRepository();
    if (!path) return;
    setActiveRepo(path);
    const updated = await addRecentRepo(path);
    if (updated.length) setRecentRepos(updated);
  };

  useEffect(() => {
    if (!activeRepo) {
      setIndexStatus(null);
      return;
    }
    let cancelled = false;
    setStatusLoading(true);
    void readIndexStatus(activeRepo)
      .then((status) => {
        if (!cancelled) {
          setIndexStatus(status);
          setStatusLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatusLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeRepo, version]);

  const isRunning = pipelineStatus === "running";
  const isIndexing = isRunning && pipelineTotalSteps === 1;
  const statusText = describeIndexStatus(indexStatus, statusLoading, isIndexing);

  return (
    <div className="flex flex-col gap-6">
      <Panel>
        <div className="flex items-start justify-between gap-6">
          <div className="flex flex-col gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">
              Active Repository
            </div>
            {activeRepo ? (
              <div className="font-mono text-[13px] text-ink-800 break-all">
                {activeRepo}
              </div>
            ) : (
              <div className="text-[13px] text-ink-500">
                No repository selected.
              </div>
            )}
            <div className="text-[12px] text-ink-500">{statusText}</div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <button
              type="button"
              onClick={open}
              className="rounded-lg bg-accent px-4 py-2 text-[13px] font-medium text-white shadow-soft transition-colors hover:bg-accent-hover"
            >
              Open Repository…
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => activeRepo && void runIndex(activeRepo)}
                disabled={!activeRepo || isRunning}
                className="rounded-lg border border-ink-200 bg-white px-4 py-2 text-[13px] font-medium text-ink-800 transition-colors hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isIndexing ? "Indexing…" : "Run Index"}
              </button>
              <button
                type="button"
                onClick={() => activeRepo && void runManagedPipeline(activeRepo)}
                disabled={!activeRepo || isRunning}
                className="rounded-lg bg-ink-900 px-4 py-2 text-[13px] font-medium text-white transition-colors hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Run Pipeline
              </button>
            </div>
          </div>
        </div>
      </Panel>

      <Panel>
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
          Recent Repositories
        </div>
        {recent.length === 0 ? (
          <div className="text-[13px] text-ink-500">
            Recent repositories will appear here once you open one.
          </div>
        ) : (
          <ul className="flex flex-col">
            {recent.map((r) => (
              <li key={r.path}>
                <button
                  type="button"
                  onClick={() => setActiveRepo(r.path)}
                  className="flex w-full items-center justify-between gap-4 rounded-lg px-3 py-2 text-left text-[13px] hover:bg-ink-100"
                >
                  <span className="font-mono truncate text-ink-800">
                    {r.path}
                  </span>
                  <span className="shrink-0 text-[11px] text-ink-400">
                    {new Date(r.openedAt).toLocaleString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function describeIndexStatus(
  status: IndexStatus | null,
  loading: boolean,
  indexing: boolean,
): string {
  if (indexing) return "Indexing is currently running for this repository.";
  if (loading) return "Checking index status…";
  if (!status) return "Select a repository to inspect index status.";
  if (status.has_index && status.has_memory_map) {
    return "Index and memory map are available.";
  }
  if (status.has_index) {
    return "Index is available, but no memory map has been saved yet.";
  }
  if (status.has_memory_map) {
    return "Memory map exists, but no persisted search index was found.";
  }
  return "Indexing is required before Memory Map and RAG search can load.";
}
