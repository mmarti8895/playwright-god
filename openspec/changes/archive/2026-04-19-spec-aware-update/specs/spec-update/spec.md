## ADDED Requirements

### Requirement: A SpecIndex SHALL map existing Playwright specs to flow-graph node IDs

The `playwright_god.spec_index.SpecIndex` SHALL scan a directory of `.spec.ts` files, parse each spec, and produce a mapping from spec path to a list of `FlowGraph` node IDs it exercises. Mapping SHALL prefer explicit `@pg-tags` comments and SHALL fall back to heuristic extraction of `page.goto(...)` URLs and selectors.

#### Scenario: Explicit @pg-tags are authoritative

- **WHEN** a spec begins with `// @pg-tags route:GET:/login action:src/Login.tsx:42#submit`
- **THEN** the index entry for that spec contains exactly those two node IDs, regardless of heuristic findings

#### Scenario: Heuristic mapping covers untagged specs

- **WHEN** a spec contains `await page.goto("/checkout")` and no `@pg-tags`
- **THEN** the index entry contains `route:GET:/checkout` (or its closest match in the graph)

#### Scenario: Tag/heuristic divergence is logged but tag wins

- **WHEN** a spec is tagged `route:GET:/a` but its `page.goto` heuristic resolves to `route:GET:/b`
- **THEN** the index entry contains only `route:GET:/a` and a debug log line notes the divergence

#### Scenario: Index is cached by content hash

- **WHEN** the index is built twice in a row with no spec changes
- **THEN** the second build reads from `<persist-dir>/spec_index.json` and re-parses zero specs

### Requirement: A DiffPlanner SHALL produce a typed UpdatePlan with add/update/keep/review buckets

The `playwright_god.update_planner.DiffPlanner` SHALL compare the current `FlowGraph` (with optional coverage) against a `SpecIndex` and SHALL produce an `UpdatePlan` with four lists: `add`, `update`, `keep`, `review`. Each entry SHALL carry `node_id` (when applicable), `spec_path` (when applicable), `reason`, and `prior_run_outcome` (when applicable).

#### Scenario: New graph node with no covering spec lands in `add`

- **WHEN** the graph contains `route:POST:/api/orders` and no spec maps to it
- **THEN** the plan's `add` list contains an entry with `node_id == "route:POST:/api/orders"` and `reason == "no covering spec"`

#### Scenario: Spec whose target node drifted lands in `update`

- **WHEN** a spec maps to `route:GET:/login` and the latest graph renamed that route to `route:GET:/auth/login`
- **THEN** the plan's `update` list contains an entry with `spec_path` set, `node_id == "route:GET:/auth/login"`, and `reason == "target node renamed"`

#### Scenario: Spec whose prior run failed lands in `update`

- **WHEN** a spec maps to a still-existing node but the prior `RunResult.status` was `"failed"`
- **THEN** the plan's `update` list contains the spec with `reason == "prior run failed"` and `prior_run_outcome == "failed"`

#### Scenario: Passing spec on unchanged node lands in `keep`

- **WHEN** a spec maps to an unchanged node and the prior run passed
- **THEN** the plan's `keep` list contains the spec and the spec is not modified by `update`

#### Scenario: Orphan spec lands in `review`

- **WHEN** a spec resolves to no node IDs and is not tagged `@pg-pin`
- **THEN** the plan's `review` list contains the spec with `reason == "no matching graph node"`

### Requirement: @pg-pin SHALL exclude a spec from update operations

A spec whose first non-blank line contains `// @pg-pin` SHALL NOT appear in `add` or `update` buckets and SHALL be left untouched on disk. It MAY appear in `review` with a `"pinned"` reason when its target node has changed.

#### Scenario: Pinned spec is never modified

- **WHEN** an `update` is executed and a `@pg-pin` spec exists
- **THEN** the spec's bytes on disk are unchanged after the run

#### Scenario: Pinned spec with stale target appears in review

- **WHEN** a `@pg-pin` spec's tagged node is no longer in the graph
- **THEN** the plan's `review` list contains the spec with `reason == "pinned, target missing"`

### Requirement: An `update` CLI subcommand SHALL execute an UpdatePlan end-to-end

The CLI SHALL provide `playwright-god update [--dry-run] [--strict-update] [--allow-dirty] [--persist-dir DIR]` that builds an `UpdatePlan`, executes `add` and `update` entries via `RefinementLoop`, and prints a per-bucket summary.

#### Scenario: --dry-run prints the plan without writing or running

- **WHEN** `playwright-god update --dry-run` is invoked
- **THEN** the plan is printed (and `update_plan.json` written) but no spec files are created/modified and no Playwright runs are executed

#### Scenario: Default invocation executes add and update via RefinementLoop

- **WHEN** `playwright-god update` is invoked with a plan containing 1 `add` and 1 `update`
- **THEN** exactly 2 `RefinementLoop` runs occur (one per entry), `keep` specs are untouched, and a summary `add: 1, update: 1, keep: N, review: M` is printed

#### Scenario: --strict-update gates on coverage parity

- **WHEN** `playwright-god update --strict-update` is invoked and a refined spec lowers coverage of its target node versus the prior baseline
- **THEN** the refined spec is discarded, the original is left in place, and the entry is moved to `review` with `reason == "refined spec regressed coverage"`

#### Scenario: Dirty working tree blocks the run unless overridden

- **WHEN** `playwright-god update` is invoked in a git working tree with unstaged changes to spec files
- **THEN** the CLI exits non-zero with a message naming the dirty files and instructing the user to commit/stash or pass `--allow-dirty`

#### Scenario: Idempotency

- **WHEN** `playwright-god update` is invoked twice in a row with no source changes between invocations
- **THEN** the second invocation produces an empty `add` and `update` plan and modifies no files

### Requirement: An update_plan.json artifact SHALL persist the plan for audit

`update_plan.json` SHALL be written under `<persist-dir>/runs/<timestamp>/` containing the four buckets in JSON form, suitable for committing to the repository or consuming in CI.

#### Scenario: Plan JSON round-trips

- **WHEN** an `UpdatePlan` is serialized to `update_plan.json` and re-loaded
- **THEN** the loaded plan equals the original (bucket order preserved, all fields intact)

#### Scenario: Plan is human-readable and small

- **WHEN** an `update_plan.json` is written for a 50-spec suite
- **THEN** the file is < 64 KB and uses 2-space indentation
