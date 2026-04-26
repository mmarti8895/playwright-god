import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import type { CoverageReport } from "@/lib/artifacts";

vi.mock("@/lib/artifacts", async () => {
  const mod = await vi.importActual<typeof import("@/lib/artifacts")>(
    "@/lib/artifacts",
  );
  return { ...mod, readCoverage: vi.fn() };
});

vi.mock("@/lib/csv", () => ({
  exportRows: vi.fn().mockResolvedValue({ message: "Exported" }),
}));

vi.mock("@/lib/coverage-run", () => ({
  runCoverage: vi.fn(),
  cancelCoverage: vi.fn().mockResolvedValue(true),
  readLatestSpecPath: vi.fn().mockResolvedValue(null),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  isTauri: vi.fn().mockReturnValue(false),
  Channel: class {},
}));

import { readCoverage } from "@/lib/artifacts";
import { exportRows } from "@/lib/csv";
import { readLatestSpecPath } from "@/lib/coverage-run";
import { CoverageView } from "@/sections/Coverage";
import { useUIStore } from "@/state/ui";
import { usePipelineStore } from "@/state/pipeline";

const REPORT: CoverageReport = {
  totals: {
    total_files: 3,
    total_lines: 100,
    covered_lines: 60,
    percent: 60.0,
  },
  files: {
    "src/a.ts": { total_lines: 10, covered_lines: 9, percent: 90.0, missing_line_ranges: [[5, 5]] },
    "src/b.ts": { total_lines: 50, covered_lines: 25, percent: 50.0, missing_line_ranges: [[1, 10]] },
    "src/c.ts": { total_lines: 40, covered_lines: 26, percent: 65.0, missing_line_ranges: [] },
  },
};

function getRowPaths(): string[] {
  const rows = screen.getAllByRole("row").slice(1);
  return rows
    .map((r) => within(r).queryAllByRole("cell")[0]?.textContent ?? "")
    .filter((p) => p.startsWith("src/"));
}

describe("CoverageView Files tab sorting", () => {
  beforeEach(() => {
    vi.mocked(readCoverage).mockReset();
    vi.mocked(readCoverage).mockResolvedValue(REPORT);
    vi.mocked(exportRows).mockReset();
    vi.mocked(exportRows).mockResolvedValue({ message: "Exported" });
    useUIStore.setState({
      activeRepo: "/tmp/repo",
      activeSection: "coverage",
      artifactsVersion: 0,
      generationPrompt: "",
    });
  });

  it("defaults to least-covered first (percent ascending)", async () => {
    render(<CoverageView />);
    await waitFor(() => expect(screen.getByText("src/a.ts")).toBeInTheDocument());
    expect(getRowPaths()).toEqual(["src/b.ts", "src/c.ts", "src/a.ts"]);
  });

  it("toggles percent ordering when the % header is clicked", async () => {
    render(<CoverageView />);
    await waitFor(() => expect(screen.getByText("src/a.ts")).toBeInTheDocument());
    // The active sort header has text "%" followed by an arrow span.
    const buttons = screen.getAllByRole("button");
    const percentBtn = buttons.find((b) => /^%/.test(b.textContent ?? ""));
    expect(percentBtn).toBeTruthy();
    fireEvent.click(percentBtn!);
    await waitFor(() =>
      expect(getRowPaths()).toEqual(["src/a.ts", "src/c.ts", "src/b.ts"]),
    );
  });

  it("sorts by path when the Path header is clicked", async () => {
    render(<CoverageView />);
    await waitFor(() => expect(screen.getByText("src/a.ts")).toBeInTheDocument());
    const buttons = screen.getAllByRole("button");
    const pathBtn = buttons.find((b) => (b.textContent ?? "").trim() === "Path");
    expect(pathBtn).toBeTruthy();
    fireEvent.click(pathBtn!);
    await waitFor(() =>
      expect(getRowPaths()).toEqual(["src/a.ts", "src/b.ts", "src/c.ts"]),
    );
  });

  it("shows empty state when there is no report", async () => {
    vi.mocked(readCoverage).mockResolvedValueOnce(null);

    render(<CoverageView />);
    await waitFor(() =>
      expect(screen.getByText("No coverage report yet")).toBeInTheDocument(),
    );
  });

  it("shows read failures as an inline error in the empty state", async () => {
    vi.mocked(readCoverage).mockRejectedValueOnce(new Error("coverage missing"));

    render(<CoverageView />);
    await waitFor(() =>
      expect(screen.getByText("Failed to read coverage data")).toBeInTheDocument(),
    );
    expect(screen.getByText("coverage missing")).toBeInTheDocument();
  });

  it("navigates to Generation and pre-fills prompt from uncovered gaps", async () => {
    render(<CoverageView />);
    await waitFor(() => expect(screen.getByText("src/a.ts")).toBeInTheDocument());

    const gapsTab = screen.getByRole("tab", { name: "Test Gaps" });
    fireEvent.mouseDown(gapsTab, { button: 0, ctrlKey: false });
    fireEvent.click(gapsTab);

    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "Generate test", hidden: true }).length,
      ).toBeGreaterThan(0),
    );
    fireEvent.click(
      screen.getAllByRole("button", { name: "Generate test", hidden: true })[0],
    );

    const state = useUIStore.getState();
    expect(state.activeSection).toBe("generation");
    expect(state.generationPrompt).toMatch(/Add a Playwright test/);
  });

  it("exports currently sorted file rows", async () => {
    render(<CoverageView />);
    await waitFor(() => expect(screen.getByText("src/a.ts")).toBeInTheDocument());

    // Toggle once so percent ordering is descending before export.
    const percentBtn = screen
      .getAllByRole("button")
      .find((b) => /^%/.test(b.textContent ?? ""));
    expect(percentBtn).toBeTruthy();
    fireEvent.click(percentBtn!);

    fireEvent.click(screen.getByRole("button", { name: "Export as CSV" }));
    await waitFor(() => expect(exportRows).toHaveBeenCalled());

    const rows = vi.mocked(exportRows).mock.calls[0]?.[0] as Array<{ path: string }>;
    expect(rows.map((r) => r.path)).toEqual(["src/a.ts", "src/c.ts", "src/b.ts"]);
  });
});

