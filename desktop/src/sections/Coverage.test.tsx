// filepath: /home/mars/Desktop/projects/playwright-god/desktop/src/sections/Coverage.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import type { CoverageReport } from "@/lib/artifacts";

vi.mock("@/lib/artifacts", async () => {
  const mod = await vi.importActual<typeof import("@/lib/artifacts")>(
    "@/lib/artifacts",
  );
  return { ...mod, readCoverage: vi.fn() };
});

import { readCoverage } from "@/lib/artifacts";
import { CoverageView } from "@/sections/Coverage";
import { useUIStore } from "@/state/ui";

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
    useUIStore.setState({
      activeRepo: "/tmp/repo",
      activeSection: "coverage",
      artifactsVersion: 0,
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
});
