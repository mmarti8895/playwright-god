## 1. SpecIndex

- [x] 1.1 Create `playwright_god/spec_index.py` with `SpecIndex`, `SpecEntry`
- [x] 1.2 Implement `@pg-tags` parser (authoritative)
- [x] 1.3 Implement heuristic extraction (`page.goto`, selectors) via tree-sitter
- [x] 1.4 Implement content-hash caching to `<persist-dir>/spec_index.json`
- [x] 1.5 Log tag/heuristic divergences at debug level

## 2. DiffPlanner

- [x] 2.1 Create `playwright_god/update_planner.py` with `DiffPlanner`, `UpdatePlan`, `PlanEntry`
- [x] 2.2 Implement bucket classification (`add`, `update`, `keep`, `review`)
- [x] 2.3 Implement `prior_run_outcome` lookup from the latest run artifacts
- [x] 2.4 Implement `@pg-pin` exclusion logic
- [x] 2.5 Round-trip serialization to `update_plan.json` (≤ 64 KB target, 2-space indent)

## 3. RefinementLoop seed support

- [x] 3.1 Add `seed_spec: Path | None` parameter to `RefinementLoop.run`
- [x] 3.2 Insert `Current spec to refine` section into the first prompt when `seed_spec` is set
- [x] 3.3 Record `seed_path` in the audit log
- [x] 3.4 Verify byte-identical prompt in the no-seed path (regression test)

## 4. FlowGraph covering_specs

- [x] 4.1 Add `covering_specs: list[str]` field to `Route`/`View`/`Action`
- [x] 4.2 Implement `FlowGraph.attach_spec_index(spec_index)` to populate it
- [x] 4.3 Default to `[]` when no spec index is attached

## 5. CLI

- [x] 5.1 Add `playwright-god update` subcommand
- [x] 5.2 Add `--dry-run`, `--strict-update`, `--allow-dirty`, `--persist-dir` flags
- [x] 5.3 Print per-bucket summary on completion
- [x] 5.4 Refuse to run on dirty spec files unless `--allow-dirty` is set

## 6. Tests

- [x] 6.1 `tests/unit/test_spec_index.py`: `@pg-tags`, heuristics, divergence, cache hit/miss
- [x] 6.2 `tests/unit/test_update_planner.py`: every bucket × every reason
- [x] 6.3 `tests/unit/test_update_planner.py`: `@pg-pin` exclusion + `pinned, target missing`
- [x] 6.4 `tests/unit/test_update_planner.py`: idempotency (run twice, second plan is empty)
- [x] 6.5 `tests/unit/test_refinement.py`: `seed_spec` path produces seed section + records `seed_path`
- [x] 6.6 `tests/unit/test_flow_graph.py`: `covering_specs` populated/empty cases
- [x] 6.7 `tests/integration/test_update_pipeline.py`: end-to-end against `sample_app` (gated `requires_node`)
- [x] 6.8 `tests/unit/test_cli.py`: `update`, `--dry-run`, `--strict-update`, dirty-tree refusal

## 7. Docs & polish

- [x] 7.1 README "Updating an existing suite" section with the dry-run-first workflow
- [x] 7.2 Document the `@pg-tags` and `@pg-pin` comment conventions with examples
- [x] 7.3 Add a worked example: route rename → `update` plan → applied diff
- [x] 7.4 Verify `pytest --cov=playwright_god` ≥ 99% with the new modules
