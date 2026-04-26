import { useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import dagre from "dagre";
import clsx from "clsx";
import { Panel } from "@/components/Panel";
import { useUIStore } from "@/state/ui";
import {
  readFusedFlowGraph,
  type FusedGraph,
  type FusedGraphEdge,
  type FusedGraphLayer,
  type FusedGraphNode,
  type FusedGraphRelation,
} from "@/lib/artifacts";

const MAX_NODES = 500;
const NODE_WIDTH = 200;
const NODE_HEIGHT = 56;

interface NodeData {
  label: string;
  sublabel?: string;
  layer: FusedGraphLayer;
  source: FusedGraphNode;
  dimmed: boolean;
}

const nodeTypes = {
  route: FlowNodeView,
  action: FlowNodeView,
  file: FlowNodeView,
  feature: FlowNodeView,
};

const ALL_LAYERS: FusedGraphLayer[] = ["route", "action", "file", "feature"];
const ALL_RELATIONS: FusedGraphRelation[] = [
  "flow",
  "handled_by",
  "evidence_for",
  "in_feature",
];

function defaultLayerState(): Record<FusedGraphLayer, boolean> {
  return {
    route: true,
    action: true,
    file: true,
    feature: true,
  };
}

function defaultRelationState(): Record<FusedGraphRelation, boolean> {
  return {
    flow: true,
    handled_by: true,
    evidence_for: true,
    in_feature: true,
  };
}

export function FlowGraphView() {
  const repo = useUIStore((s) => s.activeRepo);
  const version = useUIStore((s) => s.artifactsVersion);
  const consumeFocus = useUIStore((s) => s.consumeFlowGraphFocus);
  const [data, setData] = useState<FusedGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<FusedGraphNode | null>(null);
  const [visibleLayers, setVisibleLayers] = useState(defaultLayerState);
  const [visibleRelations, setVisibleRelations] = useState(defaultRelationState);

  useEffect(() => {
    if (!repo) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void readFusedFlowGraph(repo)
      .then((fg) => {
        if (!cancelled) {
          setData(fg);
          setLoading(false);
          setSelected(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setLoading(false);
          setSelected(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repo, version]);

  useEffect(() => {
    const focus = consumeFocus();
    if (!focus) return;
    setFilter(focus.query);
  }, [consumeFocus]);

  const total = data?.nodes?.length ?? 0;
  const truncated = total > MAX_NODES;
  const visibleNodes = useMemo(
    () => (data ? data.nodes.slice(0, MAX_NODES) : []),
    [data],
  );
  const visibleIds = useMemo(
    () => new Set(visibleNodes.map((n) => n.id)),
    [visibleNodes],
  );

  const { nodes, edges } = useMemo(
    () =>
      buildGraph(
        visibleNodes,
        data?.edges ?? [],
        visibleIds,
        filter.trim(),
        visibleLayers,
        visibleRelations,
      ),
    [visibleNodes, data, visibleIds, filter, visibleLayers, visibleRelations],
  );

  if (!repo) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">
          Open a repository to view its flow graph.
        </div>
      </Panel>
    );
  }

  if (loading) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="text-[13px] text-ink-500">Loading flow graph…</div>
      </Panel>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <Panel className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <div className="text-[15px] font-medium text-ink-700">No flow graph found</div>
        <div className="max-w-md text-[13px] text-ink-500">
          Run <span className="font-mono">playwright-god graph extract</span> to write a
          <span className="font-mono"> flow_graph.json</span> at the repository root.
        </div>
      </Panel>
    );
  }

  return (
    <Panel className="flex h-full min-h-0 flex-col gap-3 overflow-hidden p-3">
      <header className="flex items-center justify-between gap-3 px-2">
        <div className="text-[12px] text-ink-500">
          <span className="font-medium text-ink-700">{total}</span> nodes ·
          <span className="ml-1 font-medium text-ink-700">{data.edges?.length ?? 0}</span> edges ·
          <span className="ml-1 font-medium text-ink-700">{data.meta.mode}</span>
        </div>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter nodes…"
          className="w-72 rounded-md border border-ink-200 bg-white px-2 py-1 text-[12px]
                     focus:border-ink-400 focus:outline-none"
        />
      </header>

      {data.meta.missingSources.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
          Partial graph: missing {data.meta.missingSources.join(", ")}. Run indexing/graph extraction to
          restore full connectivity.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4 px-2">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="text-ink-500">Layers:</span>
          {ALL_LAYERS.map((layer) => (
            <label key={layer} className="inline-flex items-center gap-1 text-ink-700">
              <input
                type="checkbox"
                checked={visibleLayers[layer]}
                onChange={(e) =>
                  setVisibleLayers((prev) => ({ ...prev, [layer]: e.target.checked }))
                }
              />
              {layer}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-2 text-[12px]">
          <span className="text-ink-500">Relations:</span>
          {ALL_RELATIONS.map((relation) => (
            <label key={relation} className="inline-flex items-center gap-1 text-ink-700">
              <input
                type="checkbox"
                checked={visibleRelations[relation]}
                onChange={(e) =>
                  setVisibleRelations((prev) => ({ ...prev, [relation]: e.target.checked }))
                }
              />
              {relation}
            </label>
          ))}
        </div>
      </div>

      {truncated && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
          Showing top {MAX_NODES} of {total} nodes; narrow the view with the filter.
        </div>
      )}

      <div className="flex flex-1 min-h-0 gap-3">
        <div className="flex-1 min-w-0 rounded-xl border border-ink-200/60 bg-white">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
            onNodeClick={(_, node) => setSelected((node.data as NodeData).source)}
          >
            <Background gap={16} color="#e5e5e5" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>

        {selected && <SidePanel node={selected} onClose={() => setSelected(null)} />}
      </div>
    </Panel>
  );
}

function FlowNodeView({ data }: NodeProps<NodeData>) {
  const isRoute = data.layer === "route";
  const isAction = data.layer === "action";
  const isFile = data.layer === "file";
  const isFeature = data.layer === "feature";
  return (
    <div
      className={clsx(
        "shadow-sm border text-[12px] leading-tight transition-opacity",
        data.dimmed ? "opacity-30" : "opacity-100",
        isRoute && "rounded-lg bg-white border-ink-300 px-3 py-2",
        isFeature && "rounded-lg bg-violet-50 border-violet-300 px-3 py-2",
        isFile && "rounded-lg bg-sky-50 border-sky-300 px-3 py-2",
        isAction && "rounded-full bg-amber-50 border-amber-300 px-3 py-1",
      )}
      style={{ width: NODE_WIDTH }}
    >
      <div className="font-medium text-ink-800 truncate">{data.label}</div>
      {data.sublabel && (
        <div className="font-mono text-[10px] text-ink-500 truncate">{data.sublabel}</div>
      )}
    </div>
  );
}

function SidePanel({ node, onClose }: { node: FusedGraphNode; onClose: () => void }) {
  return (
    <aside className="w-72 shrink-0 overflow-y-auto rounded-xl border border-ink-200/60 bg-white p-3">
      <header className="mb-2 flex items-center justify-between">
        <span className="rounded bg-ink-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-700">
          {node.layer}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded px-2 text-[12px] text-ink-500 hover:bg-ink-100"
        >
          ×
        </button>
      </header>
      <div className="font-mono text-[12px] text-ink-800 break-all">{node.id}</div>
      {node.sublabel && <div className="mt-3 font-mono text-[11px] text-ink-600">{node.sublabel}</div>}
    </aside>
  );
}

function buildGraph(
  fusedNodes: FusedGraphNode[],
  fusedEdges: FusedGraphEdge[],
  visibleIds: Set<string>,
  filter: string,
  visibleLayers: Record<FusedGraphLayer, boolean>,
  visibleRelations: Record<FusedGraphRelation, boolean>,
): { nodes: Node<NodeData>[]; edges: Edge[] } {
  const f = filter.toLowerCase();
  const matches = (n: FusedGraphNode) =>
    !f ||
    n.id.toLowerCase().includes(f) ||
    n.label.toLowerCase().includes(f) ||
    (n.sublabel ?? "").toLowerCase().includes(f);

  const filteredNodes = fusedNodes.filter((n) => visibleLayers[n.layer]);
  const filteredNodeIds = new Set(filteredNodes.map((n) => n.id));

  // dagre layout
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 60 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of filteredNodes) g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const e of fusedEdges) {
    if (!visibleRelations[e.relation]) continue;
    if (visibleIds.has(e.source) && visibleIds.has(e.target) && filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }
  dagre.layout(g);

  const nodes: Node<NodeData>[] = filteredNodes.map((n) => {
    const pos = g.node(n.id);
    const data: NodeData = {
      label: n.label,
      sublabel: n.sublabel,
      layer: n.layer,
      source: n,
      dimmed: !matches(n),
    };
    return {
      id: n.id,
      type: n.layer,
      data,
      position: { x: pos?.x ?? 0, y: pos?.y ?? 0 },
      draggable: false,
    };
  });

  const edges: Edge[] = fusedEdges
    .map((e, i) => {
      const s = e.source;
      const t = e.target;
      if (!visibleRelations[e.relation]) return null;
      if (!visibleIds.has(s) || !visibleIds.has(t)) return null;
      if (!filteredNodeIds.has(s) || !filteredNodeIds.has(t)) return null;
      return {
        id: `e${i}`,
        source: s,
        target: t,
        type: "smoothstep",
        style: { stroke: "#9ca3af", strokeWidth: 1 },
      } as Edge;
    })
    .filter((e): e is Edge => e !== null);

  return { nodes, edges };
}
