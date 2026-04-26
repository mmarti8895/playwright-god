import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FlowGraphView } from "@/sections/FlowGraph";
import { useUIStore } from "@/state/ui";

vi.mock("reactflow", () => ({
  __esModule: true,
  default: ({ nodes, edges }: { nodes: unknown[]; edges: unknown[] }) => (
    <div>
      <div data-testid="rf-nodes">{nodes.length}</div>
      <div data-testid="rf-edges">{edges.length}</div>
    </div>
  ),
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
}));

vi.mock("@/lib/artifacts", async () => {
  const actual = await vi.importActual<typeof import("@/lib/artifacts")>(
    "@/lib/artifacts",
  );
  return {
    ...actual,
    readFusedFlowGraph: vi.fn(),
  };
});

import { readFusedFlowGraph } from "@/lib/artifacts";

const GRAPH = {
  nodes: [
    { id: "route:r1", layer: "route", label: "GET /login" },
    { id: "action:a1", layer: "action", label: "submit" },
    { id: "file:src/auth.ts", layer: "file", label: "src/auth.ts" },
    { id: "feature:Auth", layer: "feature", label: "Auth" },
  ],
  edges: [
    {
      id: "flow:route:r1->action:a1",
      source: "route:r1",
      target: "action:a1",
      relation: "flow",
    },
    {
      id: "handled_by:route:r1->file:src/auth.ts",
      source: "route:r1",
      target: "file:src/auth.ts",
      relation: "handled_by",
    },
    {
      id: "in_feature:file:src/auth.ts->feature:Auth",
      source: "file:src/auth.ts",
      target: "feature:Auth",
      relation: "in_feature",
    },
  ],
  meta: {
    mode: "in-memory",
    missingSources: [] as string[],
    fallback: false,
  },
};

describe("FlowGraphView", () => {
  beforeEach(() => {
    vi.mocked(readFusedFlowGraph).mockReset();
    vi.mocked(readFusedFlowGraph).mockResolvedValue(GRAPH as never);
    useUIStore.setState({
      activeRepo: "/tmp/repo",
      artifactsVersion: 0,
      flowGraphFocus: null,
    });
  });

  it("shows partial-source notice and mode label", async () => {
    vi.mocked(readFusedFlowGraph).mockResolvedValueOnce({
      ...GRAPH,
      meta: {
        mode: "graph-cache",
        missingSources: ["memory_map"],
        fallback: true,
      },
    } as never);

    render(<FlowGraphView />);
    await waitFor(() => expect(screen.getByText(/Partial graph:/)).toBeInTheDocument());
    expect(screen.getByText(/graph-cache/)).toBeInTheDocument();
  });

  it("applies layer and relation toggles to graph visibility", async () => {
    render(<FlowGraphView />);
    await waitFor(() => expect(screen.getByTestId("rf-nodes")).toHaveTextContent("4"));
    expect(screen.getByTestId("rf-edges")).toHaveTextContent("3");

    fireEvent.click(screen.getByRole("checkbox", { name: "file" }));
    await waitFor(() => expect(screen.getByTestId("rf-nodes")).toHaveTextContent("3"));

    fireEvent.click(screen.getByRole("checkbox", { name: "in_feature" }));
    await waitFor(() => expect(screen.getByTestId("rf-edges")).toHaveTextContent("1"));
  });

  it("consumes one-time focus handoff and sets filter", async () => {
    useUIStore.setState({ flowGraphFocus: { query: "src/auth.ts" } });
    render(<FlowGraphView />);

    const input = await screen.findByPlaceholderText("Filter nodes…");
    expect(input).toHaveValue("src/auth.ts");
    expect(useUIStore.getState().flowGraphFocus).toBeNull();
  });
});
