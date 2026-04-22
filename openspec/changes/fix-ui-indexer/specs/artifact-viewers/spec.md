## MODIFIED Requirements

### Requirement: Memory-map viewer
The desktop application SHALL render the active repository's memory-map JSON as a collapsible tree grouped by feature area, showing each file's chunk count and inferred relationships.

#### Scenario: Memory map loads
- **WHEN** the user opens the Memory Map section with an indexed repository
- **THEN** the viewer loads `memory_map.json` (or invokes `playwright-god index --memory-map -`), renders feature areas as expandable nodes, and displays file paths with chunk counts

#### Scenario: Memory map missing
- **WHEN** no memory map exists for the active repository
- **THEN** the viewer shows an empty-state message with a "Run Index" call-to-action that starts an index-only run for that repository instead of only navigating to another tab

### Requirement: RAG / SQLite query panel
The desktop application SHALL provide a query input that runs semantic search against the active repository's chromadb index (via `playwright-god` subcommand or library bridge) and renders the top-N ranked chunks with file path, line range, and similarity score.

#### Scenario: Query returns ranked chunks
- **WHEN** the user enters a query and submits it
- **THEN** the panel displays the top 10 chunks by score, each showing file path, line range, score (3 decimal places), and the chunk content with syntax highlighting

#### Scenario: No index available
- **WHEN** the active repository has no chromadb index
- **THEN** the panel shows an empty-state with a "Run Index" call-to-action that starts an index-only run for the active repository
