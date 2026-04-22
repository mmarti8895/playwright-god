import { invokeCommand } from "@/lib/tauri";
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
  return invokeCommand<MemoryMap | null>("read_memory_map", { repo });
}

export async function readFlowGraph(repo: string): Promise<FlowGraph | null> {
  return invokeCommand<FlowGraph | null>("read_flow_graph", { repo });
}

export async function readCoverage(repo: string): Promise<CoverageReport | null> {
  return invokeCommand<CoverageReport | null>("read_coverage", { repo });
}

export async function readIndexStatus(repo: string): Promise<IndexStatus> {
  return invokeCommand<IndexStatus>("read_index_status", { repo });
}

export async function ragSearch(
  repo: string,
  query: string,
  topN = 10,
): Promise<RagSearchResult> {
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
