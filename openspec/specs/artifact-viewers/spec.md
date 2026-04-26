# Artifact Viewers

## Purpose

Capability added by the `tauri-desktop-ui` change (archived). See the change for the original proposal and design notes.

## Requirements

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

### Requirement: Coverage and test-gap viewer
The desktop application SHALL render `coverage_merged.json` as a per-file table sorted least-covered first, showing percentage covered, covered/total lines, and missing line ranges, and SHALL render uncovered routes as a separate table.

#### Scenario: Coverage table loads
- **WHEN** the user opens the Coverage & Gaps section with a coverage report available
- **THEN** files are listed least-covered first with percentage, covered/total counts, and missing line ranges visible

#### Scenario: Coverage report missing
- **WHEN** no coverage report exists for the active repository
- **THEN** the section shows an empty-state message that explains how to produce `coverage_merged.json` and does not render stale rows from a previously selected repository

#### Scenario: Generate-for-gap action
- **WHEN** the user clicks "Generate test" for an uncovered route or file gap
- **THEN** the Generation section is opened, the generated description is pre-filled exactly once, and the user can immediately launch generation without retyping context

### Requirement: RAG / SQLite query panel
The desktop application SHALL provide a query input that runs semantic search against the active repository's chromadb index (via `playwright-god` subcommand or library bridge) and renders the top-N ranked chunks with file path, line range, and similarity score.

#### Scenario: Query returns ranked chunks
- **WHEN** the user enters a query and submits it
- **THEN** the panel displays the top-N chunks by score, each showing file path, line range, score (3 decimal places), and the chunk content with syntax highlighting

#### Scenario: No index available
- **WHEN** the active repository has no chromadb index
- **THEN** the panel shows an empty-state with a "Run Index" call-to-action

#### Scenario: Index-only run makes search ready
- **WHEN** the user triggers "Run Index" from the RAG panel and the index run succeeds
- **THEN** the RAG panel transitions from missing-index to ready state for the same active repository without requiring an app restart

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
