import { useEffect, useMemo, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import clsx from "clsx";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import {
  readCoverage,
  type CoverageFile,
  type CoverageReport,
  type CoverageRouteDetail,
} from "@/lib/artifacts";
import { exportRows } from "@/lib/csv";

interface FileRow {
  path: string;
  total_lines: number;
  covered_lines: number;
  percent: number;
  missing: string;
}

type SortKey = "path" | "percent" | "covered_lines" | "total_lines";

export function CoverageView() {
  const repo = useUIStore((s) => s.activeRepo);
  const version = useUIStore((s) => s.artifactsVersion);
  const setActiveSection = useUIStore((s) => s.setActiveSection);
  const setGapPrompt = useUIStore((s) => s.setGenerationPrompt);
  const [report, setReport] = useState<CoverageReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("percent");
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    if (!repo) {
      setReport(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void readCoverage(repo).then((r) => {
      if (!cancelled) {
        setReport(r);
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

  const fileRows = useMemo<FileRow[]>(
    () => buildFileRows(report?.files ?? {}),
    [report],
  );

  const sortedFiles = useMemo(() => {
    const rows = [...fileRows];
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });
    return rows;
  }, [fileRows, sortKey, sortAsc]);

  const onSort = (k: SortKey) => {
    if (sortKey === k) setSortAsc((a) => !a);
    else {
      setSortKey(k);
      setSortAsc(k === "path");
    }
  };

  const onExportFiles = async () => {
    const r = await exportRows(
      sortedFiles,
      [
        { header: "path", value: (x) => x.path },
        { header: "covered_lines", value: (x) => x.covered_lines },
        { header: "total_lines", value: (x) => x.total_lines },
        { header: "percent", value: (x) => x.percent },
        { header: "missing_line_ranges", value: (x) => x.missing },
      ],
      "coverage_files.csv",
    );
    setToast(r.message);
  };

  const onExportRoutes = async () => {
    const details = report?.routes?.details ?? [];
    const r = await exportRows(
      details,
      [
        { header: "route_id", value: (x) => x.route_id },
        { header: "method", value: (x) => x.method },
        { header: "path", value: (x) => x.path },
        { header: "covered", value: (x) => (x.covered ? "true" : "false") },
        { header: "handler_files", value: (x) => x.handler_files.join(";") },
      ],
      "coverage_routes.csv",
    );
    setToast(r.message);
  };

  const generateForGap = (description: string) => {
    setGapPrompt(description);
    setActiveSection("generation");
  };

  if (!repo) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">
          Open a repository to view coverage.
        </div>
      </Panel>
    );
  }

  if (loading) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">Loading coverage…</div>
      </Panel>
    );
  }

  if (!report) {
    return (
      <Panel className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <div className="text-[15px] font-medium text-ink-700">No coverage report yet</div>
        <div className="max-w-md text-[13px] text-ink-500">
          Run a pipeline with <span className="font-mono">--coverage</span> to produce a
          <span className="font-mono"> coverage_merged.json</span> in the latest
          <span className="font-mono"> .pg_runs/</span> directory.
        </div>
      </Panel>
    );
  }

  const totals = report.totals;
  const routes = report.routes;
  const uncoveredRoutes =
    routes?.details.filter((r) => !r.covered) ?? [];
  const uncoveredFileGaps = sortedFiles.filter((r) => r.percent < 100).slice(0, 50);

  return (
    <Panel className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      {totals && (
        <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12px] text-ink-500">
          <span>
            <span className="font-medium text-ink-800">{totals.percent.toFixed(1)}%</span> overall
          </span>
          <span>
            {totals.covered_lines.toLocaleString()} / {totals.total_lines.toLocaleString()} lines
          </span>
          <span>{totals.total_files} files</span>
          {report.generated_at && (
            <span className="text-ink-400">{report.generated_at}</span>
          )}
        </header>
      )}

      <Tabs.Root defaultValue="files" className="flex flex-1 min-h-0 flex-col">
        <Tabs.List className="flex gap-1 border-b border-ink-200/60">
          <TabTrigger value="files">Files</TabTrigger>
          <TabTrigger value="routes">Routes</TabTrigger>
          <TabTrigger value="gaps">Test Gaps</TabTrigger>
        </Tabs.List>

        <Tabs.Content value="files" className="flex flex-1 min-h-0 flex-col gap-2 pt-3">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onExportFiles}
              className="rounded-md border border-ink-200 bg-white px-3 py-1 text-[12px]
                         hover:bg-ink-50"
            >
              Export as CSV
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-auto rounded-xl border border-ink-200/60">
            <table className="w-full border-collapse text-[12px]">
              <thead className="sticky top-0 z-10 bg-white">
                <tr className="border-b border-ink-200/60 text-left text-ink-600">
                  <Th k="path" sortKey={sortKey} sortAsc={sortAsc} onSort={onSort}>
                    Path
                  </Th>
                  <Th k="percent" sortKey={sortKey} sortAsc={sortAsc} onSort={onSort}>
                    %
                  </Th>
                  <Th k="covered_lines" sortKey={sortKey} sortAsc={sortAsc} onSort={onSort}>
                    Covered
                  </Th>
                  <Th k="total_lines" sortKey={sortKey} sortAsc={sortAsc} onSort={onSort}>
                    Total
                  </Th>
                  <th className="px-3 py-2">Missing</th>
                </tr>
              </thead>
              <tbody>
                {sortedFiles.map((r) => (
                  <tr key={r.path} className="border-b border-ink-100 hover:bg-ink-50">
                    <td className="px-3 py-1.5 font-mono text-[11px] text-ink-700">{r.path}</td>
                    <td className="px-3 py-1.5">{r.percent.toFixed(1)}</td>
                    <td className="px-3 py-1.5 text-ink-600">{r.covered_lines}</td>
                    <td className="px-3 py-1.5 text-ink-600">{r.total_lines}</td>
                    <td className="px-3 py-1.5 font-mono text-[11px] text-ink-500">{r.missing}</td>
                  </tr>
                ))}
                {sortedFiles.length === 0 && (
                  <tr>
                    <td className="px-3 py-4 text-center text-ink-400" colSpan={5}>
                      No file coverage entries.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Tabs.Content>

        <Tabs.Content value="routes" className="flex flex-1 min-h-0 flex-col gap-2 pt-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[12px] text-ink-500">
              {routes ? (
                <>
                  <span className="font-medium text-ink-700">{routes.covered.length}</span>
                  {" / "}
                  {routes.total} routes covered
                </>
              ) : (
                "No route data."
              )}
            </div>
            {routes && (
              <button
                type="button"
                onClick={onExportRoutes}
                className="rounded-md border border-ink-200 bg-white px-3 py-1 text-[12px]
                           hover:bg-ink-50"
              >
                Export as CSV
              </button>
            )}
          </div>
          {routes && (
            <div className="flex-1 min-h-0 overflow-auto rounded-xl border border-ink-200/60">
              <ul className="divide-y divide-ink-100">
                {routes.details.map((r) => (
                  <RouteRow key={r.route_id} route={r} />
                ))}
              </ul>
            </div>
          )}
        </Tabs.Content>

        <Tabs.Content value="gaps" className="flex flex-1 min-h-0 flex-col gap-2 pt-3">
          {uncoveredRoutes.length === 0 && uncoveredFileGaps.length === 0 ? (
            <div className="flex flex-1 items-center justify-center text-[13px] text-ink-500">
              Nothing uncovered — nice.
            </div>
          ) : (
            <div className="flex-1 min-h-0 overflow-y-auto pr-1">
              {uncoveredRoutes.length > 0 && (
                <section className="mb-4">
                  <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wide text-ink-500">
                    Uncovered routes ({uncoveredRoutes.length})
                  </h3>
                  <ul className="flex flex-col gap-1">
                    {uncoveredRoutes.map((r) => (
                      <li
                        key={r.route_id}
                        className="flex items-center justify-between gap-3 rounded-md
                                   border border-ink-200/60 bg-white px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="font-mono text-[12px] text-ink-800">
                            {r.method} {r.path}
                          </div>
                          {r.handler_files.length > 0 && (
                            <div className="font-mono text-[10px] text-ink-500 truncate">
                              {r.handler_files.join(", ")}
                            </div>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            generateForGap(
                              `Add a Playwright test that exercises the uncovered route ${r.method} ${r.path}.`,
                            )
                          }
                          className="shrink-0 rounded-md bg-ink-900 px-3 py-1 text-[11px]
                                     font-medium text-white hover:bg-ink-800"
                        >
                          Generate test
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {uncoveredFileGaps.length > 0 && (
                <section>
                  <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wide text-ink-500">
                    Files with gaps ({uncoveredFileGaps.length})
                  </h3>
                  <ul className="flex flex-col gap-1">
                    {uncoveredFileGaps.map((r) => (
                      <li
                        key={r.path}
                        className="flex items-center justify-between gap-3 rounded-md
                                   border border-ink-200/60 bg-white px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="font-mono text-[12px] text-ink-800 truncate">
                            {r.path}
                          </div>
                          <div className="text-[11px] text-ink-500">
                            {r.percent.toFixed(1)}% · missing {r.missing || "—"}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            generateForGap(
                              `Add a Playwright test exercising uncovered behavior in ${r.path} (lines ${r.missing}).`,
                            )
                          }
                          className="shrink-0 rounded-md bg-ink-900 px-3 py-1 text-[11px]
                                     font-medium text-white hover:bg-ink-800"
                        >
                          Generate test
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
        </Tabs.Content>
      </Tabs.Root>

      {toast && (
        <div className="pointer-events-none fixed bottom-6 right-6 z-50 rounded-lg
                        bg-ink-900 px-3 py-2 text-[12px] text-white shadow-lg">
          {toast}
        </div>
      )}
    </Panel>
  );
}

function TabTrigger({ value, children }: { value: string; children: React.ReactNode }) {
  return (
    <Tabs.Trigger
      value={value}
      className={clsx(
        "rounded-t-md px-3 py-1.5 text-[12px] text-ink-600",
        "data-[state=active]:bg-white data-[state=active]:text-ink-900",
        "data-[state=active]:border-x data-[state=active]:border-t",
        "data-[state=active]:border-ink-200/60",
        "hover:text-ink-800",
      )}
    >
      {children}
    </Tabs.Trigger>
  );
}

function Th({
  k,
  sortKey,
  sortAsc,
  onSort,
  children,
}: {
  k: SortKey;
  sortKey: SortKey;
  sortAsc: boolean;
  onSort: (k: SortKey) => void;
  children: React.ReactNode;
}) {
  const active = sortKey === k;
  return (
    <th className="px-3 py-2">
      <button
        type="button"
        onClick={() => onSort(k)}
        className={clsx(
          "inline-flex items-center gap-1 font-medium",
          active ? "text-ink-900" : "text-ink-600 hover:text-ink-800",
        )}
      >
        {children}
        {active && <span className="text-[10px]">{sortAsc ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}

function RouteRow({ route }: { route: CoverageRouteDetail }) {
  return (
    <li className="flex items-center justify-between gap-3 px-3 py-2 hover:bg-ink-50">
      <div className="min-w-0">
        <div className="font-mono text-[12px] text-ink-800">
          {route.method} {route.path}
        </div>
        {route.handler_files.length > 0 && (
          <div className="font-mono text-[10px] text-ink-500 truncate">
            {route.handler_files.join(", ")}
          </div>
        )}
      </div>
      <span
        className={clsx(
          "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium",
          route.covered
            ? "bg-emerald-100 text-emerald-800"
            : "bg-rose-100 text-rose-800",
        )}
      >
        {route.covered ? "covered" : "uncovered"}
      </span>
    </li>
  );
}

function buildFileRows(files: Record<string, CoverageFile>): FileRow[] {
  return Object.entries(files).map(([path, f]) => ({
    path,
    total_lines: f.total_lines,
    covered_lines: f.covered_lines,
    percent: f.percent,
    missing: (f.missing_line_ranges ?? [])
      .map((r) => (r[0] === r[1] ? `${r[0]}` : `${r[0]}–${r[1]}`))
      .join(", "),
  }));
}
