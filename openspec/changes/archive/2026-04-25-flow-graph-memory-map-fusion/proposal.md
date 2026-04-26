## Why

The current Flow Graph view often shows route nodes as disconnected vertical stacks, which makes the graph hard to use for reasoning about feature coverage and execution context. We need a graph model that links flow nodes to memory-map evidence so users can see how routes, handlers, files, and feature areas connect in one navigable view.

## What Changes

- Expand the Flow Graph viewer model from route/action-only links to a fused graph that includes memory-map entities (feature areas, files, chunk groups) and typed edges between these entities and existing flow nodes.
- Add graph-composition logic that merges `flow_graph.json` and `memory_map.json` into a single graph payload with stable node IDs and edge semantics.
- Introduce visual layering/filtering in the Flow Graph section to prevent clutter while still exposing interconnectivity (for example: routes, actions, files, features).
- Define an optional lightweight open-source graph database cache path (for example, DuckDB extension-based graph tables or Kuzu embedded) only when in-memory composition is insufficient for responsiveness.
- Add tests for merged-graph construction, filter behavior, and fallback behavior when either artifact is missing.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `artifact-viewers`: Extend Flow Graph requirements to visualize memory-map relationships and avoid disconnected route stacks by rendering cross-entity edges.
- `pipeline-orchestration`: Clarify artifact-preparation expectations for fused graph inputs and optional lightweight graph-cache build/refresh behavior after indexing.

## Impact

- Affected code:
  - `desktop/src/sections/FlowGraph.tsx`
  - `desktop/src/sections/MemoryMap.tsx` (cross-navigation/context handoff)
  - `desktop/src/lib/artifacts.ts`
  - `desktop/src-tauri/src/artifacts.rs` (if fused payload is materialized server-side)
  - related desktop tests under `desktop/src/sections/` and `desktop/src/lib/`
- Affected systems: Desktop artifact viewers, desktop backend artifact readers, and optional local graph-cache handling.
- Dependencies: No required external service; optional embedded open-source graph database only if needed for scale/performance.