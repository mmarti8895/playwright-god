## Why

The Coverage & Gaps section currently only reads a pre-existing `coverage_merged.json` file — there is no way to trigger, monitor, or reset a coverage run from within the desktop UI. Users must drop to a terminal to generate data, then return to the UI to view it, which breaks flow and makes the tool harder to adopt.

## What Changes

- Add a **Run Coverage** button that invokes the `playwright-god` pipeline with `--coverage` on the active repository from inside the desktop app.
- Display **live progress** (log lines / percentage) streamed from the subprocess while the report is being generated.
- **Automatically refresh** the Coverage & Gaps view once generation completes, surfacing results inline.
- Add a **Cancel** button (visible while a run is in progress) that terminates the subprocess cleanly.
- Add a **Clear** button that wipes the current in-memory report so the user can trigger a fresh run without leaving the section.
- Preserve the existing **Export CSV** capability (files + routes tabs) — no behaviour changes there.

## Capabilities

### New Capabilities

- `coverage-run-controls`: UI controls and Tauri IPC for triggering, streaming progress of, cancelling, and clearing a coverage report run inside the Coverage & Gaps section.

### Modified Capabilities

- `test-coverage`: The Coverage & Gaps view gains run/cancel/clear controls and a progress display area. The core read-only display requirements are unchanged; only the interaction model gains new states (`idle`, `running`, `done`, `error`).

## Impact

- `desktop/src/sections/Coverage.tsx` — primary UI change; new run state machine, progress log area, and action buttons.
- `desktop/src-tauri/src/` — new Tauri command(s): `run_coverage` (spawns subprocess, streams events) and `cancel_coverage` (kills the child process).
- `desktop/src/lib/wrappers.ts` (or a new `coverage_run.ts`) — TypeScript bindings for the new IPC commands and the streaming event listener.
- `desktop/src/state/ui.ts` — extend store with coverage-run state (`status`, `log lines`, `abort controller`).
- No changes to Python CLI or backend indexing logic.
