import { invokeCommand, inTauri } from "@/lib/tauri";
import type { PipelineMode } from "@/lib/pipeline";

export interface MemoryMapFile {
  path: string;
  chunk_count?: number | null;
  feature?: string | null;
}

export interface MemoryMapFeature {
  name?: string;
  area?: string;
  files?: string[];
}

export interface MemoryMap {
  schema_version?: string | number;
  total_files?: number;
  total_chunks?: number;
  languages?: Record<string, number>;
  files?: MemoryMapFile[];
  features?: MemoryMapFeature[];
}

export interface FlowEvidence {
  file?: string;
  line_range?: [number, number];
}

export interface FlowNode {
  id: string;
  kind: "route" | "view" | "action";
  method?: string;
  path?: string;
  handler?: string;
  symbol?: string;
  file?: string;
  role?: string;
  line?: number;
  evidence?: FlowEvidence[];
}

export interface FlowEdge {
  source?: string;
  target?: string;
  source_id?: string;
  target_id?: string;
}

export interface FlowGraph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export type FusedGraphLayer = "route" | "action" | "file" | "feature";
export type FusedGraphRelation =
  | "flow"
  | "handled_by"
  | "evidence_for"
  | "in_feature";

export interface FusedGraphNode {
  id: string;
  layer: FusedGraphLayer;
  label: string;
  sublabel?: string;
}

export interface FusedGraphEdge {
  id: string;
  source: string;
  target: string;
  relation: FusedGraphRelation;
}

export type FusedGraphSource = "flow_graph" | "memory_map";
export type FusedGraphMode = "in-memory" | "graph-cache";

export interface FusedGraphMeta {
  mode: FusedGraphMode;
  missingSources: FusedGraphSource[];
  fallback: boolean;
}

export interface FusedGraph {
  nodes: FusedGraphNode[];
  edges: FusedGraphEdge[];
  meta: FusedGraphMeta;
}

export interface FusedGraphComposeOptions {
  graphCacheEnabled?: boolean;
  graphCacheNodeThreshold?: number;
  graphCacheEdgeThreshold?: number;
  forceMode?: FusedGraphMode;
}

export interface CoverageTotals {
  total_files: number;
  total_lines: number;
  covered_lines: number;
  percent: number;
}

export interface CoverageFile {
  total_lines: number;
  covered_lines: number;
  percent: number;
  missing_line_ranges?: Array<[number, number]>;
}

export interface CoverageRouteDetail {
  route_id: string;
  method: string;
  path: string;
  covered: boolean;
  handler_files: string[];
}

export interface CoverageRoutes {
  total: number;
  covered: string[];
  details: CoverageRouteDetail[];
}

export interface CoverageReport {
  generated_at?: string;
  totals?: CoverageTotals;
  files?: Record<string, CoverageFile>;
  routes?: CoverageRoutes;
}

export interface SearchHit {
  file: string;
  line?: number | null;
  score: number;
  content: string;
}

export interface RagSearchResult {
  hits: SearchHit[];
  error: string | null;
}

export interface IndexStatus {
  has_index: boolean;
  has_memory_map: boolean;
  index_dir: string | null;
  memory_map_path: string | null;
  active_run_id: string | null;
  active_run_mode: PipelineMode | null;
}

export async function readMemoryMap(repo: string): Promise<MemoryMap | null> {
  if (!inTauri()) return null;
  return invokeCommand<MemoryMap | null>("read_memory_map", { repo });
}

export async function readFlowGraph(repo: string): Promise<FlowGraph | null> {
  if (!inTauri()) return null;
  return invokeCommand<FlowGraph | null>("read_flow_graph", { repo });
}

export async function readFusedFlowGraph(
  repo: string,
  options: FusedGraphComposeOptions = {},
): Promise<FusedGraph> {
  const [flowResult, memoryResult] = await Promise.allSettled([
    readFlowGraph(repo),
    readMemoryMap(repo),
  ]);

  const flow = flowResult.status === "fulfilled" ? flowResult.value : null;
  const memory = memoryResult.status === "fulfilled" ? memoryResult.value : null;

  return composeFusedGraph(flow, memory, options);
}

export async function readCoverage(repo: string): Promise<CoverageReport | null> {
  if (!inTauri()) return null;
  return invokeCommand<CoverageReport | null>("read_coverage", { repo });
}

export async function readIndexStatus(repo: string): Promise<IndexStatus> {
  if (!inTauri()) {
    return {
      has_index: false,
      has_memory_map: false,
      index_dir: null,
      memory_map_path: null,
      active_run_id: null,
      active_run_mode: null,
    };
  }
  return invokeCommand<IndexStatus>("read_index_status", { repo });
}

