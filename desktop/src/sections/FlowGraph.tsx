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
  readFlowGraph,
  type FlowEdge,
  type FlowGraph,
  type FlowNode,
} from "@/lib/artifacts";

const MAX_NODES = 500;
const NODE_WIDTH = 200;
const NODE_HEIGHT = 56;

interface NodeData {
  label: string;
  sublabel?: string;
  kind: FlowNode["kind"];
  source: FlowNode;
  dimmed: boolean;
}

const nodeTypes = {
  route: FlowNodeView,
  view: FlowNodeView,
  action: FlowNodeView,
};

export function FlowGraphView() {
  const repo = useUIStore((s) => s.activeRepo);
  const version = useUIStore((s) => s.artifactsVersion);
  const [data, setData] = useState<FlowGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<FlowNode | null>(null);

  useEffect(() => {
    if (!repo) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void readFlowGraph(repo).then((fg) => {
      if (!cancelled) {
        setData(fg);
        setLoading(false);
        setSelected(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [repo, version]);

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
    () => buildGraph(visibleNodes, data?.edges ?? [], visibleIds, filter.trim()),
    [visibleNodes, data, visibleIds, filter],
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
          <span className="ml-1 font-medium text-ink-700">{data.edges?.length ?? 0}</span> edges
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
  const isRoute = data.kind === "route";
  const isAction = data.kind === "action";
  return (
    <div
      className={clsx(
        "shadow-sm border text-[12px] leading-tight transition-opacity",
        data.dimmed ? "opacity-30" : "opacity-100",
        isRoute && "rounded-lg bg-white border-ink-300 px-3 py-2",
        data.kind === "view" && "rounded-lg bg-violet-50 border-violet-300 px-3 py-2",
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

function SidePanel({ node, onClose }: { node: FlowNode; onClose: () => void }) {
  const evidence = node.evidence ?? [];
  return (
    <aside className="w-72 shrink-0 overflow-y-auto rounded-xl border border-ink-200/60 bg-white p-3">
      <header className="mb-2 flex items-center justify-between">
        <span className="rounded bg-ink-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-700">
          {node.kind}
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
      {evidence.length > 0 ? (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ink-500">
            Evidence
          </div>
          <ul className="flex flex-col gap-1">
            {evidence.map((e, i) => (
              <li key={i} className="font-mono text-[11px] text-ink-700">
                {e.file}:{e.line_range?.[0]}–{e.line_range?.[1]}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="mt-3 text-[11px] text-ink-400">No evidence recorded.</div>
      )}
    </aside>
  );
}

function buildGraph(
  flowNodes: FlowNode[],
  flowEdges: FlowEdge[],
  visibleIds: Set<string>,
  filter: string,
): { nodes: Node<NodeData>[]; edges: Edge[] } {
  const f = filter.toLowerCase();
  const matches = (n: FlowNode) =>
    !f ||
    n.id.toLowerCase().includes(f) ||
    nodeLabel(n).toLowerCase().includes(f) ||
    nodeSublabel(n).toLowerCase().includes(f);

  // dagre layout
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 60 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of flowNodes) g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const e of flowEdges) {
    const s = e.source ?? e.source_id ?? "";
    const t = e.target ?? e.target_id ?? "";
    if (visibleIds.has(s) && visibleIds.has(t)) g.setEdge(s, t);
  }
  dagre.layout(g);

  const nodes: Node<NodeData>[] = flowNodes.map((n) => {
    const pos = g.node(n.id);
    const data: NodeData = {
      label: nodeLabel(n),
      sublabel: nodeSublabel(n),
      kind: n.kind,
      source: n,
      dimmed: !matches(n),
    };
    return {
      id: n.id,
      type: n.kind,
      data,
      position: { x: pos?.x ?? 0, y: pos?.y ?? 0 },
      draggable: false,
    };
  });

  const edges: Edge[] = flowEdges
    .map((e, i) => {
      const s = e.source ?? e.source_id ?? "";
      const t = e.target ?? e.target_id ?? "";
      if (!visibleIds.has(s) || !visibleIds.has(t)) return null;
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

function nodeLabel(n: FlowNode): string {
  if (n.kind === "route") return `${n.method} ${n.path}`;
  if (n.kind === "view") return n.symbol || "default";
  return n.role || "(action)";
}
function nodeSublabel(n: FlowNode): string {
  if (n.kind === "route") return n.handler ?? "";
  if (n.kind === "view") return n.file ?? "";
  return `${n.file}:${n.line}`;
}
