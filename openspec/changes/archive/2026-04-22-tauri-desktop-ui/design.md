## Context

`playwright-god` is a Python CLI that produces a rich set of artifacts per repository: a chromadb vector index, a JSON memory map, a flow graph, plan markdown, generated `.spec.ts` files, merged frontend/backend coverage reports, run summaries, and per-run audit artifacts under `.pg_runs/<timestamp>/`. Today every workflow is a separate command and reading the artifacts requires opening JSON in an editor. New users have a steep ramp; experienced users juggle terminals.

The desktop app is a thin orchestration + visualization layer on top of the existing CLI. It does not re-implement pipeline logic in Rust or TypeScript. It spawns `playwright-god` as subprocesses, streams their output, and renders the artifacts the CLI already writes.

Stakeholders:
- End users running playwright-god against their own repos (primary).
- Contributors developing playwright-god itself who want a faster artifact-review loop.
- Platform: macOS first, Linux on parity (Windows out of scope for v1).

## Goals / Non-Goals

**Goals:**
- Native-feeling macOS shell (frosted sidebar, hidden-inset traffic lights, rounded panels, soft shadows, muted palette, roomy spacing).
- Single source of truth: every action in the UI is a CLI subprocess; the UI never duplicates pipeline logic.
- Read-only viewers for memory map, flow graph, coverage, gaps, audit log, dry-run/inspect.
- Live progress bar + streaming output for the full pipeline.
- LLM provider settings centralized in one widget and forwarded to subprocesses via the existing env-var contract.
- CSV export from any tabular view (output pane, coverage table, audit log).
- Codegen-stream toggle that live-tails LLM prompt/response and `playwright codegen` output.

**Non-Goals:**
- Bundling the Python interpreter or `playwright-god` itself inside the `.app` bundle. Users must have `playwright-god` on PATH or configure a path in Settings.
- Reimplementing chromadb queries, coverage merging, or flow-graph extraction in Rust/TypeScript. The UI consumes the JSON the CLI writes.
- Windows support in v1 (frosted-window vibrancy story is materially different and falls below the priority bar).
- Authoring `.spec.ts` files inside the app. The UI shows generated specs read-only and links to them in the user's editor.
- Multi-user / cloud sync. The app is single-user, local-only.

## Decisions

### D1: Tauri 2 over Electron
**Choice**: Tauri 2 (Rust backend, system webview frontend).
**Why**: Smaller binary, lower memory, native menu / vibrancy / file-dialog APIs out of the box, and our app is artifact-rendering + subprocess-driving, neither of which benefits from Chromium-only APIs. Tauri 2 has stable plugin APIs for `dialog`, `fs`, `shell`, `os`, `store`, and `window-vibrancy`.
**Alternatives**: Electron (heavier, no advantage here), egui/iced (would force a fully native renderer and re-implement complex graph + table widgets), web-only Vite app (no native dialog, no secure store).

### D2: React + TypeScript + Vite + Tailwind in `desktop/src/`
**Choice**: React 18 + TypeScript + Vite + Tailwind CSS with a single `tailwind.config.ts` defining the design tokens (colors, spacing, radii, shadows, typography). Component library: hand-rolled with Radix UI primitives for menus/dialogs/tooltips.
**Why**: Mature ecosystem, fastest dev loop (Vite HMR), Tailwind centralizes the design-token requirement, Radix gives accessible primitives without imposing a visual style.
**Alternatives**: Svelte/SvelteKit (smaller bundles but smaller graph/table component ecosystem), Solid (excellent perf but fewer mature data-grid/graph libs).

### D3: macOS look & feel via `tauri-plugin-window-vibrancy` + Tailwind tokens
**Choice**: On macOS apply NSVisualEffectView vibrancy (`Sidebar` material) to the sidebar region and `HiddenInset` titlebar style to the window. On Linux fall back to an opaque muted background (`bg-stone-50/95`) and a borderless window decoration. Design tokens live in `tailwind.config.ts`:
- Colors: warm-neutral grays + a single accent (`#0A84FF` macOS system blue).
- Radii: `lg=10`, `xl=14`, `2xl=18`.
- Shadows: `soft = 0 1px 2px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.08)`.
- Spacing: 4-pt grid; panels use `p-6`/`gap-6` for roominess.
- Typography: `-apple-system, BlinkMacSystemFont, "SF Pro Text"` stack.

