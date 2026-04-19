## MODIFIED Requirements

### Requirement: The planner SHALL prioritize feature areas by uncovered size

When a memory map carries a coverage block, `playwright-god plan` SHALL order feature areas by descending count of uncovered lines (default), with `--prioritize percent` selecting descending uncovered-percentage ordering instead. **When a flow graph is also present, the planner SHALL additionally annotate each area with its uncovered routes and actions, and SHALL include `--prioritize routes` selecting descending count of uncovered routes as the primary key.**

#### Scenario: Default ordering targets the biggest gap first

- **WHEN** `plan` runs against a memory map where feature `auth` has 120 uncovered lines and feature `nav` has 30 uncovered lines
- **THEN** `auth` appears before `nav` in the generated Markdown plan

#### Scenario: `--prioritize percent` switches the ordering

- **WHEN** `plan --prioritize percent` runs against a memory map where feature `auth` is at 60% covered and feature `nav` is at 20% covered
- **THEN** `nav` appears before `auth` in the generated Markdown plan

#### Scenario: `--prioritize routes` orders by uncovered routes

- **WHEN** `plan --prioritize routes` runs against a memory map with a flow graph where feature `checkout` has 5 uncovered routes and feature `auth` has 1 uncovered route
- **THEN** `checkout` appears before `auth` in the generated Markdown plan

#### Scenario: Plan includes a Coverage Delta section

- **WHEN** `plan` runs with a coverage-bearing memory map
- **THEN** the output Markdown contains a `## Coverage Delta` section listing top-N gaps with file paths and line ranges, and (when a flow graph is present) the section also lists uncovered route/action IDs

### Requirement: The generator prompt SHALL include uncovered-line excerpts as RAG context

When coverage data is present, `PlaywrightTestGenerator.generate` SHALL include up to N (default 12, configurable) uncovered line excerpts in the prompt, ranked by feature membership for the requested description. **When a flow graph is also present, the prompt SHALL additionally include the relevant subgraph (up to M routes, default 5, plus their immediate views and actions), so the LLM is told which routes/actions to exercise rather than asked to guess.**

#### Scenario: Uncovered excerpts are added to the prompt

- **WHEN** `generate "checkout flow"` is invoked with a memory map whose `checkout` feature has uncovered lines in `pay.ts:42-58` and `cart.ts:10-12`
- **THEN** the constructed prompt contains those line ranges verbatim under a `Uncovered code (gaps)` section

#### Scenario: Excerpt count is capped to protect token budget

- **WHEN** the relevant feature has 50 uncovered excerpts and the cap is the default 12
- **THEN** at most 12 excerpts appear in the prompt and a debug log line records the truncation count

#### Scenario: Flow-graph subgraph is included when present

- **WHEN** `generate "checkout flow"` is invoked with a memory map containing a flow graph and `checkout` includes routes `route:POST:/cart` and `route:POST:/checkout`
- **THEN** the prompt contains a `Relevant routes & actions` section listing both route IDs (and connected view/action IDs) up to the configured M cap
