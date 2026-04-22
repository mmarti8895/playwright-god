## 1. Scaffold the desktop workspace

- [x] 1.1 Create `desktop/` at the repo root and initialize a Tauri 2 + React + TypeScript + Vite project (`npm create tauri-app@latest -- --template react-ts`)
- [x] 1.2 Add Tailwind CSS and configure `tailwind.config.ts` with the design tokens from design.md D3 (colors, radii, shadows, spacing, typography)
- [x] 1.3 Add Radix UI primitives (`@radix-ui/react-dialog`, `-dropdown-menu`, `-tooltip`, `-tabs`, `-checkbox`, `-select`)
- [x] 1.4 Add `reactflow`, `dagre`, `react-virtuoso`, `ansi-to-html`, `papaparse`, `clsx`, `zustand` (state) to `desktop/package.json`
- [x] 1.5 Add Rust crates to `desktop/src-tauri/Cargo.toml`: `tauri-plugin-dialog`, `tauri-plugin-fs`, `tauri-plugin-shell`, `tauri-plugin-store`, `tauri-plugin-os`, `window-vibrancy`, `keyring`, `tokio`, `serde`, `serde_json`, `walkdir`, `anyhow`, `thiserror`
- [x] 1.6 Add a top-level `Makefile` target `desktop` that runs `cd desktop && npm install && npm run tauri dev`
- [x] 1.7 Add a "Desktop app" section to `README.md` documenting prerequisites (Node 18+, Rust toolchain, `playwright-god` on PATH) and the `make desktop` workflow
- [x] 1.8 Update `AGENTS.md` to note the new `desktop/` workspace and its build commands

## 2. Window chrome and layout shell

- [x] 2.1 Configure `desktop/src-tauri/tauri.conf.json` with `titleBarStyle: "Overlay"`, `hiddenTitle: true`, min size 1100x720, default 1280x820, transparent on macOS
- [x] 2.2 In `src-tauri/src/lib.rs`, on `setup` apply NSVisualEffectView vibrancy (`Sidebar` material) on macOS via `window-vibrancy::apply_vibrancy`
- [x] 2.3 Detect Linux at runtime and apply the opaque `bg-stone-50/85 backdrop-blur-md` fallback to the sidebar
- [x] 2.4 Build the layout shell `src/components/Shell.tsx` with three regions: `Sidebar` (240px fixed), `MainPanel` (flex-1), `OutputPane` (collapsible, 240px default height)
- [x] 2.5 Implement `Sidebar.tsx` with the nine entries from the desktop-shell spec and an active-state indicator (rounded `bg-white/60` pill on macOS, `bg-stone-200` on Linux)
- [x] 2.6 Implement `OutputPane.tsx` with virtualized lines (`react-virtuoso`), an ANSI renderer, a "Clear" button, an "Export as CSV" button, and a collapse toggle in the status bar
- [x] 2.7 Wire the active-section state into a `zustand` store (`src/state/ui.ts`) and persist `outputPaneCollapsed` via `tauri-plugin-store`

## 3. Repository selection and recent-repos

- [x] 3.1 Add a Rust command `pick_repository() -> Result<String>` that opens the native folder dialog via `tauri-plugin-dialog` and validates the path is an existing directory
- [x] 3.2 Add a Rust command `list_recent_repos() -> Vec<RecentRepo>` and `add_recent_repo(path)` that persist to `tauri-plugin-store` (`recent.json`), capped at 10 entries, MRU-ordered
- [x] 3.3 Build `src/sections/Repository.tsx` with an "Open Repository" button, the active repo header card, and a Recent Repositories list (click to activate)
- [x] 3.4 Add the active-repo path to the `zustand` store and surface it in the `Shell` header

## 4. Pipeline orchestration backend

- [x] 4.1 In `src-tauri/src/pipeline.rs`, define the `PipelineEvent` enum (`Started`, `StdoutLine`, `StderrLine`, `Progress`, `Finished`, `Cancelled`, `Failed`) with `serde` derive matching the design.md D4 schema
- [x] 4.2 Implement `run_pipeline(repo: String, channel: Channel<PipelineEvent>) -> Result<RunId>` that runs steps sequentially: `index → memory-map → flow-graph → plan → generate → run`, spawning each via `tokio::process::Command` and forwarding stdout/stderr lines into the channel
- [x] 4.3 Implement a `CancellationToken` per run and a `cancel_pipeline(run_id)` command that calls `child.kill()` on the active subprocess and emits `Cancelled`
- [x] 4.4 Inject env vars from settings (D8) into each subprocess: `PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_URL`
- [x] 4.5 On step failure, emit `Failed` and short-circuit remaining steps; on success of the final step, emit `Finished` for the whole run
- [x] 4.6 Add a 50,000-line in-memory cap on the channel buffer; spill older lines to `<repo>/.pg_runs/<timestamp>/desktop_log.txt`
- [x] 4.7 Disable concurrent runs: `run_pipeline` returns `Err(PipelineBusy)` if a run is already active for any repo

