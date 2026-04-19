## Context

`playwright-god`'s value proposition is "drive a repo toward 100% Playwright coverage." Today the planner ranks features by inferred salience (filename heuristics, keyword evidence) — not by what is actually untested. That means the tool can happily regenerate tests for already-covered areas and miss large gaps.

The coverage data is naturally split: Playwright/Chromium can produce per-file JS coverage for the frontend, but backend coverage requires the user's own runtime (Python `coverage`, Node Istanbul, etc.). Rather than try to be a universal coverage runner, this change *brackets* a backend coverage command around the Playwright run and merges the results.

## Goals / Non-Goals

**Goals:**
- A single, normalized `MergedCoverageReport` that downstream features (planning, refinement) can consume without knowing the source.
- Frontend (JS) coverage works out of the box once `--coverage` is passed.
- Backend coverage is opt-in via `--backend-coverage "<cmd>"` and is language-agnostic (we shell out).
- Plans and prompts visibly prioritize the biggest gaps, with an auditable "Coverage delta" section.
- `MemoryMap` schema evolves backward-compatibly (`schema_version` bump + missing-field tolerance in loader).

**Non-Goals:**
- Reimplementing coverage tools. We orchestrate `coverage`/Istanbul; we don't replace them.
- Branch / mutation coverage. Line + per-route coverage is v1.
- Live coverage HUD or watch mode.
- Coverage for unit tests outside Playwright's run.

## Decisions

1. **JS coverage via an autouse Playwright fixture, not an external tool.** We ship `playwright_god/_assets/coverage_fixture.ts`. When `--coverage` is on, the runner injects an `import "@playwright-god/coverage";` line at the top of each generated spec (or via `playwright.config.ts` modification when present). Trade-off: relies on Playwright's `page.coverage` API (Chromium-only). Documented limitation; Firefox/WebKit fallback is "coverage skipped, warning logged."
2. **Backend coverage as a subprocess sandwich.** `CoverageCollector.collect(backend_cmd, run_callable)` does:
   - `subprocess.run("coverage erase")` (or user-provided `pre_cmd`)
   - start backend in coverage mode (user-provided `start_cmd`, e.g. `coverage run -m uvicorn app:app --port 8000`)
   - call `run_callable()` (the Playwright run)
   - signal backend to stop, run `coverage json -o .pg_coverage.json`
   - parse the JSON into `CoverageReport(source="backend")`
   This keeps the contract narrow and avoids language assumptions.
3. **`CoverageReport` is the single shape.** Both sources produce the same record:
   ```
   CoverageReport(
       source: Literal["frontend", "backend"],
       files: dict[str, FileCoverage(total_lines, covered_lines, missing_line_ranges)],
       generated_at: datetime,
   )
   ```
   `MergedCoverageReport` is just `frontend | backend | merge_meta`.
4. **Memory-map schema bump is additive.** `schema_version` goes `2.0 → 2.1`. The loader treats `coverage` as optional; existing memory maps continue to load. `MemoryMap.with_coverage(report)` produces an updated map.
5. **Planner sorts by gap size, not absolute size.** A 1000-line file at 95% covered (50 missing lines) outranks a 200-line file at 50% covered (100 missing lines) only if we sort by absolute uncovered lines — this is the right behavior for "drive to 100%." A `--prioritize percent` flag offers the alternative.
6. **Prompt-side coverage injection is bounded.** We include up to N (default 12) uncovered line excerpts per prompt to stay within token budgets, ranked by feature membership. Documented in tasks.
7. **`coverage report` is a read-only command.** It loads the saved coverage JSON from the persist dir and prints text/JSON/HTML. No re-running, no mutation. Cheap and CI-friendly.

## Risks / Trade-offs

- **Browser-engine limitation.** JS coverage only works under Chromium. Mitigated by detecting the browser at runtime and emitting a structured warning rather than failing.
- **Backend command divergence.** The user controls the backend coverage command, so misconfiguration produces empty/garbage reports. Mitigated by a strict JSON schema check on the parsed report and a clear warning when the file count is zero.
- **Schema compatibility.** Bumping to `2.1` could break consumers that hard-check `schema_version == "2.0"`. Mitigated by writing the loader to accept any `2.x` and add a one-line entry to the README's Memory Map section.
- **Token budget pressure.** Including coverage gaps in the prompt grows context. Mitigated by the N-excerpt cap and by ranking gaps before truncation.
- **Subprocess lifecycle on backend.** Stopping a `coverage run` cleanly across platforms is tricky. Mitigated by sending SIGINT first then SIGTERM after a configurable timeout; fully documented in the runner code.
- **False sense of completeness.** Hitting 100% line coverage is not the same as testing every flow. The README will explicitly call this out; the planner uses coverage as a *prioritizer*, not as the sole oracle (the existing `feature_map` evidence still ranks).
