import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import { usePipelineStore } from "@/state/pipeline";
import {
  readIndexStatus,
  readFlowGraph,
  readMemoryMap,
  type FlowGraph,
  type IndexStatus,
  type MemoryMap,
  type MemoryMapFile,
} from "@/lib/artifacts";
import { runIndex } from "@/lib/pipeline-run";
import * as Collapsible from "@radix-ui/react-collapsible";
import clsx from "clsx";

export function MemoryMapView() {
  const repo = useUIStore((s) => s.activeRepo);
  const version = useUIStore((s) => s.artifactsVersion);
  const setActiveSection = useUIStore((s) => s.setActiveSection);
  const setFlowGraphFocus = useUIStore((s) => s.setFlowGraphFocus);
  const pipelineStatus = usePipelineStore((s) => s.status);
  const pipelineTotalSteps = usePipelineStore((s) => s.totalSteps);
  const [data, setData] = useState<MemoryMap | null>(null);
  const [flowGraph, setFlowGraph] = useState<FlowGraph | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const isIndexing = pipelineStatus === "running" && pipelineTotalSteps === 1;

  useEffect(() => {
    if (!repo) {
      setData(null);
      setFlowGraph(null);
      setIndexStatus(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void Promise.all([readMemoryMap(repo), readIndexStatus(repo), readFlowGraph(repo)])
      .then(([mm, status, fg]) => {
        if (!cancelled) {
          setData(mm);
          setIndexStatus(status);
          setFlowGraph(fg);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setFlowGraph(null);
          setIndexStatus(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repo, version]);

  if (!repo) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">
          Open a repository from the Repository tab to view its memory map.
        </div>
      </Panel>
    );
  }

  if (loading && !isIndexing) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">Loading memory map…</div>
      </Panel>
    );
  }

  if (!data) {
    return (
      <Panel className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <div className="text-[15px] font-medium text-ink-700">
          {isIndexing ? "Indexing repository…" : "No memory map found"}
        </div>
        <div className="max-w-md text-[13px] text-ink-500">
          {isIndexing
            ? "The desktop app is running the index step now. This view will refresh when the run completes."
            : indexStatus?.has_index
              ? "A persisted index exists, but no memory map artifact was found yet. Run Index to rebuild the memory map."
              : (
                <>
                  Run the <span className="font-mono">index</span> step to build a memory map at
                  <span className="font-mono"> .idx/memory_map.json</span>.
                </>
              )}
        </div>
        <button
          type="button"
          onClick={() => repo && void runIndex(repo)}
          disabled={!repo || isIndexing}
          className="rounded-xl bg-ink-900 px-4 py-2 text-[12px] font-medium text-white hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isIndexing ? "Indexing…" : "Run Index"}
        </button>
      </Panel>
    );
  }

  // Group files by feature area (or fall back to top-level directory).
  const filesByFeature = groupFiles(data);
  const evidenceFiles = new Set<string>();
  for (const n of flowGraph?.nodes ?? []) {
    for (const e of n.evidence ?? []) {
      if (e.file) evidenceFiles.add(e.file);
    }
  }
  const featureNames = Object.keys(filesByFeature).sort();

  return (
    <Panel className="flex h-full min-h-0 flex-col gap-4 overflow-hidden">
      <header className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] text-ink-500">
          <span className="font-medium text-ink-700">{data.total_files ?? 0}</span> files ·
          <span className="ml-1 font-medium text-ink-700">{data.total_chunks ?? 0}</span> chunks
          {data.schema_version && (
            <span className="ml-2 text-ink-400">schema {data.schema_version}</span>
          )}
        </div>
        {data.languages && Object.keys(data.languages).length > 0 && (
          <div className="flex flex-wrap gap-1">
            {Object.entries(data.languages).map(([lang, n]) => (
              <span
                key={lang}
                className="rounded-full bg-ink-100 px-2 py-0.5 text-[11px] text-ink-700"
              >
                {lang} · {n}
              </span>
            ))}
          </div>
        )}
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto pr-1">
        <ul className="flex flex-col gap-2">
          {featureNames.map((name) => (
            <FeatureGroup
              key={name}
              name={name}
              files={filesByFeature[name]}
              hasFlowEvidence={(path) => evidenceFiles.has(path)}
              onOpenInFlowGraph={(path) => {
                setFlowGraphFocus({ query: path });
                setActiveSection("flow-graph");
              }}
            />
          ))}
        </ul>
      </div>
    </Panel>
  );
}

function FeatureGroup({
  name,
  files,
  hasFlowEvidence,
  onOpenInFlowGraph,
}: {
  name: string;
  files: MemoryMapFile[];
  hasFlowEvidence: (path: string) => boolean;
  onOpenInFlowGraph: (path: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} asChild>
      <li className="rounded-xl border border-ink-200/60 bg-white/60">
        <Collapsible.Trigger
          className={clsx(
            "flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left",
            "hover:bg-ink-50",
          )}
        >
          <span className="text-[13px] font-medium text-ink-800">{name}</span>
          <span className="text-[11px] text-ink-500">
            {files.length} {files.length === 1 ? "file" : "files"}
            <span className="ml-2 text-ink-400">{open ? "▾" : "▸"}</span>
          </span>
        </Collapsible.Trigger>
        <Collapsible.Content className="border-t border-ink-200/60 px-3 py-2">
          <ul className="flex flex-col gap-0.5">
            {files.map((f) => (
              <li
                key={f.path}
                className="flex items-center justify-between gap-3 rounded px-2 py-1 hover:bg-ink-50"
              >
                <span className="font-mono text-[12px] text-ink-700 truncate">{f.path}</span>
                <div className="shrink-0 flex items-center gap-2">
                  <span className="text-[11px] text-ink-500">
                    {f.chunk_count != null ? `${f.chunk_count} chunks` : ""}
                  </span>
                  {hasFlowEvidence(f.path) && (
                    <button
                      type="button"
                      className="rounded border border-ink-200 bg-white px-2 py-0.5 text-[10px] text-ink-700 hover:bg-ink-50"
                      onClick={() => onOpenInFlowGraph(f.path)}
                    >
                      Open in Flow Graph
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Collapsible.Content>
      </li>
    </Collapsible.Root>
  );
}

function groupFiles(mm: MemoryMap): Record<string, MemoryMapFile[]> {
  const files = mm.files ?? [];
  const groups: Record<string, MemoryMapFile[]> = {};

  // First, build feature → files from explicit feature definitions if present.
  if (mm.features && mm.features.length > 0) {
    const fileToFeature = new Map<string, string>();
    for (const feat of mm.features) {
      const featName = feat.name || feat.area || "(unnamed)";
      for (const fp of feat.files ?? []) {
        if (!fileToFeature.has(fp)) fileToFeature.set(fp, featName);
      }
    }
    for (const f of files) {
      const name = fileToFeature.get(f.path) ?? topDir(f.path);
      (groups[name] ??= []).push(f);
    }
  } else {
    for (const f of files) {
      const name = (f.feature as string) || topDir(f.path);
      (groups[name] ??= []).push(f);
    }
  }
  for (const arr of Object.values(groups)) {
    arr.sort((a, b) => a.path.localeCompare(b.path));
  }
  return groups;
}

function topDir(path: string): string {
  const idx = path.indexOf("/");
  return idx === -1 ? "(root)" : path.slice(0, idx);
}
