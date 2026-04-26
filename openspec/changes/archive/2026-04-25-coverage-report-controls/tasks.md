## 1. Rust Backend — Coverage Run Module

- [x] 1.1 Create `desktop/src-tauri/src/coverage_run.rs` with `CoverageRegistry` (mirrors `PipelineRegistry` lock pattern) and `CoverageEvent` enum (`RunStarted`, `LogLine`, `Finished`, `Cancelled`, `Failed`)
- [x] 1.2 Implement `run_coverage` Tauri command: resolve latest spec path via `latest_run_dir`, spawn `playwright-god run <spec> --coverage`, stream stdout/stderr as `LogLine` events through a `Channel<CoverageEvent>`, use `CancellationToken` for clean kill
- [x] 1.3 Implement `cancel_coverage` Tauri command: look up active `CoverageRegistry` entry and cancel the token; emit `Cancelled` event
- [x] 1.4 Register `CoverageRegistry` as managed state and register `run_coverage` / `cancel_coverage` commands in `lib.rs`
- [x] 1.5 Add helper `latest_spec_path(repo: &Path) -> Option<PathBuf>` to `artifacts.rs` (scan `.pg_runs/` newest-first for `generated.spec.ts`)

## 2. Rust Backend — Pipeline Interlock

- [x] 2.1 Expose `PipelineRegistry::is_busy_for_repo(repo: &str) -> bool` (or reuse `active_for_repo`) so `run_coverage` can return an early error when the main pipeline is running on the same repo
- [x] 2.2 Add a new `read_latest_spec_path` Tauri command (wraps `latest_spec_path`) so the frontend can check spec availability on mount and disable the Run button accordingly

## 3. TypeScript Bindings

- [x] 3.1 Add `runCoverage(repo: string, onEvent: (e: CoverageEvent) => void): Promise<void>` wrapper in `desktop/src/lib/wrappers.ts` using `invokeCommand` + `listen` (Channel pattern)
- [x] 3.2 Add `cancelCoverage(): Promise<void>` wrapper in `desktop/src/lib/wrappers.ts`
- [x] 3.3 Add `readLatestSpecPath(repo: string): Promise<string | null>` wrapper in `desktop/src/lib/wrappers.ts`
- [x] 3.4 Define `CoverageEvent` TypeScript discriminated union type in `desktop/src/lib/wrappers.ts`

## 4. Zustand State Slice

- [x] 4.1 Add `coverageRun` slice to `desktop/src/state/ui.ts`: `{ status: "idle" | "running" | "done" | "error"; logLines: string[]; errorMessage: string | null }`
- [x] 4.2 Add actions: `setCoverageRunStatus`, `appendCoverageLogLine` (ring-buffer capped at 500 lines), `clearCoverageRun` (resets status to `idle`, clears logLines and errorMessage)

## 5. Coverage UI — Controls Toolbar

- [x] 5.1 Add a toolbar row at the top of `Coverage.tsx` (above the existing totals header) containing **Run Coverage**, **Cancel**, and **Clear** buttons; visibility/disabled state driven by `coverageRun.status` and spec availability
- [x] 5.2 Implement **Run Coverage** click handler: call `runCoverage`, wire `onEvent` callbacks to dispatch `appendCoverageLogLine` / `setCoverageRunStatus`; on `RunFinished` bump `artifactsVersion`
- [x] 5.3 Implement **Cancel** click handler: call `cancelCoverage`, set status to `idle`
- [x] 5.4 Implement **Clear** click handler: call `clearCoverageRun`, reset local `report` state to `null`
- [x] 5.5 Disable **Run Coverage** when spec unavailable (tooltip: "No generated spec found. Run the full pipeline first.") and when pipeline is running (tooltip: "Pipeline is running. Wait for it to finish.")

## 6. Coverage UI — Progress Log Panel

- [x] 6.1 Add a collapsible `LogPanel` sub-component inside `Coverage.tsx`: renders `coverageRun.logLines` in a fixed-height scrollable `<pre>` (auto-scrolls to bottom on new lines)
- [x] 6.2 Show `LogPanel` while `status === "running"`; keep it visible but collapsed (with a toggle) when `status === "done"` or `status === "error"`
- [x] 6.3 Display "Run cancelled — partial coverage results may exist in .pg_runs/" inline in the log panel after a cancellation

## 7. Empty-State Integration

- [x] 7.1 Update the existing "No coverage report yet" empty state in `Coverage.tsx` to also render the **Run Coverage** button (same button as toolbar, reuses same handler)
- [x] 7.2 In the error state (when `loadError` is set or `coverageRun.status === "error"`), render the **Run Coverage** button alongside the error message to allow immediate retry

## 8. Tests

- [x] 8.1 Add vitest unit tests for the `coverageRun` Zustand slice: verify state transitions, ring-buffer cap, and `clearCoverageRun` reset behaviour
- [x] 8.2 Add vitest unit tests for `runCoverage` / `cancelCoverage` TypeScript wrappers (mock `invokeCommand`)
- [x] 8.3 Add vitest rendering tests for `Coverage.tsx`: verify Run/Cancel/Clear button visibility in each lifecycle state (`idle`, `running`, `done`, `error`)
- [x] 8.4 Add Rust unit test in `coverage_run.rs`: verify `latest_spec_path` returns `None` when `.pg_runs/` is absent and returns the spec from the newest run directory when present