**Why**: Vibrancy + hidden-inset chrome is the single most recognizable macOS visual cue; centralized tokens satisfy the spec's design-tokens requirement.

### D4: Pipeline orchestration via Rust `Command` + `tauri::Channel`
**Choice**: Each pipeline step is a Rust `tokio::process::Command` spawned by a Tauri `#[tauri::command]`. stdout/stderr lines are forwarded to the frontend via a typed `tauri::ipc::Channel<PipelineEvent>` (Tauri 2 streaming channel), with event variants `Started{step}`, `StdoutLine{step, line}`, `StderrLine{step, line}`, `Progress{step, fraction}`, `Finished{step, exit_code}`, `Cancelled`, `Failed{step, exit_code}`.
**Why**: Channels avoid event-name collisions across concurrent runs (each run has its own channel), give backpressure, and serialize cleanly to TypeScript discriminated unions.
**Alternatives**: Global `emit_all` events (collide across runs), polling stdout via REST (no streaming), a sidecar gRPC server (overkill).

### D5: Pipeline step DAG + cancellation
**Choice**: Steps run sequentially: `index → memory-map → flow-graph → plan → generate → run`. A `CancellationToken` (Rust) is associated with each run; cancellation calls `child.kill()` on the active subprocess and short-circuits the remaining steps with a `Cancelled` event. Failure of any step short-circuits with `Failed` and skips downstream steps.
**Why**: Matches the existing CLI's data dependencies (generate needs the index; run needs a generated spec). Sequential is simpler and matches user expectations from the CLI.

### D6: Artifact discovery
**Choice**: After every run and on Repository activation, the Rust backend walks `<repo>/.pg_runs/`, sorts directories by name (timestamps are ISO-like and sort lexicographically), and exposes a `list_runs(repo) -> Vec<RunSummary>` command. The viewers fetch artifacts on demand via `read_run_artifact(run_id, artifact_name)` rather than pre-loading everything.
**Why**: Lazy loading keeps memory bounded for repos with hundreds of runs.

### D7: Settings store
**Choice**: Non-secret settings (provider, model, Ollama URL, Playwright-CLI timeout, recent repos, output-pane state) go in `tauri-plugin-store` (JSON file in app-config dir). API keys go in the OS credential store via `tauri-plugin-stronghold` *or* `keyring-rs` (preferred: `keyring-rs`, simpler, native Keychain on macOS, libsecret on Linux). Plaintext fallback file is mode 0600 with a UI warning.
**Why**: Splitting non-secret + secret storage matches OS conventions; `keyring-rs` is mature and avoids the heavier Stronghold dependency for a simple key-value need.

### D8: Settings → CLI env-var bridge
**Choice**: Before spawning a CLI subprocess, the Rust orchestrator reads settings from the store + secure-store and merges them into the subprocess `Command`'s env (`PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_URL`). The desktop app does **not** write to the user's `.env` - that would mutate state outside the app's scope.
**Why**: Reuses the env-var contract the CLI already supports (no new CLI flags required), and keeps mutation contained.

### D9: Graph viewer = `reactflow`
**Choice**: `reactflow` for the flow-graph viewer, with a force-directed layout via `dagre` for initial positioning. Routes rendered as rounded rectangles, actions as pills, evidence edges as thin gray curves; selected node highlights and opens a side panel.
**Why**: `reactflow` is the most mature React graph library, supports custom node renderers (so we can match the macOS aesthetic), and ships with pan/zoom/minimap out of the box.
**Alternatives**: `cytoscape` (more powerful but uglier defaults and harder to theme), raw d3 (too much wheel-reinvention).

### D10: RAG query bridge
**Choice**: Add a thin CLI command `playwright-god search "<query>" --persist-dir <dir> --json --top-n 10` (if not already present, add it as a follow-up; for v1 the desktop app shells out to `playwright-god generate --dry-run --json ...` or directly invokes a Python helper script that imports `RepositoryIndexer.search`). Render results as a list of cards with file:line and score.
**Why**: Keeps query logic in Python; UI is render-only.
**Open**: A dedicated `search` subcommand may need to be added in a separate change.

