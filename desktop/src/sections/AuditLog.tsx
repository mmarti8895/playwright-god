import { useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import clsx from "clsx";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import { listRuns, type RunSummary } from "@/lib/runs";
import { exportRows } from "@/lib/csv";

type SortKey =
  | "run_id"
  | "status"
  | "duration_ms"
  | "tests_total"
  | "tests_failed"
  | "coverage_percent"
  | "new_nodes";

const COLS: Array<{ key: SortKey; label: string; align?: "right" }> = [
  { key: "run_id", label: "Run" },
  { key: "status", label: "Status" },
  { key: "duration_ms", label: "Duration", align: "right" },
  { key: "tests_total", label: "Tests", align: "right" },
  { key: "tests_failed", label: "Failed", align: "right" },
  { key: "coverage_percent", label: "Cov %", align: "right" },
  { key: "new_nodes", label: "New nodes", align: "right" },
];

export function AuditLog() {
  const repo = useUIStore((s) => s.activeRepo);
  const version = useUIStore((s) => s.artifactsVersion);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("run_id");
  const [sortAsc, setSortAsc] = useState(false);
  const [selected, setSelected] = useState<RunSummary | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!repo) {
      setRuns([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    listRuns(repo)
      .then((r) => {
        if (!cancelled) {
          setRuns(r);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(String(e));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repo, version]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    let rows = q
      ? runs.filter(
          (r) =>
            r.run_id.toLowerCase().includes(q) ||
            r.status.toLowerCase().includes(q) ||
            (r.eval_status ?? "").toLowerCase().includes(q),
        )
      : runs.slice();
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av ?? "").localeCompare(String(bv ?? ""));
      return sortAsc ? cmp : -cmp;
    });
    return rows;
  }, [runs, filter, sortKey, sortAsc]);

  const onSort = (k: SortKey) => {
    if (sortKey === k) setSortAsc((a) => !a);
    else {
      setSortKey(k);
      setSortAsc(false);
    }
  };

  const onExportCsv = async () => {
    const r = await exportRows(
      visible,
      [
        { header: "run_id", value: (x) => x.run_id },
        { header: "timestamp", value: (x) => x.timestamp },
        { header: "status", value: (x) => x.status },
        { header: "duration_ms", value: (x) => x.duration_ms },
        { header: "tests_total", value: (x) => x.tests_total },
        { header: "tests_passed", value: (x) => x.tests_passed },
        { header: "tests_failed", value: (x) => x.tests_failed },
        { header: "eval_status", value: (x) => x.eval_status ?? "" },
        { header: "new_nodes", value: (x) => x.new_nodes },
        { header: "new_journeys", value: (x) => x.new_journeys },
        { header: "new_routes", value: (x) => x.new_routes },
        { header: "coverage_percent", value: (x) => x.coverage_percent ?? "" },
        { header: "prompt_count", value: (x) => x.prompt_count },
        { header: "run_dir", value: (x) => x.run_dir },
      ],
      "audit_log.csv",
    );
    setToast(r.message);
  };

  const onExportJson = async () => {
    const r = await exportRows(
      visible.map((row) => ({ json: JSON.stringify(row) })),
      [{ header: "json", value: (x) => x.json }],
      "audit_log.json.csv",
    );
    setToast(r.message);
  };

  if (!repo) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">
          Open a repository to view its audit log.
        </div>
      </Panel>
    );
  }

  return (
    <Panel className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by run id, status, or eval status…"
          className="flex-1 rounded-md border border-ink-200 bg-white px-3 py-2 text-[13px] focus:border-ink-400 focus:outline-none"
        />
        <span className="text-[11px] text-ink-500">
          {visible.length} of {runs.length}
        </span>
        <button
          type="button"
          onClick={onExportCsv}
          disabled={!visible.length}
          className="rounded-md border border-ink-200 bg-white px-3 py-2 text-[12px] font-medium text-ink-800 hover:bg-ink-50 disabled:opacity-40"
        >
          Export CSV
        </button>
        <button
          type="button"
          onClick={onExportJson}
          disabled={!visible.length}
          className="rounded-md border border-ink-200 bg-white px-3 py-2 text-[12px] font-medium text-ink-800 hover:bg-ink-50 disabled:opacity-40"
        >
          Export JSON
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-[12px] text-rose-900">
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-auto rounded-md border border-ink-200/60">
        <table className="min-w-full text-left text-[12px]">
          <thead className="sticky top-0 bg-ink-50/80 backdrop-blur">
            <tr>
              {COLS.map((c) => (
                <th
                  key={c.key}
                  onClick={() => onSort(c.key)}
                  className={clsx(
                    "cursor-pointer select-none px-3 py-2 font-medium text-ink-600 hover:text-ink-900",
                    c.align === "right" && "text-right",
                  )}
                  scope="col"
                >
                  {c.label}
                  {sortKey === c.key && (
                    <span className="ml-1 text-ink-400">
                      {sortAsc ? "▲" : "▼"}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={COLS.length} className="px-3 py-6 text-center text-ink-500">
                  Loading runs…
                </td>
              </tr>
            )}
            {!loading && visible.length === 0 && (
              <tr>
                <td colSpan={COLS.length} className="px-3 py-6 text-center text-ink-500">
                  No runs found in <code>.pg_runs/</code>.
                </td>
              </tr>
            )}
            {visible.map((r) => (
              <tr
                key={r.run_id}
                onClick={() => setSelected(r)}
                className="cursor-pointer border-t border-ink-100 hover:bg-ink-50"
              >
                <td className="px-3 py-2 font-mono text-[11px] text-ink-800">
                  {r.timestamp}
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={r.status} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatDuration(r.duration_ms)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{r.tests_total}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {r.tests_failed > 0 ? (
                    <span className="text-rose-700">{r.tests_failed}</span>
                  ) : (
                    "0"
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {r.coverage_percent != null ? r.coverage_percent.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{r.new_nodes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {toast && (
        <div className="rounded-md border border-ink-200 bg-ink-50 px-3 py-2 text-[12px] text-ink-700">
          {toast}
        </div>
      )}

      <RunDetailDialog run={selected} onClose={() => setSelected(null)} />
    </Panel>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "passed"
      ? "bg-emerald-100 text-emerald-800"
      : status === "failed"
      ? "bg-rose-100 text-rose-800"
      : status === "interrupted"
      ? "bg-amber-100 text-amber-800"
      : "bg-ink-100 text-ink-700";
  return (
    <span className={clsx("rounded px-2 py-0.5 text-[11px] font-medium", tone)}>
      {status}
    </span>
  );
}

function formatDuration(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${(s - m * 60).toFixed(0)}s`;
}

function RunDetailDialog({
  run,
  onClose,
}: {
  run: RunSummary | null;
  onClose: () => void;
}) {
  const setSection = useUIStore((s) => s.setActiveSection);
  return (
    <Dialog.Root open={!!run} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm" />
        <Dialog.Content className="fixed right-0 top-0 z-50 flex h-full w-[480px] flex-col gap-4 border-l border-ink-200 bg-white p-6 shadow-xl">
          <Dialog.Title className="text-[16px] font-semibold text-ink-900">
            Run {run?.timestamp}
          </Dialog.Title>
          <Dialog.Description className="text-[12px] text-ink-500">
            Detailed summary for the selected run.
          </Dialog.Description>
          {run && (
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto text-[12px]">
              <DetailRow label="Run ID" value={run.run_id} mono />
              <DetailRow label="Run dir" value={run.run_dir} mono />
              <DetailRow label="Status" value={run.status} />
              <DetailRow
                label="Duration"
                value={formatDuration(run.duration_ms)}
              />
              <DetailRow
                label="Tests"
                value={`${run.tests_passed} passed / ${run.tests_failed} failed / ${run.tests_total} total`}
              />
              <DetailRow label="Eval status" value={run.eval_status ?? "—"} />
              <DetailRow
                label="Newly covered"
                value={`${run.new_nodes} nodes, ${run.new_journeys} journeys, ${run.new_routes} routes`}
              />
              <DetailRow
                label="Coverage"
                value={
                  run.coverage_percent != null
                    ? `${run.coverage_percent.toFixed(1)}%`
                    : "—"
                }
              />
              <DetailRow label="Prompts" value={String(run.prompt_count)} />
              <div className="mt-3 flex flex-wrap gap-2">
                {run.has_coverage && (
                  <button
                    type="button"
                    onClick={() => {
                      setSection("coverage");
                      onClose();
                    }}
                    className="rounded-md border border-ink-200 bg-white px-3 py-1.5 text-[11px] font-medium text-ink-800 hover:bg-ink-50"
                  >
                    Open coverage →
                  </button>
                )}
                {run.prompt_count > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setSection("codegen-stream");
                      onClose();
                    }}
                    className="rounded-md border border-ink-200 bg-white px-3 py-1.5 text-[11px] font-medium text-ink-800 hover:bg-ink-50"
                  >
                    View prompts →
                  </button>
                )}
              </div>
            </div>
          )}
          <Dialog.Close asChild>
            <button
              type="button"
              className="self-end rounded-md bg-ink-900 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-ink-800"
            >
              Close
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wider text-ink-500">
        {label}
      </div>
      <div
        className={clsx(
          "mt-0.5 break-words text-ink-800",
          mono && "font-mono text-[11px]",
        )}
      >
        {value}
      </div>
    </div>
  );
}
