## 1. Refinement module

- [ ] 1.1 Create `playwright_god/refinement.py` with `RefinementLoop`, `Evaluation`, `RefinementConfigError`
- [ ] 1.2 Implement classification (`compile_failed`, `runtime_failed`, `passed_with_gap`, `passed`)
- [ ] 1.3 Implement stop policies (`passed`, `covered`, `stable`) plus `max_attempts` hard cap (8)
- [ ] 1.4 Implement final-attempt selection by `argmax(coverage)` with latest-wins tiebreak
- [ ] 1.5 Centralize secret patterns into `playwright_god/_secrets.py` and reuse in generator + refinement

## 2. Runner & generator deltas

- [ ] 2.1 Add `RunResult.is_actionable_failure()` with the four-way classification
- [ ] 2.2 Add `failure_excerpt` and `coverage_delta` parameters to `PlaywrightTestGenerator.generate`
- [ ] 2.3 Append `Previous attempt failure` and `Coverage delta since last attempt` sections to the prompt when set
- [ ] 2.4 Verify byte-identical prompt for the no-addenda path (regression test)

## 3. Audit log

- [ ] 3.1 Implement `refinement_log.jsonl` writer (append-only, one object per attempt)
- [ ] 3.2 Include `prompt_hash` (stable hash of the assembled prompt) in each entry
- [ ] 3.3 Roundtrip test: read the JSONL, reconstruct prompts, assert hash equality

## 4. CLI

- [ ] 4.1 Add `playwright-god refine "<description>"` subcommand
- [ ] 4.2 Add `--max-attempts`, `--stop-on`, `--coverage-target`, `--retry-on-flake` flags
- [ ] 4.3 Emit a warning when `--max-attempts > 5`
- [ ] 4.4 Map final outcome to a CLI exit code

## 5. Tests

- [ ] 5.1 `tests/unit/test_refinement.py`: scripted attempt sequences for every outcome × stop-policy combo
- [ ] 5.2 `tests/unit/test_refinement.py`: secret redaction regression (token in failure log → `[REDACTED]` in addendum and audit log)
- [ ] 5.3 `tests/unit/test_refinement.py`: argmax-coverage final selection
- [ ] 5.4 `tests/unit/test_runner.py`: classification truth table for `is_actionable_failure()`
- [ ] 5.5 `tests/unit/test_generator.py`: addenda sections appear iff inputs are set; no-addenda byte-identity
- [ ] 5.6 `tests/integration/test_refinement_pipeline.py`: end-to-end against `sample_app` (gated `requires_node`)
- [ ] 5.7 `tests/unit/test_cli.py`: `refine` subcommand + flags

## 6. Docs & polish

- [ ] 6.1 README "Iterative refinement" section with examples and the cost warning
- [ ] 6.2 README example `refinement_log.jsonl` snippet
- [ ] 6.3 Verify `pytest --cov=playwright_god` ≥ 99% with the new module