### D11: CSV export
**Choice**: `papaparse` (frontend) for CSV serialization; the user picks the destination via Tauri's `dialog.save` plugin and the Rust backend writes the bytes via `fs.writeFile`. Header row is emitted from the table column definitions so exports stay in sync with the visible columns.
**Why**: `papaparse` handles quoting/escaping correctly; using the table-column definitions as the source of truth avoids drift.

### D12: Output pane = virtualized log
**Choice**: Use `react-virtuoso` to virtualize the output pane so a 100k-line run does not freeze the UI. ANSI rendering via `ansi-to-html`. A line buffer in the Rust backend caps each run at 50,000 lines (older lines spill to disk under `.pg_runs/<timestamp>/desktop_log.txt`).
**Why**: Long pipeline runs can produce a lot of output; virtualization + a disk spill keeps memory bounded.

### D13: Codegen-stream view
**Choice**: Two side-by-side panes - left shows LLM prompt/response transcripts (one entry per LLM call, expandable), right shows `playwright codegen` raw output. Both are populated only when the user toggles the "Live tail codegen" checkbox to avoid the cost of rendering when not needed.
**Why**: Prompt transcripts are already written to `.pg_runs/<timestamp>/prompts/`; the UI just tails those files.

### D14: Dry-run / Inspect
**Choice**: `Inspect` and `Discover` views run `playwright-god inspect --json` and `playwright-god discover --json` (the existing subcommands). The Prompt-preview action invokes `playwright-god generate --description "..." --dry-run --print-prompt --json` (a flag that needs to be added in this change to the CLI - small, additive).
**Why**: `--dry-run --print-prompt` is the minimal CLI change required to satisfy the dry-run spec scenario without re-implementing prompt assembly in the UI.

## Risks / Trade-offs

- **[Risk]** Users without `playwright-god` on PATH get a confusing first-run experience → **Mitigation**: First-launch detector runs `which playwright-god`; if missing, Settings opens to a "CLI not found" panel with installation instructions and a path-picker.
- **[Risk]** Long-running pipeline runs consume large amounts of memory in the output pane → **Mitigation**: D12 (virtualization + 50k-line cap + disk spill).
- **[Risk]** Concurrent runs (user clicks "Run" twice) cause artifact races → **Mitigation**: Disable "Run Pipeline" while a run is active; queue or reject duplicate clicks.
- **[Risk]** Flow graphs with thousands of nodes hang `reactflow` → **Mitigation**: Cap initial render at 500 nodes; show a banner "showing top 500 of N nodes; use the filter to narrow down" with a virtualization fallback view.
- **[Risk]** macOS vibrancy + Linux fallback diverge visually enough to feel like two apps → **Mitigation**: Linux fallback uses the same Tailwind tokens with `backdrop-blur-md` + `bg-stone-50/85`; QA both platforms before tagging v1.
- **[Risk]** Secret storage via `keyring-rs` fails silently on minimal Linux desktops without libsecret → **Mitigation**: Detect at startup; if unavailable, surface a Settings-panel warning and fall back to the 0600 file.
- **[Trade-off]** Shipping a separate `desktop/` tree increases repo footprint and CI matrix → **Acceptable**: The tree is self-contained (Tauri + npm) and CI can opt-in to building it.

## Migration Plan

1. Land `desktop/` scaffold + design tokens + window chrome (Phase 1 of tasks).
2. Land orchestration backend + settings store + repository selection (Phase 2).
3. Land artifact viewers iteratively (memory map → flow graph → coverage → audit → RAG → dry-run) (Phase 3).
4. Land codegen stream + CSV export + polish (Phase 4).
5. Document `make desktop` and add a "Desktop app" section to `README.md`.

There is no rollback risk for the Python CLI - the desktop app is additive and consumes existing artifacts read-only. If the desktop app proves unwanted, deleting `desktop/` and the `make desktop` target removes it cleanly.

## Open Questions

- Do we want to ship a signed/notarized macOS `.app` in v1, or developer-build only? (Notarization requires an Apple Developer account.)
- Should the dry-run prompt-preview live entirely in the CLI (`--print-prompt`) or partially in the UI? Decision in D14 favors the CLI; confirm during implementation.
- Do we add a `playwright-god search` subcommand as part of this change or as a follow-up? Recommend follow-up to keep this change scoped to the desktop app.
