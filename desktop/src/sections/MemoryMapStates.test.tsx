import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    readMemoryMap: vi.fn(),
    readIndexStatus: vi.fn(),
    ragSearch: vi.fn(),
  };
});

import { readIndexStatus, readMemoryMap } from "@/lib/artifacts";

describe("MemoryMap and Rag states", () => {
  beforeEach(() => {
    vi.mocked(readMemoryMap).mockReset();
    vi.mocked(readIndexStatus).mockReset();
    usePipelineStore.getState().reset();
    useUIStore.setState({
      activeRepo: "/tmp/repo",
      artifactsVersion: 0,
    });
  });

  it("MemoryMap shows indexing state during an index-only run", async () => {
    vi.mocked(readMemoryMap).mockResolvedValue(null);
    vi.mocked(readIndexStatus).mockResolvedValue({
      has_index: false,
      has_memory_map: false,
      index_dir: null,
      memory_map_path: null,
      active_run_id: "run-1",
      active_run_mode: "index-only",
    });
    usePipelineStore.setState({ status: "running", totalSteps: 1 });

    render(<MemoryMapView />);
    await waitFor(() => expect(screen.getByText("Indexing repository…")).toBeInTheDocument());
  });

  it("MemoryMap covers no-repo, loading, and persisted-index-empty states", async () => {
    act(() => {
      useUIStore.setState({ activeRepo: null, artifactsVersion: 0 });
    });
    const { rerender } = render(<MemoryMapView />);
    expect(
      screen.getByText("Open a repository from the Repository tab to view its memory map."),
    ).toBeInTheDocument();

    act(() => {
      useUIStore.setState({ activeRepo: "/tmp/repo", artifactsVersion: 0 });
    });
    vi.mocked(readMemoryMap).mockImplementation(() => new Promise(() => {}));
    vi.mocked(readIndexStatus).mockImplementation(() => new Promise(() => {}));
    rerender(<MemoryMapView />);
    await waitFor(() => expect(screen.getByText("Loading memory map…")).toBeInTheDocument());

    vi.mocked(readMemoryMap).mockResolvedValue(null);
    vi.mocked(readIndexStatus).mockResolvedValue({
      has_index: true,
      has_memory_map: false,
      index_dir: "/tmp/repo/.idx",
      memory_map_path: null,
      active_run_id: null,
      active_run_mode: null,
    });
    act(() => {
      useUIStore.getState().bumpArtifactsVersion();
    });
    rerender(<MemoryMapView />);
    await waitFor(() =>
      expect(
        screen.getByText(/A persisted index exists, but no memory map artifact was found yet/),
      ).toBeInTheDocument(),
    );
  });

  it("MemoryMap renders grouped files when data is present", async () => {
    vi.mocked(readMemoryMap).mockResolvedValue({
      total_files: 1,
      total_chunks: 2,
      files: [{ path: "src/app.ts", chunk_count: 2 }],
      features: [{ name: "Auth", files: ["src/app.ts"] }],
    });
    vi.mocked(readIndexStatus).mockResolvedValue({
      has_index: true,
      has_memory_map: true,
      index_dir: "/tmp/repo/.idx",
      memory_map_path: "/tmp/repo/.idx/memory_map.json",
      active_run_id: null,
      active_run_mode: null,
    });

    render(<MemoryMapView />);
    await waitFor(() => expect(screen.getByText("Auth")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /auth/i })).toHaveTextContent("1 file");
    fireEvent.click(screen.getByRole("button", { name: /auth/i }));
    await waitFor(() => expect(screen.getByText("src/app.ts")).toBeInTheDocument());
    expect(screen.getByText("2 chunks")).toBeInTheDocument();
  });

  it("MemoryMap groups files by directory when features are absent", async () => {
    vi.mocked(readMemoryMap).mockResolvedValue({
      schema_version: "2",
      total_files: 2,
      total_chunks: 2,
      languages: { ts: 1 },
      files: [
        { path: "README.md", chunk_count: null },
        { path: "src/app.ts", chunk_count: 2 },
      ],
      features: [],
    });
    vi.mocked(readIndexStatus).mockResolvedValue({
      has_index: true,
      has_memory_map: true,
      index_dir: "/tmp/repo/.idx",
      memory_map_path: "/tmp/repo/.idx/memory_map.json",
      active_run_id: null,
      active_run_mode: null,
    });

    render(<MemoryMapView />);
    await waitFor(() => expect(screen.getByText("schema 2")).toBeInTheDocument());
    expect(screen.getByText("ts · 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\(root\)/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^src/i })).toBeInTheDocument();
  });

  it("MemoryMap falls back to the empty state when loading artifacts fails", async () => {
    vi.mocked(readMemoryMap).mockRejectedValueOnce(new Error("bad artifact"));
    vi.mocked(readIndexStatus).mockResolvedValueOnce({
      has_index: false,
      has_memory_map: false,
      index_dir: null,
      memory_map_path: null,
      active_run_id: null,
      active_run_mode: null,
    });

    render(<MemoryMapView />);
    await waitFor(() => expect(screen.getByText("No memory map found")).toBeInTheDocument());
  });

  it("Rag shows checking state before the index status resolves", () => {
    vi.mocked(readIndexStatus).mockImplementation(() => new Promise(() => {}));
    render(<RagView />);
    expect(screen.getByText("Checking index status…")).toBeInTheDocument();
  });
});
