## MODIFIED Requirements

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
