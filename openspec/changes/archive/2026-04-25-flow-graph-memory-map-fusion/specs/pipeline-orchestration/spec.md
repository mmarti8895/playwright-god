## ADDED Requirements

### Requirement: Fused graph artifact preparation
The desktop pipeline/artifact layer SHALL prepare a fused graph model from flow-graph and memory-map artifacts for the active repository and SHALL refresh this model after successful index-related runs.

#### Scenario: Fused graph refresh after indexing
- **WHEN** an index-only or full pipeline run completes successfully for the active repository
- **THEN** the fused graph inputs are refreshed so the Flow Graph section can render updated cross-entity connectivity without requiring app restart

#### Scenario: Deterministic fused graph identity
- **WHEN** fused graph nodes and edges are composed from artifacts
- **THEN** node and edge identities remain stable across refreshes when source artifact content is unchanged

### Requirement: Optional embedded graph-cache mode
The desktop application SHALL support an optional lightweight embedded open-source graph-cache mode for fused-graph queries on large repositories while keeping in-memory composition as the default mode.

#### Scenario: Default mode remains dependency-light
- **WHEN** the user has not enabled graph-cache mode
- **THEN** fused graph composition runs in-memory with no required external graph database runtime

#### Scenario: Graph-cache mode is used when enabled
- **WHEN** graph-cache mode is enabled and repository graph size exceeds configured thresholds
- **THEN** the app materializes/queries the fused graph via the embedded graph-cache backend and preserves viewer behavior parity with in-memory mode
