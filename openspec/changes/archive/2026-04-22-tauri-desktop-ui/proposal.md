## Why

Today `playwright-god` is CLI-only: every workflow (indexing, generating, planning, running, inspecting coverage, reviewing audit logs, configuring providers) is a separate command and JSON/text artifact. This is a steep ramp for new users, hides relationships between artifacts (memory map ↔ flow graph ↔ coverage ↔ generated specs), and offers no single place to drive the pipeline against a chosen repository or to review results visually. A native-feeling desktop shell would make the tool approachable, surface artifacts as first-class views, and let users iterate without reaching for a terminal.

## What Changes

- Add a new top-level `desktop/` Tauri 2 application (Rust backend + React + TypeScript + Vite frontend) that wraps the existing Python CLI as the single source of truth - the UI never re-implements pipeline logic, only orchestrates `playwright-god` subprocesses and reads the JSON/SQLite artifacts they produce.
- Provide a clean macOS-style shell: titlebar-less window with `hiddenInset` traffic lights, frosted/vibrancy sidebar, rounded panels, soft shadows, muted palette, roomy spacing, and a sidebar + main panel + bottom output-pane layout.
- Sidebar sections: **Repository**, **Memory Map**, **Flow Graph**, **Coverage & Gaps**, **Generation**, **Codegen Stream**, **Dry Run / Inspect**, **Audit Log**, **Settings**.
- Repository picker (native folder dialog) with recent-repos list persisted to app config, and a **Run pipeline** button that triggers index → memory-map → flow-graph → plan → generate → run, streaming progress events into a progress bar and the output pane.
- RAG / SQLite query panel that issues semantic + keyword queries against the active repo's `chromadb` index and the spec/test SQLite stores, rendering ranked chunks with file/line citations.
- Graph viewer (force-directed) for the flow graph (`flow_graph.json`) - routes, actions, journeys, evidence edges, with hover-to-cite-source and a route/action filter.
- Memory-map viewer that renders the JSON memory map as a collapsible tree with feature-area badges and inferred relationships.
- Coverage / "tests covered" viewer that loads the merged coverage report (frontend + backend) and shows per-file %, uncovered line ranges, and a routes-covered table; includes a **Test Gap Reviewer** tab listing prioritized uncovered routes/files with one-click "Generate test for this gap".
- LLM Provider Settings widget (provider, model, API key, Ollama URL, Playwright-CLI timeout) that writes to `.env` (or app-scoped config) and is read by every subsequent CLI invocation.
- Output / run console pane with per-run filtering, ANSI rendering, and **Export as CSV** for any tabular run-summary (test results, coverage rows, audit entries).
- Codegen Stream view: a checkbox toggle to live-tail `npx playwright codegen` output and the LLM prompt/response transcripts as they stream from the pipeline.
- Audit log section that reads the existing per-run `.pg_runs/<timestamp>/` artifacts (run summary, evaluation report, coverage, prompts) into a sortable, filterable list with **Export as CSV/JSON**.
- Dry-run / Inspect UI that surfaces `playwright-god inspect` and `discover` outputs (routes, journeys, scenario candidates) and lets the user preview the prompt that *would* be sent without invoking the LLM.
- Add a `make desktop` / `npm run tauri dev` developer workflow and document it in `README.md`.

## Capabilities

### New Capabilities
- `desktop-shell`: Tauri application shell, window chrome, native macOS look-and-feel, sidebar + main + output layout, theming, and recent-repos persistence.
- `pipeline-orchestration`: Spawning and streaming the `playwright-god` CLI from the desktop app, progress events, cancellation, and per-run artifact discovery under `.pg_runs/`.
- `artifact-viewers`: Memory-map tree viewer, flow-graph node viewer, coverage / test-gap viewer, RAG query panel, audit-log viewer, dry-run / inspect viewer, and CSV export for tabular outputs.
- `desktop-settings`: LLM provider configuration widget that reads/writes provider, model, API key, Ollama URL, and Playwright-CLI timeout to a desktop-scoped config consumed by CLI invocations.

### Modified Capabilities
<!-- None. The desktop app consumes existing CLI artifacts read-only and does not change spec-level behavior of test-coverage. -->

## Impact

- **New top-level directory**: `desktop/` (Tauri 2 + Rust + React + TypeScript + Vite + Tailwind).
- **New runtime dependencies (developer-only)**: Node.js 18+, Rust toolchain, Tauri CLI, `@tauri-apps/api`, React 18, Vite, Tailwind CSS, a graph library (`reactflow` or `cytoscape`), `papaparse` for CSV export.
- **No changes to `playwright_god/` Python code are required** for the MVP - the desktop app drives the existing CLI and reads the JSON/SQLite artifacts it already writes. Optional follow-up: add a stable, machine-readable `--json --stream` event mode to long-running CLI commands so the UI can show structured progress without parsing human-readable stdout.
- **Build / packaging**: `desktop/` produces a standalone `.app` (macOS), `.dmg`, `.AppImage`/`.deb` (Linux); the Python CLI is invoked via the user's installed `playwright-god` (PATH) or a configured path - bundling Python is out of scope for this change.
- **Docs**: `README.md` gains a "Desktop app" section; `AGENTS.md` notes the new `desktop/` workspace.
- **Tests**: Frontend uses Vitest + React Testing Library; Rust commands use `#[cfg(test)]` unit tests. Existing Python tests are unaffected.
