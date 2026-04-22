import { useEffect, useMemo, useRef, useState } from "react";
import * as Checkbox from "@radix-ui/react-checkbox";
import { Virtuoso } from "react-virtuoso";
import clsx from "clsx";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import { useOutputStore } from "@/state/output";
import {
  listRuns,
  tailCodegen,
  type CodegenEvent,
  type RunSummary,
} from "@/lib/runs";

interface PromptRow {
  seq: number;
  filename: string;
  body: unknown;
}

export function CodegenStream() {
  const repo = useUIStore((s) => s.activeRepo);
  const version = useUIStore((s) => s.artifactsVersion);
  const subprocessLines = useOutputStore((s) => s.lines);

  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [prompts, setPrompts] = useState<PromptRow[]>([]);
  const [live, setLive] = useState(false);
  const [status, setStatus] = useState<string>("Idle");
  const stopRef = useRef<{ stop: () => void } | null>(null);

  useEffect(() => {
    if (!repo) {
      setRuns([]);
      setRunId(null);
      return;
    }
    let cancelled = false;
    void listRuns(repo).then((r) => {
      if (!cancelled) {
        setRuns(r);
        setRunId((cur) => cur ?? (r.length > 0 ? r[0].run_id : null));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [repo, version]);

  useEffect(() => {
    stopRef.current?.stop();
    stopRef.current = null;
    if (!live || !repo || !runId) {
      setStatus(live ? "Waiting for repo/run…" : "Idle");
      return;
    }
    setPrompts([]);
    setStatus(`Tailing ${runId}…`);
    const handle = tailCodegen(repo, runId, (e: CodegenEvent) => {
      if (e.type === "prompt") {
        setPrompts((rows) => [
          ...rows,
          { seq: e.seq, filename: e.filename, body: e.body },
        ]);
      } else if (e.type === "stopped") {
        setStatus("Stopped");
      }
    });
    stopRef.current = handle;
    return () => {
      handle.stop();
    };
  }, [live, repo, runId]);

  if (!repo) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">
          Open a repository to tail codegen output.
        </div>
      </Panel>
    );
  }

  return (
    <Panel className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-[12px] text-ink-700">
          <Checkbox.Root
            checked={live}
            onCheckedChange={(v) => setLive(v === true)}
            className="flex h-4 w-4 items-center justify-center rounded border border-ink-300 bg-white data-[state=checked]:border-ink-900 data-[state=checked]:bg-ink-900"
          >
            <Checkbox.Indicator className="text-[10px] text-white">
              ✓
            </Checkbox.Indicator>
          </Checkbox.Root>
          Live tail codegen
        </label>
        <select
          value={runId ?? ""}
          onChange={(e) => setRunId(e.target.value || null)}
          className="rounded-md border border-ink-200 bg-white px-2 py-1.5 text-[12px] focus:border-ink-400 focus:outline-none"
        >
          {runs.length === 0 && <option value="">(no runs)</option>}
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.timestamp} ({r.prompt_count} prompts)
            </option>
          ))}
        </select>
        <span className="text-[11px] text-ink-500">{status}</span>
      </div>

      <div className="flex flex-1 min-h-0 gap-3">
        <PromptsPane prompts={prompts} />
        <SubprocessPane lines={subprocessLines} />
      </div>
    </Panel>
  );
}

function PromptsPane({ prompts }: { prompts: PromptRow[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const toggle = (seq: number) =>
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });

  return (
    <div className="flex flex-1 min-w-0 flex-col rounded-md border border-ink-200/60">
      <header className="flex h-7 shrink-0 items-center justify-between border-b border-ink-200/60 px-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
          LLM transcripts
        </span>
        <span className="text-[10px] text-ink-500">{prompts.length}</span>
      </header>
      <div className="flex-1 min-h-0">
        {prompts.length === 0 ? (
          <div className="flex h-full items-center justify-center px-3 text-[12px] text-ink-400">
            Enable “Live tail codegen” to stream prompts.
          </div>
        ) : (
          <Virtuoso
            data={prompts}
            itemContent={(_, p) => {
              const isOpen = expanded.has(p.seq);
              return (
                <div className="border-b border-ink-100 px-3 py-2 font-mono text-[11px]">
                  <button
                    type="button"
                    onClick={() => toggle(p.seq)}
                    className="flex w-full items-center justify-between gap-2 text-left text-ink-800 hover:text-ink-900"
                  >
                    <span className="truncate">
                      <span className="text-ink-400">#{p.seq} </span>
                      {p.filename}
                    </span>
                    <span className="text-ink-400">{isOpen ? "▾" : "▸"}</span>
                  </button>
                  {isOpen && (
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-ink-50 p-2 text-[10px] text-ink-700">
                      {prettyJson(p.body)}
                    </pre>
                  )}
                </div>
              );
            }}
          />
        )}
      </div>
    </div>
  );
}

function SubprocessPane({
  lines,
}: {
  lines: ReturnType<typeof useOutputStore.getState>["lines"];
}) {
  const data = useMemo(() => lines, [lines]);
  return (
    <div className="flex flex-1 min-w-0 flex-col rounded-md border border-ink-200/60">
      <header className="flex h-7 shrink-0 items-center justify-between border-b border-ink-200/60 px-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
          Codegen subprocess
        </span>
        <span className="text-[10px] text-ink-500">{data.length}</span>
      </header>
      <div className="flex-1 min-h-0">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center px-3 text-[12px] text-ink-400">
            Run a pipeline to see codegen subprocess output.
          </div>
        ) : (
          <Virtuoso
            data={data}
            followOutput
            itemContent={(_, line) => (
              <div
                className={clsx(
                  "px-3 py-0.5 font-mono text-[11px]",
                  line.stream === "stderr" && "text-rose-700",
                  line.stream === "info" && "text-ink-500",
                  line.stream === "stdout" && "text-ink-800",
                )}
              >
                <span className="whitespace-pre-wrap break-words">
                  {line.text}
                </span>
              </div>
            )}
          />
        )}
      </div>
    </div>
  );
}

function prettyJson(v: unknown): string {
  try {
    return typeof v === "string" ? v : JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
