## Context

The Coverage & Gaps section (`desktop/src/sections/Coverage.tsx`) currently loads a pre-existing `coverage_merged.json` from the lexicographically-latest `.pg_runs/<run-id>/` directory via the `read_coverage` Tauri command. There is no way to trigger a fresh coverage run, observe its progress, cancel it, or reset state from the UI.

The desktop backend already has a mature subprocess-management pattern in `pipeline.rs`: a `PipelineRegistry` holding at most one `ActiveRun` (with a `CancellationToken`), a `Channel<PipelineEvent>` for streaming stdout/stderr to the front-end, and a typed event enum that the TypeScript layer listens to via `onEvent`.

The CLI surface: `playwright-god run <spec> [--target-dir <repo>] [--artifact-dir <runs-dir>] [--coverage]` executes a generated spec and, when `--coverage` is passed, writes `coverage_merged.json` into the run's artifact directory.

## Goals / Non-Goals

**Goals:**
- Add a **Run Coverage** button to the Coverage & Gaps section that invokes `playwright-god run <last_spec> --coverage` on the active repository.
- Stream subprocess stdout/stderr lines to a live log area in the Coverage view.
- Support **Cancel**: send a kill signal to the child process mid-run.
- Support **Clear**: reset the in-memory report and run-log so the user can trigger a fresh run.
- Auto-refresh the coverage display when the run completes successfully (`bumpArtifactsVersion`).
- **Export** (CSV) remains unchanged.

**Non-Goals:**
- Running the full pipeline (index → generate → run) from this button. This only re-runs an existing spec with `--coverage`.
- Generating a brand-new test spec from this view.
- Changing the Python CLI or coverage data format.
- Persisting the log lines to disk (ephemeral session state only).

## Decisions

### D1 — Separate Tauri module (`coverage_run.rs`) vs. extending `pipeline.rs`

**Decision**: Introduce a new file `desktop/src-tauri/src/coverage_run.rs` with its own `CoverageRegistry` (same `Mutex<Option<ActiveRun>>` pattern) and two Tauri commands: `run_coverage` and `cancel_coverage`.

**Rationale**: The main pipeline already uses a global concurrency lock (`PipelineRegistry::busy`). A coverage run should be independently lockable (user may want to run coverage after a pipeline that already finished), and mixing coverage state into `PipelineRegistry` would complicate the existing step-DAG logic. Reusing the same `ActiveRun` / `CancellationToken` types keeps implementation cost low.

**Alternative considered**: Add a `Coverage` step to the existing pipeline DAG. Rejected because it couples coverage to the full pipeline run and prevents on-demand re-runs.

### D2 — Event schema: new `CoverageEvent` enum vs. reusing `PipelineEvent`

**Decision**: Define a new `CoverageEvent` enum in `coverage_run.rs` with variants `RunStarted`, `LogLine { stream, line }`, `Finished { exit_code }`, `Cancelled`, `Failed { message }`. Do **not** reuse `PipelineEvent`.

**Rationale**: Coverage run events don't have a `step` dimension; forcing them into `PipelineEvent`'s step-aware schema would require a dummy step name. A minimal, flat schema is cleaner on both sides.

### D3 — Spec path resolution

**Decision**: `run_coverage` resolves the latest spec automatically server-side: scan `.pg_runs/` for the lexicographically-largest run directory containing a `generated.spec.ts` file. Expose the resolved path to the frontend in the `RunStarted` event so the UI can display it.

**Rationale**: The frontend already delegates file-system queries to Rust (see `read_coverage`, `latest_run_dir`). This avoids duplicating path-resolution logic in TypeScript.

**Alternative considered**: Let the frontend pass the spec path explicitly. Rejected to avoid an extra `read_runs` roundtrip just to populate a path picker.

### D4 — UI state: Zustand slice vs. local component state

**Decision**: Add a `coverageRun` slice to `ui.ts` (Zustand store):

```ts
interface CoverageRunState {
  status: "idle" | "running" | "done" | "error";
  logLines: string[];
  errorMessage: string | null;
}
```

Actions: `setCoverageRunStatus`, `appendCoverageLogLine`, `clearCoverageRun`.

**Rationale**: The run status needs to survive navigation (user leaves Coverage section and comes back while a run is in progress). Local component state would be lost on unmount.

### D5 — Log area: bounded buffer

**Decision**: Limit `logLines` to the last 500 lines (ring-buffer semantics in `appendCoverageLogLine`). Older lines are silently dropped in memory (the actual subprocess stdout/stderr can be reviewed in the `.pg_runs/` directory).

**Rationale**: Keeps memory usage bounded without adding disk I/O from the frontend.

## Risks / Trade-offs

- **No existing spec to run** → `run_coverage` returns an error if no `generated.spec.ts` is found in `.pg_runs/`. The UI shows an actionable message directing the user to run the full pipeline first.
- **Coverage requires Node + `@playwright/test`** → Same prerequisite as the existing `run` pipeline step. Error message surfaces the missing-dependency string from the subprocess's stderr.
- **Concurrent pipeline + coverage run** → Each uses its own registry, so both could theoretically run simultaneously. This is acceptable (rare in practice); a future change could add cross-registry locking if needed.
- **Windows process kill** → `CancellationToken` triggers a `kill()` on the `Child` handle. On Windows, `tokio::process::Child::kill()` sends `TerminateProcess`, which is immediate but may leave coverage temp files partially written. The UI communicates this with a "Cancelled — partial results may exist" message.

## Migration Plan

1. Add `coverage_run.rs` to `src-tauri/src/`.
2. Register `run_coverage` and `cancel_coverage` commands in `lib.rs`.
3. Extend `ui.ts` with `coverageRun` slice.
4. Add `runCoverage` / `cancelCoverage` TypeScript wrappers in `lib/wrappers.ts`.
5. Update `Coverage.tsx`: add toolbar (Run / Cancel / Clear buttons) and log panel below the existing tabs.
6. Unit-test the new Zustand slice and the TypeScript wrappers (vitest).
7. No database migrations, no Python changes, no breaking API changes.

## Open Questions

- Should the "Run Coverage" button be disabled when the main pipeline is actively running? (Current leaning: yes — check `PipelineRegistry::active_for_repo` and show a tooltip explaining why.)
- Should the log panel be collapsible? (Current leaning: yes, collapsed by default to avoid visual noise after a successful run.)