export async function ragSearch(
  repo: string,
  query: string,
  topN = 10,
): Promise<RagSearchResult> {
  if (!inTauri()) {
    return {
      hits: [],
      error: null,
    };
  }
  try {
    const hits = await invokeCommand<SearchHit[]>("rag_search", {
      repo,
      query,
      topN,
    });
    return { hits, error: null };
  } catch (error) {
    return {
      hits: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function flowNodeId(node: FlowNode): string {
  return node.kind === "route" ? `route:${node.id}` : `action:${node.id}`;
}

function fileNodeId(path: string): string {
  return `file:${path}`;
}

function featureNodeId(name: string): string {
  return `feature:${name}`;
}

function addNode(map: Map<string, FusedGraphNode>, node: FusedGraphNode) {
  if (!map.has(node.id)) map.set(node.id, node);
}

function addEdge(map: Map<string, FusedGraphEdge>, edge: Omit<FusedGraphEdge, "id">) {
  const id = `${edge.relation}:${edge.source}->${edge.target}`;
  if (!map.has(id)) map.set(id, { id, ...edge });
}

function flowNodeLabel(node: FlowNode): string {
  if (node.kind === "route") {
    const method = node.method ?? "?";
    const path = node.path ?? node.id;
    return `${method} ${path}`.trim();
  }
  return node.role ?? node.symbol ?? node.id;
}

function flowNodeSublabel(node: FlowNode): string {
  if (node.kind === "route") return node.handler ?? "";
  const filePart = node.file ?? "";
  return node.line != null && filePart ? `${filePart}:${node.line}` : filePart;
}

function createInMemoryFusedGraph(
  flow: FlowGraph | null,
  memory: MemoryMap | null,
  mode: FusedGraphMode,
): FusedGraph {
  const nodes = new Map<string, FusedGraphNode>();
  const edges = new Map<string, FusedGraphEdge>();
  const missingSources: FusedGraphSource[] = [];

  if (!flow) missingSources.push("flow_graph");
  if (!memory) missingSources.push("memory_map");

  if (flow) {
    const flowNodeMap = new Map<string, string>();
    for (const node of flow.nodes ?? []) {
      const id = flowNodeId(node);
      flowNodeMap.set(node.id, id);
      addNode(nodes, {
        id,
        layer: node.kind === "route" ? "route" : "action",
        label: flowNodeLabel(node),
        sublabel: flowNodeSublabel(node),
      });

      for (const evidence of node.evidence ?? []) {
        if (!evidence.file) continue;
        const fileId = fileNodeId(evidence.file);
        addNode(nodes, {
          id: fileId,
          layer: "file",
          label: evidence.file,
        });
        addEdge(edges, {
          source: id,
          target: fileId,
          relation: "evidence_for",
        });

        if (node.kind === "route") {
          addEdge(edges, {
            source: id,
            target: fileId,
            relation: "handled_by",
          });
        }
      }
    }

    for (const edge of flow.edges ?? []) {
      const sourceRaw = edge.source ?? edge.source_id;
      const targetRaw = edge.target ?? edge.target_id;
      if (!sourceRaw || !targetRaw) continue;
      const source = flowNodeMap.get(sourceRaw) ?? sourceRaw;
      const target = flowNodeMap.get(targetRaw) ?? targetRaw;
      addEdge(edges, {
        source,
        target,
        relation: "flow",
      });
    }
  }

  if (memory) {
    for (const file of memory.files ?? []) {
      const id = fileNodeId(file.path);
      addNode(nodes, {
        id,
        layer: "file",
        label: file.path,
        sublabel:
          file.chunk_count != null ? `${file.chunk_count} chunks` : undefined,
      });

      if (file.feature) {
        const featureId = featureNodeId(file.feature);
        addNode(nodes, { id: featureId, layer: "feature", label: file.feature });
        addEdge(edges, {
          source: id,
          target: featureId,
          relation: "in_feature",
        });
      }
    }

    for (const feature of memory.features ?? []) {
      const name = feature.name || feature.area;
      if (!name) continue;
      const featureId = featureNodeId(name);
      addNode(nodes, { id: featureId, layer: "feature", label: name });

      for (const filePath of feature.files ?? []) {
        const fileId = fileNodeId(filePath);
        addNode(nodes, { id: fileId, layer: "file", label: filePath });
        addEdge(edges, {
          source: fileId,
          target: featureId,
          relation: "in_feature",
        });
      }
    }
  }

  const orderedNodes = [...nodes.values()].sort((a, b) => a.id.localeCompare(b.id));
  const orderedEdges = [...edges.values()].sort((a, b) => a.id.localeCompare(b.id));

  return {
    nodes: orderedNodes,
    edges: orderedEdges,
    meta: {
      mode,
      missingSources,
      fallback: missingSources.length > 0,
    },
  };
}

export function composeFusedGraph(
  flow: FlowGraph | null,
  memory: MemoryMap | null,
  options: FusedGraphComposeOptions = {},
): FusedGraph {
  const preview = createInMemoryFusedGraph(flow, memory, "in-memory");
  const nodeThreshold = options.graphCacheNodeThreshold ?? 1500;
  const edgeThreshold = options.graphCacheEdgeThreshold ?? 3000;

  const useCacheMode =
    options.forceMode === "graph-cache" ||
    (options.forceMode !== "in-memory" &&
      !!options.graphCacheEnabled &&
      (preview.nodes.length >= nodeThreshold || preview.edges.length >= edgeThreshold));

  const mode: FusedGraphMode = useCacheMode ? "graph-cache" : "in-memory";
  return createInMemoryFusedGraph(flow, memory, mode);
}