describe("CoverageView – run controls lifecycle", () => {
  beforeEach(() => {
    vi.mocked(readCoverage).mockReset();
    vi.mocked(readCoverage).mockResolvedValue(null);
    vi.mocked(readLatestSpecPath).mockReset();
    vi.mocked(readLatestSpecPath).mockResolvedValue(null);
    useUIStore.setState({
      activeRepo: "/tmp/repo",
      activeSection: "coverage",
      artifactsVersion: 0,
      generationPrompt: "",
      coverageRun: { status: "idle", logLines: [], errorMessage: null },
    });
    usePipelineStore.getState().reset();
  });

  it("shows Run Coverage button in empty state", async () => {
    render(<CoverageView />);
    await waitFor(() =>
      expect(screen.getByText("No coverage report yet")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Run Coverage/i })).toBeInTheDocument();
  });

  it("Run Coverage disabled when no spec is available", async () => {
    vi.mocked(readLatestSpecPath).mockResolvedValue(null);
    render(<CoverageView />);
    const btn = await screen.findByRole("button", { name: /Run Coverage/i });
    expect(btn).toBeDisabled();
  });

  it("Run Coverage enabled when spec is available", async () => {
    vi.mocked(readLatestSpecPath).mockResolvedValue("/repo/.pg_runs/run/generated.spec.ts");
    render(<CoverageView />);
    const btn = await screen.findByRole("button", { name: /Run Coverage/i });
    await waitFor(() => expect(btn).toBeEnabled());
  });

  it("running state renders Cancel button", async () => {
    useUIStore.setState({
      coverageRun: { status: "running", logLines: [], errorMessage: null },
    });
    render(<CoverageView />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument(),
    );
  });

  it("done state renders Clear button", async () => {
    useUIStore.setState({
      coverageRun: { status: "done", logLines: ["done"], errorMessage: null },
    });
    render(<CoverageView />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Clear/i })).toBeInTheDocument(),
    );
  });

  it("log panel shows line count when lines exist", async () => {
    useUIStore.setState({
      coverageRun: {
        status: "running",
        logLines: ["line a", "line b", "line c"],
        errorMessage: null,
      },
    });
    render(<CoverageView />);
    await waitFor(() =>
      expect(screen.getByText(/Run log \(3 lines\)/i)).toBeInTheDocument(),
    );
  });
});