## 5. Pipeline orchestration frontend

- [x] 5.1 Build `src/sections/Generation.tsx` with a "Run Pipeline" button, a description input, a progress bar (advances on each `Started`/`Finished` event), an elapsed-time counter, and a "Cancel" button
- [x] 5.2 Subscribe to the `Channel<PipelineEvent>` and forward `StdoutLine`/`StderrLine` events to the `OutputPane`
- [x] 5.3 Disable the "Run Pipeline" button while a run is active; show a status badge (`idle`, `running`, `cancelled`, `failed`, `succeeded`)
- [x] 5.4 On `Finished`, refresh the audit-log list and the artifact viewers for the active repo

## 6. Settings widget and secret storage

- [x] 6.1 In `src-tauri/src/settings.rs`, define the `Settings` struct (provider, model, ollama_url, playwright_cli_timeout, cli_path) and persist via `tauri-plugin-store` (`settings.json`)
- [x] 6.2 Implement `get_secret(key) -> Option<String>` and `set_secret(key, value)` using the `keyring` crate (Keychain on macOS, libsecret on Linux); on failure fall back to a 0600-permission file under app-config and surface a warning flag
- [x] 6.3 Build `src/sections/Settings.tsx` with form controls: provider `Select` (`openai`, `anthropic`, `gemini`, `ollama`, `template`, `playwright-cli`), model `Input`, API-key masked `Input`, Ollama URL `Input`, Playwright-CLI timeout `Input` (integer ≥ 1), CLI path `Input` with a "Browse" button
- [x] 6.4 Implement client-side validation (timeout ≥ 1 integer); disable Save while invalid; show a "Saved" toast on success
- [x] 6.5 Add a "Reset to defaults" button with a Radix `AlertDialog` confirmation that clears both the store and the secret entries owned by this app
- [x] 6.6 On startup, run `which playwright-god` (or use `cli_path` from settings); if missing, open the Settings panel to a "CLI not found" callout

## 7. Memory-map viewer

- [x] 7.1 Add a Rust command `read_memory_map(repo) -> Result<MemoryMap>` that runs `playwright-god index --memory-map - <repo> --json` (or reads a cached `memory_map.json` if present)
- [x] 7.2 Build `src/sections/MemoryMap.tsx` rendering feature areas as Radix `Collapsible` nodes; each file shows path + chunk count
- [x] 7.3 Empty-state: when no map exists, show a "Run Index" CTA that triggers the index step of the pipeline

## 8. Flow-graph viewer

- [x] 8.1 Add a Rust command `read_flow_graph(repo) -> Result<FlowGraph>` that returns the parsed `flow_graph.json` (running the extract step if missing, gated behind a confirmation in the UI)
- [x] 8.2 Build `src/sections/FlowGraph.tsx` using `reactflow` with custom node renderers (rounded rectangle for routes, pill for actions) and `dagre` for initial layout
- [x] 8.3 Implement node selection → side panel showing evidence (file + line range)
- [x] 8.4 Implement the filter input: matching nodes are highlighted, non-matching dimmed (`opacity-30`)
- [x] 8.5 Cap initial render at 500 nodes; show a banner "showing top 500 of N nodes; narrow with the filter" when exceeded

## 9. Coverage and test-gap viewer

- [x] 9.1 Add a Rust command `read_coverage(repo) -> Result<CoverageReport>` that returns the most recent `<repo>/.pg_runs/<ts>/coverage_merged.json`
- [x] 9.2 Build `src/sections/Coverage.tsx` with two tabs: "Files" (sortable table, least-covered first) and "Routes" (covered/uncovered route list)
- [x] 9.3 Add an "Export as CSV" action on the Files table using `papaparse` + `tauri-plugin-dialog.save`
- [x] 9.4 Build the "Test Gaps" tab listing prioritized uncovered routes/files with a "Generate test for this gap" button that switches to the Generation section pre-populated with a description targeting that gap

