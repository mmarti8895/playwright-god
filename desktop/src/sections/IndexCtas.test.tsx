import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Repository } from "@/sections/Repository";
import { MemoryMapView } from "@/sections/MemoryMap";
import { RagView } from "@/sections/Rag";
import { usePipelineStore } from "@/state/pipeline";
import { useUIStore } from "@/state/ui";

vi.mock("@/lib/artifacts", async () => {
  const actual = await vi.importActual<typeof import("@/lib/artifacts")>(
    "@/lib/artifacts",
  );
  return {
    ...actual,
    readIndexStatus: vi.fn(),
    readMemoryMap: vi.fn(),
    ragSearch: vi.fn(),
  };
});

vi.mock("@/lib/pipeline-run", () => ({
  runIndex: vi.fn(),
  runManagedPipeline: vi.fn(),
}));

vi.mock("@/lib/commands", () => ({
  addRecentRepo: vi.fn(),
  pickRepository: vi.fn(),
}));

import { ragSearch, readIndexStatus, readMemoryMap } from "@/lib/artifacts";
import { runIndex, runManagedPipeline } from "@/lib/pipeline-run";
import { addRecentRepo, pickRepository } from "@/lib/commands";

const MISSING_INDEX = {
  has_index: false,
  has_memory_map: false,
  index_dir: null,
  memory_map_path: null,
  active_run_id: null,
  active_run_mode: null,
} as const;

