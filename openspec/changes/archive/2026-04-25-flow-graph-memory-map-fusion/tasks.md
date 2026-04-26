## 1. Fused Graph Data Model

- [x] 1.1 Define shared fused-graph node/edge types in desktop artifact code with stable prefixed IDs and typed relations.
- [x] 1.2 Implement composition logic that merges `flow_graph.json` and `memory_map.json` into a canonical fused graph DTO.
- [x] 1.3 Implement graceful fallback behavior when one artifact is missing, including metadata indicating which source is absent.

## 2. Flow Graph Viewer Integration

- [x] 2.1 Update `desktop/src/sections/FlowGraph.tsx` to consume fused graph data and render routes/actions/files/features in a single graph.
- [x] 2.2 Add layer toggles and relation-type toggles so users can reduce graph clutter without losing context.
- [x] 2.3 Add partial-artifact inline notices and preserve pan/zoom when applying layer/relation filters.

## 3. Memory Map to Flow Graph Context Handoff

- [x] 3.1 Add Memory Map item actions that navigate to Flow Graph with preselected context filters/highlights.
- [x] 3.2 Add shared UI-store fields/events for one-time graph focus handoff and consume-once behavior.

## 4. Optional Lightweight Graph Cache Path

- [x] 4.1 Add a graph-composition adapter boundary supporting in-memory mode as default and optional embedded graph-cache mode.
- [x] 4.2 Implement threshold/config gating that enables cache mode only when configured and graph size warrants it.
- [x] 4.3 Ensure cache and in-memory modes emit the same fused DTO contract for viewer parity.

## 5. Validation and Tests

- [x] 5.1 Add or update unit tests for fused graph composition, stable identities, and missing-artifact fallback behavior.
- [x] 5.2 Add or update section tests for Flow Graph layer/relation filtering and Memory Map-to-Flow Graph handoff.
- [x] 5.3 Add tests validating cache-mode parity against in-memory output for representative fixtures.
- [x] 5.4 Run desktop validation (`npm run test` in `desktop/` and relevant `cargo test` in `desktop/src-tauri`) and resolve regressions.