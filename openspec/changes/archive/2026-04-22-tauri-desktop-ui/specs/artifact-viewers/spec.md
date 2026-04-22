## ADDED Requirements

### Requirement: Memory-map viewer
The desktop application SHALL render the active repository's memory-map JSON as a collapsible tree grouped by feature area, showing each file's chunk count and inferred relationships.

#### Scenario: Memory map loads
- **WHEN** the user opens the Memory Map section with an indexed repository
- **THEN** the viewer loads `memory_map.json` (or invokes `playwright-god index --memory-map -`), renders feature areas as expandable nodes, and displays file paths with chunk counts

#### Scenario: Memory map missing
- **WHEN** no memory map exists for the active repository
- **THEN** the viewer shows an empty-state message with a "Run Index" call-to-action that triggers the index step of the pipeline

### Requirement: Flow-graph viewer
The desktop application SHALL render the active repository's `flow_graph.json` as an interactive node-link diagram in which routes and actions are nodes, evidence relationships are edges, and hovering a node reveals its source file and line range.

#### Scenario: Graph renders
- **WHEN** the user opens the Flow Graph section with a flow graph available
- **THEN** the viewer displays all routes and actions as a force-directed graph and clicking a node opens a side panel showing its evidence (file + line range)

#### Scenario: Filtering nodes
- **WHEN** the user types into the graph filter input
- **THEN** only nodes whose id, route path, or action role contain the filter text are highlighted; non-matching nodes are dimmed

### Requirement: Coverage and test-gap viewer
The desktop application SHALL render `coverage_merged.json` as a per-file table sorted least-covered first, showing percentage covered, covered/total lines, and missing line ranges, and SHALL render uncovered routes as a separate table.

#### Scenario: Coverage table loads
- **WHEN** the user opens the Coverage & Gaps section with a coverage report available
- **THEN** files are listed least-covered first with percentage, covered/total counts, and missing line ranges visible

#### Scenario: Generate-for-gap action
- **WHEN** the user clicks "Generate test for this gap" on an uncovered route or file
- **THEN** the Generation section is opened, pre-populated with a description targeting that gap, and the user can launch generation against it

### Requirement: RAG / SQLite query panel
The desktop application SHALL provide a query input that runs semantic search against the active repository's chromadb index (via `playwright-god` subcommand or library bridge) and renders the top-N ranked chunks with file path, line range, and similarity score.

#### Scenario: Query returns ranked chunks
- **WHEN** the user enters a query and submits it
- **THEN** the panel displays the top 10 chunks by score, each showing file path, line range, score (3 decimal places), and the chunk content with syntax highlighting

#### Scenario: No index available
- **WHEN** the active repository has no chromadb index
- **THEN** the panel shows an empty-state with a "Run Index" call-to-action

### Requirement: Audit-log viewer
The desktop application SHALL list every per-run artifact directory under `<repo>/.pg_runs/` as a sortable, filterable row showing timestamp, status, duration, generation evaluation status, and counts of newly-covered nodes/journeys/routes.

#### Scenario: Runs are sortable
- **WHEN** the user clicks a column header in the audit-log table
- **THEN** the table sorts by that column ascending, then descending on a second click

#### Scenario: Run details
- **WHEN** the user clicks a row
- **THEN** a detail drawer opens showing the run summary, evaluation report, and links to coverage and prompt-transcript artifacts for that run

### Requirement: Dry-run / inspect viewer
The desktop application SHALL surface the output of `playwright-god inspect` and `playwright-god discover` (routes, journeys, scenario candidates) and SHALL allow the user to preview the prompt that would be sent to the LLM for a given description without actually invoking the LLM.

#### Scenario: Inspect output
- **WHEN** the user opens the Dry Run / Inspect section with an active repository
- **THEN** the viewer runs `playwright-god inspect --json` and `playwright-god discover --json` and renders routes, journeys, and scenario candidates in collapsible sections

#### Scenario: Prompt preview
- **WHEN** the user enters a description and clicks "Preview Prompt"
- **THEN** the app invokes the CLI in a dry-run mode (no LLM call) and renders the assembled prompt in a read-only viewer

### Requirement: CSV export for tabular outputs
The desktop application SHALL provide an "Export as CSV" action on the output pane, the coverage table, and the audit-log table that downloads the current view's rows as a UTF-8 CSV file with a header row.

#### Scenario: Coverage table is exported
- **WHEN** the user clicks "Export as CSV" on the coverage table
- **THEN** the app prompts for a save location and writes a CSV with one row per file containing path, percent, covered_lines, total_lines, and missing_line_ranges columns