describe("desktop index CTAs", () => {
  beforeEach(() => {
    vi.mocked(readIndexStatus).mockReset();
    vi.mocked(readMemoryMap).mockReset();
    vi.mocked(ragSearch).mockReset();
    vi.mocked(runIndex).mockReset();
    vi.mocked(runManagedPipeline).mockReset();
    vi.mocked(pickRepository).mockReset();
    vi.mocked(addRecentRepo).mockReset();
    vi.mocked(readIndexStatus).mockResolvedValue(MISSING_INDEX);
    vi.mocked(readMemoryMap).mockResolvedValue(null);
    vi.mocked(ragSearch).mockResolvedValue({ hits: [], error: null });
    vi.mocked(pickRepository).mockResolvedValue(null);
    vi.mocked(addRecentRepo).mockResolvedValue([]);

    useUIStore.setState({
      activeRepo: "/tmp/repo",
      activeSection: "repository",
      recentRepos: [],
      artifactsVersion: 0,
    });
    usePipelineStore.getState().reset();
  });

  it("Repository shows missing-index state and triggers Run Index", async () => {
    render(<Repository />);

    await waitFor(() =>
      expect(
        screen.getByText("Indexing is required before Memory Map and RAG search can load."),
      ).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Run Index" }));
    expect(runIndex).toHaveBeenCalledWith("/tmp/repo");
  });

  it("Repository shows active indexing state for an index-only run", async () => {
    usePipelineStore.setState({ status: "running", totalSteps: 1 });

    render(<Repository />);

    await waitFor(() =>
      expect(
        screen.getByText("Indexing is currently running for this repository."),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Indexing…" })).toBeDisabled();
  });

  it("Repository covers the no-repo state and recent repository selection", async () => {
    act(() => {
      useUIStore.setState({
        activeRepo: null,
        activeSection: "repository",
        recentRepos: [{ path: "/tmp/old", openedAt: "2026-04-22T12:00:00Z" }],
        artifactsVersion: 0,
      });
    });

    render(<Repository />);
    expect(
      screen.getByText("Select a repository to inspect index status."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /\/tmp\/old/i }));
    expect(useUIStore.getState().activeRepo).toBe("/tmp/old");
    await waitFor(() =>
      expect(
        screen.getByText("Indexing is required before Memory Map and RAG search can load."),
      ).toBeInTheDocument(),
    );
  });

  it("Repository renders the available status variants", async () => {
    const cases = [
      {
        status: {
          has_index: true,
          has_memory_map: true,
          index_dir: "/tmp/old/.idx",
          memory_map_path: "/tmp/old/.idx/memory_map.json",
          active_run_id: null,
          active_run_mode: null,
        },
        text: "Index and memory map are available.",
      },
      {
        status: {
          has_index: true,
          has_memory_map: false,
          index_dir: "/tmp/old/.idx",
          memory_map_path: null,
          active_run_id: null,
          active_run_mode: null,
        },
        text: "Index is available, but no memory map has been saved yet.",
      },
      {
        status: {
          has_index: false,
          has_memory_map: true,
          index_dir: null,
          memory_map_path: "/tmp/old/.idx/memory_map.json",
          active_run_id: null,
          active_run_mode: null,
        },
        text: "Memory map exists, but no persisted search index was found.",
      },
    ] as const;

    for (const testCase of cases) {
      useUIStore.setState({
        activeRepo: "/tmp/old",
        activeSection: "repository",
        recentRepos: [],
        artifactsVersion: 0,
      });
      vi.mocked(readIndexStatus).mockResolvedValueOnce(testCase.status);

      const view = render(<Repository />);
      await waitFor(() => expect(screen.getByText(testCase.text)).toBeInTheDocument());
      view.unmount();
    }
  });

  it("Repository opens a repository and can start the full pipeline", async () => {
    vi.mocked(pickRepository).mockResolvedValue("/tmp/new");
    vi.mocked(addRecentRepo).mockResolvedValue([
      { path: "/tmp/new", openedAt: "2026-04-22T12:30:00Z" },
    ]);

    render(<Repository />);
    fireEvent.click(screen.getByRole("button", { name: "Open Repository…" }));

    await waitFor(() => expect(useUIStore.getState().activeRepo).toBe("/tmp/new"));
    expect(useUIStore.getState().recentRepos).toEqual([
      { path: "/tmp/new", openedAt: "2026-04-22T12:30:00Z" },
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Run Pipeline" }));
    expect(runManagedPipeline).toHaveBeenCalledWith("/tmp/new");
  });

  it("Repository falls back to the generic status message when index status loading fails", async () => {
    vi.mocked(readIndexStatus).mockRejectedValueOnce(new Error("missing"));

    render(<Repository />);
    await waitFor(() =>
      expect(screen.getByText("Select a repository to inspect index status.")).toBeInTheDocument(),
    );
  });

  it("Memory Map empty state runs index directly", async () => {
    render(<MemoryMapView />);

    await waitFor(() =>
      expect(screen.getByText("No memory map found")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Run Index" }));
    expect(runIndex).toHaveBeenCalledWith("/tmp/repo");
  });

  it("RAG empty state runs index directly", async () => {
    render(<RagView />);

    await waitFor(() =>
      expect(screen.getByText("No repository index found")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Run Index" }));
    expect(runIndex).toHaveBeenCalledWith("/tmp/repo");
  });

  it("RAG shows the no-repo and status-load-failure fallbacks", async () => {
    act(() => {
      useUIStore.setState({
        activeRepo: null,
        activeSection: "repository",
        recentRepos: [],
        artifactsVersion: 0,
      });
    });
    const { rerender } = render(<RagView />);
    expect(screen.getByText("Open a repository to search its index.")).toBeInTheDocument();

    act(() => {
      useUIStore.setState({
        activeRepo: "/tmp/repo",
        activeSection: "repository",
        recentRepos: [],
        artifactsVersion: 0,
      });
    });
    vi.mocked(readIndexStatus).mockRejectedValueOnce(new Error("missing"));
    rerender(<RagView />);
    await waitFor(() =>
      expect(screen.getByText("No repository index found")).toBeInTheDocument(),
    );
  });

  it("RAG searches with Enter, clamps topN, and renders results", async () => {
    vi.mocked(readIndexStatus).mockResolvedValue({
      has_index: true,
      has_memory_map: false,
      index_dir: "/tmp/repo/.idx",
      memory_map_path: null,
      active_run_id: null,
      active_run_mode: null,
    });
    vi.mocked(ragSearch).mockResolvedValue({
      hits: [{ file: "src/auth.ts", line: 7, score: 0.9876, content: "login()" }],
      error: null,
    });

    render(<RagView />);
    const query = await screen.findByPlaceholderText(/Search the repository index/i);
    fireEvent.change(query, { target: { value: "login" } });
    fireEvent.change(screen.getByTitle("Top-N results"), { target: { value: "99" } });
    fireEvent.keyDown(query, { key: "Enter" });

    await waitFor(() =>
      expect(ragSearch).toHaveBeenCalledWith("/tmp/repo", "login", 50),
    );
    expect(screen.getByText(/src\/auth\.ts:7/)).toBeInTheDocument();
    expect(screen.getByText("0.988")).toBeInTheDocument();
    expect(screen.getByText("login()")).toBeInTheDocument();
  });

  it("RAG shows errors, empty results, and index-in-progress states", async () => {
    const { rerender } = render(<RagView />);
    await waitFor(() =>
      expect(screen.getByText("No repository index found")).toBeInTheDocument(),
    );

    vi.mocked(readIndexStatus).mockResolvedValue({
      has_index: true,
      has_memory_map: false,
      index_dir: "/tmp/repo/.idx",
      memory_map_path: null,
      active_run_id: null,
      active_run_mode: null,
    });
    vi.mocked(ragSearch).mockResolvedValueOnce({ hits: [], error: "stale index" });
    act(() => {
      useUIStore.getState().bumpArtifactsVersion();
    });
    rerender(<RagView />);

    const query = await screen.findByPlaceholderText(/Search the repository index/i);
    fireEvent.change(query, { target: { value: "auth" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText("Search failed")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: "Run Index" }).at(-1)!);
    expect(runIndex).toHaveBeenCalledWith("/tmp/repo");

    vi.mocked(ragSearch).mockResolvedValueOnce({ hits: [], error: null });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText("No results.")).toBeInTheDocument());

    act(() => {
      usePipelineStore.setState({ status: "running", totalSteps: 1 });
    });
    rerender(<RagView />);
    expect(screen.getByText("Indexing repository…")).toBeInTheDocument();
  });
});
