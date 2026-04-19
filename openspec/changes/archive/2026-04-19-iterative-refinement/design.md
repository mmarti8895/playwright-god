## Context

`PlaywrightTestGenerator.generate()` produces a spec from a single LLM call. In practice, the first attempt has a meaningful failure rate: missing imports, hallucinated selectors, race conditions, or simply a passing test that doesn't move coverage. A loop that observes the run output and re-prompts is the smallest abstraction that converts these failures from user toil into automated convergence.

Iteration also creates new risks: unbounded loops, runaway token spend, and leaking secrets from failure logs into prompts. The design has to make those failure modes hard.

## Goals / Non-Goals

**Goals:**
- Bounded, observable loop with first-class stop conditions.
- A typed `Evaluation` per attempt so behavior is testable without LLM calls.
- Per-attempt audit trail (`refinement_log.jsonl`) usable for postmortem and for future "what worked" fine-tuning.
- Hard secret-redaction on every prompt addendum derived from failure logs.
- Backward compatibility: the existing `generate` command keeps single-shot semantics; `refine` is the opt-in iterative entry point.

**Non-Goals:**
- Autonomous open-ended agent behavior. Bounded by attempt cap and stop conditions.
- Running the loop in parallel across descriptions (sequential v1).
- LLM cost accounting / budget caps (deferred; documented as a future change).
- Cross-attempt prompt fine-tuning. Each attempt builds on the last via deterministic addenda, not learned weights.

## Decisions

1. **The loop is a pure orchestrator.** `RefinementLoop(generator, runner, evaluator, max_attempts=3)` composes existing components and owns no domain logic itself. This makes it trivially mockable.
2. **Four canonical outcomes per attempt.**
   - `compile_failed`: the spec didn't even start (TypeScript error, missing import). Addendum: paste the compile error verbatim and a "fix the spec to compile against `@playwright/test` v1.x" instruction.
   - `runtime_failed`: spec ran, at least one assertion failed or selector timed out. Addendum: failing test name + truncated error + last-known-good DOM excerpt if available.
   - `passed_with_gap`: spec passed but coverage delta < ε. Addendum: include uncovered excerpts ranked by feature membership.
   - `passed`: spec passed AND coverage moved by ≥ ε OR no coverage data is being tracked. Stop.
3. **Stop conditions are explicit and orthogonal.**
   - `passed` (default): stop on first `passed`.
   - `covered`: stop only when feature coverage hits a configurable target (default 95%).
   - `stable`: stop when two consecutive attempts produce zero coverage delta and the previous outcome was `passed_with_gap` (i.e., we've plateaued).
   - Hard cap (`max_attempts`, default 3, configurable up to 8) overrides all of the above.
4. **`refinement_log.jsonl` per run.** One JSON object per attempt: `attempt`, `prompt_hash`, `spec_path`, `run_summary`, `evaluation`, `next_prompt_addendum`. Stored under `<persist-dir>/runs/<timestamp>/refinement_log.jsonl`. Append-only, replayable.
5. **Secret redaction is the loop's responsibility, not the generator's.** Before any failure excerpt is fed back into the next prompt, it passes through the same `_SECRET_PATTERNS` scrubber the output redactor uses (centralized into `playwright_god/_secrets.py`). This is enforced by a unit test.
6. **`is_actionable_failure()` lives on `RunResult`.** Returns the canonical outcome. This avoids string-sniffing inside the loop and gives `spec-aware-update` the same primitive.
7. **Idempotent spec writes.** Each attempt overwrites the same `-o` path; the audit log preserves history. Prevents directory pollution and keeps the user-visible artifact stable.
8. **Default attempts kept low (3).** Real-world LLM cost matters; the loop is opt-in. A loud warning prints when `--max-attempts > 5`.

## Risks / Trade-offs

- **Token cost grows linearly with attempts.** Mitigated by low default cap, an explicit warning at higher caps, and (future) cost accounting in a separate change.
- **Pathological non-convergence.** A spec might oscillate (attempt A passes, B regresses). Mitigated by the `stable` stop condition and by always keeping the highest-coverage attempt as the final artifact (`final_attempt = argmax(coverage)`).
- **Secret leakage into prompts.** Mitigated by mandatory redaction step + a regression test that asserts no `sk-`, `Bearer `, or known credential pattern reaches the next prompt addendum.
- **Flaky tests indistinguishable from real failures.** Mitigated by a `--retry-on-flake N` flag (default 0) that re-runs the same spec before counting as `runtime_failed`. Documented but conservative by default.
- **Audit log size.** JSONL is append-only; capped at one file per run (no global growth). Documented.
- **Loop coupling to LLM nondeterminism.** Even with the same prompt addendum the next attempt may behave differently. Mitigated by `prompt_hash` in the audit log so the human can see exactly what was sent.
