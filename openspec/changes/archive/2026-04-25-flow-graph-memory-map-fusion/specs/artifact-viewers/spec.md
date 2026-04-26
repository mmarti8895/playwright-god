## MODIFIED Requirements

### Requirement: Flow-graph viewer
The desktop application SHALL render a fused graph derived from the active repository's `flow_graph.json` and `memory_map.json` as an interactive node-link diagram in which routes, actions, files, and feature areas are graph nodes and typed relationships are graph edges.

#### Scenario: Fused graph renders with interconnectivity
- **WHEN** the user opens the Flow Graph section with both flow and memory-map artifacts available
- **THEN** the viewer displays routes/actions/files/features in one graph and renders cross-entity edges so route-heavy stacks are connected to file and feature context

#### Scenario: Layer and relation filtering
- **WHEN** the user toggles graph layers or relation types in the Flow Graph controls
- **THEN** only the selected node layers and edge relation types remain visible while preserving the current pan/zoom state

#### Scenario: Partial artifact fallback
- **WHEN** one of `flow_graph.json` or `memory_map.json` is missing
- **THEN** the viewer renders the available subgraph and shows an inline notice describing which artifact is missing and how to generate it

### Requirement: Memory-map viewer
The desktop application SHALL render the active repository's memory-map JSON as a collapsible tree grouped by feature area, showing each file's chunk count and inferred relationships.

#### Scenario: Memory map loads
- **WHEN** the user opens the Memory Map section with an indexed repository
- **THEN** the viewer loads `memory_map.json` (or invokes `playwright-god index --memory-map -`), renders feature areas as expandable nodes, and displays file paths with chunk counts

#### Scenario: Memory map opens context in flow graph
- **WHEN** the user activates a memory-map item that has flow evidence
- **THEN** the app navigates to the Flow Graph section and pre-filters/highlights the corresponding fused graph neighborhood

#### Scenario: Memory map missing
- **WHEN** no memory map exists for the active repository
- **THEN** the viewer shows an empty-state message with a "Run Index" call-to-action that starts an index-only run for that repository instead of only navigating to another tab
