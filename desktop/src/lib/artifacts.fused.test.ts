import { describe, expect, it } from "vitest";
import {
  composeFusedGraph,
  type FlowGraph,
  type MemoryMap,
} from "@/lib/artifacts";

const FLOW: FlowGraph = {
  nodes: [
    {
      id: "route.login",
      kind: "route",
      method: "GET",
      path: "/login",
      handler: "src/auth.ts:login",
      evidence: [{ file: "src/auth.ts", line_range: [10, 20] }],
    },
    {
      id: "action.submit",
      kind: "action",
      role: "submit",
      file: "src/auth.ts",
      line: 24,
      evidence: [{ file: "src/auth.ts", line_range: [24, 30] }],
    },
  ],
  edges: [{ source: "route.login", target: "action.submit" }],
};

const MEMORY: MemoryMap = {
  files: [{ path: "src/auth.ts", chunk_count: 3, feature: "Auth" }],
  features: [{ name: "Auth", files: ["src/auth.ts"] }],
};

describe("composeFusedGraph", () => {
  it("creates fused route/action/file/feature graph with typed edges", () => {
    const graph = composeFusedGraph(FLOW, MEMORY);

    expect(graph.nodes.map((n) => n.id)).toEqual(
      expect.arrayContaining([
        "route:route.login",
        "action:action.submit",
        "file:src/auth.ts",
        "feature:Auth",
      ]),
    );
    expect(graph.edges.map((e) => e.relation)).toEqual(
      expect.arrayContaining(["flow", "handled_by", "evidence_for", "in_feature"]),
    );
    expect(graph.meta.missingSources).toEqual([]);
    expect(graph.meta.fallback).toBe(false);
  });

  it("reports fallback metadata when one source artifact is missing", () => {
    const graph = composeFusedGraph(FLOW, null);
    expect(graph.meta.fallback).toBe(true);
    expect(graph.meta.missingSources).toEqual(["memory_map"]);
  });

  it("keeps stable node and edge identities for unchanged inputs", () => {
    const first = composeFusedGraph(FLOW, MEMORY);
    const second = composeFusedGraph(FLOW, MEMORY);
    expect(first.nodes.map((n) => n.id)).toEqual(second.nodes.map((n) => n.id));
    expect(first.edges.map((e) => e.id)).toEqual(second.edges.map((e) => e.id));
  });

  it("preserves DTO parity between in-memory and graph-cache modes", () => {
    const mem = composeFusedGraph(FLOW, MEMORY, { forceMode: "in-memory" });
    const cache = composeFusedGraph(FLOW, MEMORY, { forceMode: "graph-cache" });

    expect(mem.nodes).toEqual(cache.nodes);
    expect(mem.edges).toEqual(cache.edges);
    expect(mem.meta.mode).toBe("in-memory");
    expect(cache.meta.mode).toBe("graph-cache");
  });
});
