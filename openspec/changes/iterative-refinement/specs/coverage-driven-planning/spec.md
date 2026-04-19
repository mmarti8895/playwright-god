## MODIFIED Requirements

### Requirement: The generator prompt SHALL accept failure-excerpt and coverage-delta addenda

`PlaywrightTestGenerator.generate` SHALL accept optional `failure_excerpt: str | None` and `coverage_delta: CoverageDelta | None` parameters and SHALL incorporate them into the prompt under dedicated, clearly-labeled sections in addition to the existing `Uncovered code (gaps)` block, so that the iterative-refinement loop can supply per-attempt context without bypassing the generator.

#### Scenario: Failure excerpt appears under a dedicated section

- **WHEN** `generate(..., failure_excerpt="TypeError at app.ts:42")` is invoked
- **THEN** the constructed prompt contains a section labeled `Previous attempt failure` whose body includes the excerpt verbatim (already redacted by the caller)

#### Scenario: Coverage delta appears as a structured hint

- **WHEN** `generate(..., coverage_delta=delta)` is invoked with a non-empty delta
- **THEN** the prompt contains a `Coverage delta since last attempt` section listing newly-covered and still-uncovered files

#### Scenario: Backward compatibility is preserved

- **WHEN** `generate(...)` is invoked without `failure_excerpt` or `coverage_delta`
- **THEN** the prompt is byte-identical to the prompt produced before this change for the same inputs
