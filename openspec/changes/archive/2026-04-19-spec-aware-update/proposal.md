## Why

Once a project has a real Playwright test suite, regenerating from scratch is wasteful and destructive: it loses hand-edits, blows away stable baselines, and produces churn that humans will reject. The tool needs to *update* an existing suite — adding tests for new flow-graph nodes, rewriting tests whose target route/action changed, and leaving green tests alone. Without this, `playwright-god` is a one-shot scaffolder, not a steady-state companion.

## What Changes

- Add a `SpecIndex` that scans an existing `tests/` directory, parses each `.spec.ts`, and maps each test to the flow-graph node IDs it exercises (via heuristics + explicit `@pg-tags` comments).
- Add a `DiffPlanner` that compares the current `FlowGraph` against the `SpecIndex` and produces a typed `UpdatePlan` with three lists:
  - `add`: graph nodes with no covering test → generate new specs.
  - `update`: existing specs whose target node changed (route renamed, action signature drifted, last run failed) → regenerate with diff context.
  - `keep`: passing specs whose target nodes are unchanged → leave untouched.
- Add a `playwright-god update` subcommand that executes an `UpdatePlan` end-to-end (delegating to `RefinementLoop` per generated/updated spec) and prints a human-readable summary.
- Add a `--dry-run` flag that prints the plan without writing or running anything.
- Add support for `@pg-tags route:GET:/login action:src/Login.tsx:42#submit` comments at the top of a spec so users can pin a test to graph nodes deterministically (and so generated specs always include them).
- Persist `update_plan.json` per run for audit and CI consumption.

## Capabilities

### New Capabilities
- `spec-update`: Diffing an existing spec suite against the current flow graph + coverage and producing an executable `UpdatePlan` of add/update/keep operations.

### Modified Capabilities
- `iterative-refinement`: `RefinementLoop` accepts an existing spec path as a "seed" so an `update` operation refines the existing test in place rather than generating from scratch.
- `flow-graph`: nodes gain an optional `covering_specs: list[str]` field populated by `SpecIndex` so the graph itself can answer "which specs cover this route?".

## Impact

- **Code**: new `playwright_god/spec_index.py`, `playwright_god/update_planner.py`, modifications to `refinement.py` (seed support), `flow_graph.py` (covering_specs field), `cli.py` (new `update` subcommand + `--dry-run`).
- **Dependencies**: reuses `tree-sitter`/`tree-sitter-typescript` from `flow-graph-extraction`. No new required deps.
- **Tests**: new `tests/unit/test_spec_index.py`, `tests/unit/test_update_planner.py`, integration test `tests/integration/test_update_pipeline.py` (gated `requires_node`).
- **Docs**: README "Updating an existing suite" section; `@pg-tags` comment convention documented.
- **Downstream**: this is the terminal change in the roadmap — together with the previous four, it converts `playwright-god` from a one-shot scaffolder into a steady-state coverage-driving companion.
