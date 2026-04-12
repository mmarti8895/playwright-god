<!--
Sync Impact Report
Version change: template -> 1.0.0
Modified principles:
- Added I. Code Quality Is Product Quality
- Added II. Tests Are the Release Gate
- Added III. Consistent User Experience by Default
- Added IV. Performance and Local-First Reliability
- Added V. Documentation and Evidence Stay in Sync
Added sections:
- Operational Standards
- Delivery Workflow & Quality Gates
Removed sections:
- None
Templates requiring updates:
- updated: .specify/templates/plan-template.md
- updated: .specify/templates/spec-template.md
- updated: .specify/templates/tasks-template.md
Follow-up TODOs:
- None
-->
# playwright-god Constitution

## Core Principles

### I. Code Quality Is Product Quality
All changes MUST be minimal, scoped, and idiomatic for this Python-first CLI
codebase. Public modules, functions, classes, and CLI flags MUST have clear
names, explicit failure modes, and no dead paths left behind for future cleanup.
New abstractions or dependencies MUST only be introduced when they reduce
complexity, improve testability, or measurably improve maintainability.
Rationale: `playwright-god` earns trust through readable behavior and predictable
local workflows, so code quality is part of the shipped product.

### II. Tests Are the Release Gate
Every behavior change MUST add or update deterministic tests at the lowest
useful level and expand integration or end-to-end coverage when a workflow,
contract, or user journey changes. New or changed code MUST reach 100% unit test
coverage unless an explicit exception is approved before implementation. Tests
MUST avoid real LLM calls, non-local backends, flaky sleeps, and uncontrolled
time or filesystem coupling when mocks, fixtures, or dependency injection can
provide equivalent confidence. Rationale: reliable local verification is core to
the tool's promise and cannot be deferred.

### III. Consistent User Experience by Default
CLI commands, flags, stdout and stderr behavior, generated artifact structure,
and sample workflows MUST stay consistent across `index`, `generate`, and
`plan`. User-facing text MUST be actionable, concise, and stable enough for docs
and automated tests; any intentional change to wording, output shape, or common
flows MUST be reflected in tests and documentation in the same change.
Generated Playwright code and fixtures MUST prefer accessible, stable selectors
and readable defaults over brittle shortcuts. Rationale: consistent UX keeps the
tool understandable for both humans and automation.

### IV. Performance and Local-First Reliability
Default local workflows MUST remain fast enough for tight development loops.
Changes MUST avoid unnecessary full rescans, heavyweight startup work, hidden
downloads, or network-dependent behavior on common offline paths. Every network
or external-process boundary MUST define timeouts, cancellation behavior, and
bounded retries or fallbacks. When a change is expected to materially affect
indexing time, search latency, generation latency, or test runtime, the plan and
verification steps MUST include a measurable performance check. Rationale:
performance regressions directly damage the value of a local-first developer
tool.

### V. Documentation and Evidence Stay in Sync
README content, test documentation, sample fixtures, and spec-kit templates MUST
be updated whenever commands, flags, workflows, expectations, or performance
constraints change. Plans and tasks MUST state how code quality, testing,
user-facing consistency, and performance will be validated before implementation
starts. A change is not complete until the tests, docs, and verification
commands tell the same story. Rationale: accurate documentation and evidence
prevent drift between intended behavior and actual behavior.

## Operational Standards

- The primary implementation surface is the `playwright_god/` Python package,
  with validation split across `tests/unit/`, `tests/integration/`, and
  `tests/e2e/`.
- Offline and local-first verification is the default. `MockEmbedder` and
  `TemplateLLMClient` or equivalent deterministic substitutes MUST remain
  available for tests and local smoke checks.
- Provider integrations, secrets, and networked behavior MUST remain optional.
  Secrets MUST enter through environment variables or approved config files and
  MUST never be committed or printed into generated artifacts.
- User-visible Playwright examples and generated tests MUST prefer accessible
  semantics, stable selectors, and readable flow structure over terse but brittle
  code.
- If a change is expected to add more than trivial runtime or startup cost, the
  spec or plan MUST document the expected impact and how the regression will be
  measured or contained.

## Delivery Workflow & Quality Gates

1. Gather facts from the repository before making changes, including affected
   code, tests, docs, and existing workflows.
2. Write or update the relevant spec-kit artifacts so the constitution check
   explicitly covers code quality, testing, UX consistency, and performance.
3. Implement in small, reviewable increments and add or update tests alongside
   production changes, not after them.
4. Run the smallest relevant unit, integration, and end-to-end test commands for
   the touched behavior, plus coverage for changed modules.
5. Update README and test-facing documentation when commands, flows, or
   expectations change.
6. Complete a self-review for correctness, readability, user-facing consistency,
   failure handling, and performance impact before requesting review or merging.

## Governance

This constitution supersedes conflicting local process guidance for feature
planning and delivery. Amendments MUST include the rationale, the affected
principles or sections, and any template or documentation updates needed to keep
the workflow aligned. Versioning follows semantic intent: MAJOR for removing or
incompatibly redefining a principle, MINOR for adding a principle or materially
expanding a requirement, and PATCH for clarifications that do not change the
required behavior. Every plan, task list, and review MUST check compliance with
this constitution; unresolved violations MUST be documented explicitly with a
justified exception. `AGENTS.md` and `README.md` remain operational companions
but do not override this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-04-11 | **Last Amended**: 2026-04-11
