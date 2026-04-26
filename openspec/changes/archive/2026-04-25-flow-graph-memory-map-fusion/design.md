## Context

The current Flow Graph UI renders nodes from `flow_graph.json` with dagre layout, but many repositories produce sparse edges and route-heavy stacks that appear disconnected. The Memory Map view already contains useful grouping context (feature areas, file membership, chunk counts) that is not currently represented in the Flow Graph.

This change introduces a fused graph view that combines flow and memory-map structures into one graph model, so users can trace relationships across routes, actions, files, and feature areas. The desktop shell must remain local-first and CLI-backed; no hosted graph service is in scope.

## Goals / Non-Goals

**Goals:**
- Eliminate "isolated route stacks" by adding meaningful interconnectivity derived from memory-map relationships.
- Define a deterministic graph-composition model (stable IDs, typed nodes, typed edges) from existing artifacts.
- Keep the viewer performant for medium-sized repos by defaulting to in-memory composition and allowing an optional embedded graph-cache path if needed.
- Provide filter and layering controls that make fused graphs readable instead of visually noisy.
- Specify testable behavior for missing artifacts, partial artifacts, and graph rendering.

**Non-Goals:**
- Replacing the existing crawler/indexer pipeline with a mandatory graph database dependency.
- Introducing cloud graph infrastructure or remote synchronization.
- Building a full graph query language UI in this change.

## Decisions

### Decision: Compose a fused graph DTO at read time
Create a unified graph DTO from `flow_graph.json` + `memory_map.json` with stable prefixed node IDs (`route:`, `action:`, `file:`, `feature:`) and typed edges (`calls`, `handled_by`, `in_file`, `in_feature`, `evidence_for`).

Alternatives considered:
- Render two independent graphs side-by-side. Rejected because it does not solve cross-entity traversal.
- Modify only layout parameters on existing flow nodes. Rejected because layout-only changes cannot create missing connectivity.

### Decision: Keep in-memory composition as the default implementation
Frontend or desktop backend composition remains default and required. Optional local graph-cache materialization (DuckDB/Kuzu) is only enabled behind a feature/config gate when node/edge volume exceeds thresholds.

Alternatives considered:
- Require embedded graph DB for all repositories. Rejected to avoid new hard dependency and install friction.
- Never allow a graph cache. Rejected because very large repos may require indexed traversal for responsive filtering.

### Decision: Add viewer layering + relation filters
Flow Graph will expose layer toggles (routes/actions/files/features) and relation toggles to reduce clutter while preserving connectivity.

Alternatives considered:
- Only global text filter. Rejected because it is insufficient for dense multi-entity graphs.

### Decision: Use graceful degradation for missing artifacts
If one artifact is missing, render the available subgraph and show actionable status messaging rather than a hard failure.

Alternatives considered:
- Block rendering until both artifacts exist. Rejected as unnecessarily strict and less helpful during iterative indexing.

## Risks / Trade-offs

- [Risk] Fused graphs can overwhelm the UI with too many nodes/edges. -> Mitigation: layer toggles, edge-type toggles, and truncation warnings with clear limits.
- [Risk] Heuristic linking between flow evidence and memory-map files can mis-associate nodes. -> Mitigation: deterministic matching rules, explicit provenance metadata, and tests with representative fixtures.
- [Risk] Optional graph-cache path may diverge from in-memory results. -> Mitigation: single canonical fused DTO schema and parity tests for cache vs in-memory outputs.

## Migration Plan

1. Define fused graph types in desktop artifact-reading layer and implement deterministic composition.
2. Update Flow Graph section to consume fused graph data and add layer/relation controls.
3. Add optional graph-cache adapter abstraction (disabled by default) and threshold-based activation guard.
4. Add/extend tests for composition, fallback states, filtering, and rendering behavior.
5. Validate with desktop unit tests and Rust tests where composition lives.

Rollback strategy:
- Disable fused composition path and restore legacy flow-only rendering; no persisted data migration is required.

## Open Questions

- Which embedded option should be preferred if cache mode is enabled first: Kuzu, DuckDB+extensions, or pure SQLite adjacency tables?
- Should layer/relation toggle state persist per repository or per app session?