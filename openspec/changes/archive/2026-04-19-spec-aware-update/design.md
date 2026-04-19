## Context

After the prior four changes ship, `playwright-god` can run, measure, refine, and structurally understand a target app. What it still can't do is update an existing suite without destroying it. The diff between "what the suite covers today" and "what the flow graph + coverage data say should be covered" is exactly the work the user wants automated. Doing this well requires both a stable mapping from specs back to graph nodes and a policy for when to add vs. update vs. leave alone.

## Goals / Non-Goals

**Goals:**
- Idempotent updates: running `update` twice with no source changes is a no-op.
- Deterministic add/update/keep classification.
- Respect for human edits: a spec marked `@pg-pin` is never modified by the tool.
- Auditable plan: `update_plan.json` and a clear summary on stdout.
- Reuse: every per-spec generation goes through `RefinementLoop` so we get the same convergence guarantees.

**Non-Goals:**
- Refactoring tests for style or modernization. We change tests only when their target node changed or coverage demands it.
- Migrating between Playwright versions. Out of scope.
- Cross-suite consolidation (merging duplicate tests). v1 keeps the existing layout.
- Removing tests. The plan never deletes; orphaned specs are listed under a `review` bucket for the human.

## Decisions

1. **`SpecIndex` is the source of truth for "what does this spec cover?"** Two signals, in priority order:
   - **Explicit `@pg-tags`** at the top of a spec (`// @pg-tags route:GET:/login action:src/Login.tsx:42#submit`). Authoritative.
   - **Heuristic mapping** via tree-sitter: extract `page.goto(...)` URLs → match against route nodes; extract selectors → match against action nodes. Best-effort.
   When the heuristic disagrees with `@pg-tags`, the tag wins and a debug log notes the divergence.
2. **`UpdatePlan` is a typed, serializable record.** Three lists (`add`, `update`, `keep`) plus a fourth informational `review` for orphaned specs. Each entry carries `node_id`, `spec_path` (when applicable), `reason`, and `prior_run_outcome` (when applicable).
3. **`update` always honors `--dry-run` first in CI.** The recommended workflow is `playwright-god update --dry-run > plan.txt` in PRs and `playwright-god update` on merge. Documented.
4. **`@pg-pin` is the escape hatch.** A spec with `// @pg-pin` at the top is never in the `update` bucket regardless of node drift. It can still appear in `review` with a "pinned, but its target changed" note.
5. **Per-spec refinement reuses `RefinementLoop` with a seed.** `RefinementLoop.run(description, seed_spec=path)` reads the existing spec, includes its source in the prompt under a `Current spec to refine` section, and proceeds normally. The audit log records `seed_path`.
6. **Add operations get fresh refinement.** No seed; same default policy as `refine` (3 attempts, stop on `passed`).
7. **Update operations have a stricter stop.** Default `stop_on="passed"`, but with `--strict-update` the policy becomes `covered` so updates aren't accepted unless coverage at least matches the prior baseline. Prevents silent regressions.
8. **Orphan policy is conservative.** A spec with no resolvable node IDs (and no `@pg-pin`) is listed in `review` with a "no matching graph node — likely stale or hand-written" note. The user decides; we never delete.
9. **The plan is committable.** `update_plan.json` is small and human-readable; teams can commit it as a record of what changed and why.

## Risks / Trade-offs

- **Heuristic mismapping.** A spec might exercise route X but the heuristic infers Y. Mitigated by `@pg-tags` as the authoritative override and by surfacing every heuristic mapping in `--dry-run` output.
- **Update churn.** Even small graph changes (a route rename) can sweep many specs. Mitigated by including the diff context in the refinement prompt so the LLM produces minimal edits, and by `--strict-update` to gate on coverage.
- **Pinned specs going stale.** A `@pg-pin` spec whose target route is gone will pass forever covering nothing. Mitigated by `review` bucket reporting "pinned, target missing" so humans see it.
- **Test framework churn (Vitest, Cypress, etc.).** The `SpecIndex` is Playwright-specific in v1. Documented; extension is a future change.
- **Performance on large suites.** Indexing scales linearly in spec count; tree-sitter parsing is fast but not free. Mitigated by caching index results keyed on spec content hash, in `<persist-dir>/spec_index.json`.
- **Race with hand-edits.** A user editing while `update` runs could lose work. Mitigated by writing through a temp file + atomic rename, and by refusing to run when the working tree has unstaged changes to spec files (`--allow-dirty` overrides).