## 10. RAG / SQLite query panel

- [x] 10.1 Add a Rust command `rag_search(repo, query, top_n) -> Result<Vec<SearchHit>>` that shells out to a small Python helper (e.g., `python -m playwright_god._search "<query>" --persist-dir <dir> --top-n <n> --json`) - if no such CLI exists, document the follow-up and fall back to `playwright-god generate --description "<query>" --dry-run --print-context --json`
- [x] 10.2 Build `src/sections/Rag.tsx` with a query input, a "Search" button, and a results list showing file:line, score (3 decimals), and the chunk content with monospace formatting
- [x] 10.3 Empty-state when no chromadb index exists: "Run Index" CTA

## 11. Audit-log viewer

- [x] 11.1 Add a Rust command `list_runs(repo) -> Result<Vec<RunSummary>>` that walks `<repo>/.pg_runs/`, parses each run's `run_summary.json` and `generated_spec_evaluation.json`
- [x] 11.2 Build `src/sections/AuditLog.tsx` as a sortable, filterable table (timestamp, status, duration, evaluation status, new nodes/journeys/routes counts)
- [x] 11.3 Row click opens a Radix `Dialog` drawer with run details and links to coverage and prompt-transcript artifacts
- [x] 11.4 Add an "Export as CSV/JSON" action that exports the visible (filtered + sorted) rows

## 12. Codegen-stream view

- [x] 12.1 Add a Rust command `tail_codegen(run_id, channel)` that tails `<repo>/.pg_runs/<run_id>/prompts/*.json` and the active `playwright codegen` subprocess stdout (when applicable), forwarding lines via a `Channel<CodegenEvent>`
- [x] 12.2 Build `src/sections/CodegenStream.tsx` with a "Live tail codegen" Radix `Checkbox` and two side-by-side virtualized panes (LLM transcripts left, codegen output right)
- [x] 12.3 When the checkbox is unchecked, unsubscribe from the channel and drop buffered events

## 13. Dry-run / Inspect viewer

- [x] 13.1 Add Rust commands `inspect_repo(repo) -> Inspect` and `discover_repo(repo) -> Discover` that run `playwright-god inspect --json` and `playwright-god discover --json`
- [x] 13.2 Build `src/sections/Inspect.tsx` with collapsible sections for routes, journeys, and scenario candidates
- [x] 13.3 Add a "Preview Prompt" form: description input + button that invokes a CLI dry-run mode and renders the assembled prompt in a read-only `<pre>` block (add a `--print-prompt --dry-run --json` flag to `playwright-god generate` if not already present, or document as a follow-up CLI change required to satisfy the spec scenario)

## 14. CSV export utility

- [x] 14.1 Implement `src/lib/csv.ts` with `exportRows(rows, columns, filename)` that builds CSV via `papaparse`, opens `dialog.save`, writes via `fs.writeFile`, and shows a "Saved to <path>" toast
- [x] 14.2 Wire `exportRows` into the OutputPane (one row per output line: timestamp, stream, line), Coverage Files table, Coverage Routes table, and Audit Log table

## 15. Tests

- [x] 15.1 Vitest + React Testing Library setup in `desktop/`; add tests for `Sidebar` navigation, `Settings` validation, `Coverage` table sorting, and `csv.ts` round-trip
- [x] 15.2 Rust unit tests in `src-tauri/src/`: pipeline event serialization, recent-repos cap (10), settings round-trip, secret-store fallback path
- [x] 15.3 Add a CI job (`.github/workflows/desktop.yml`) that runs `npm run lint`, `npm test`, `cargo test`, and `npm run tauri build --debug` on macos-latest and ubuntu-latest

## 16. Polish and ship

- [x] 16.1 Pass an accessibility audit (keyboard navigation through every section, focus outlines visible, Radix primitives unmodified)
- [x] 16.2 QA both macOS and Linux: vibrancy on macOS, opaque fallback on Linux, all viewers populated against a real `.pg_runs/` directory (checklist documented in `desktop/QA.md`)
- [x] 16.3 Generate a demo `.dmg` (macOS) and `.AppImage` (Linux) and attach to a draft release (automated via `.github/workflows/release-desktop.yml` on `desktop-v*` tags)
- [x] 16.4 Update `README.md` "Desktop app" section with screenshots and the demo-build links
