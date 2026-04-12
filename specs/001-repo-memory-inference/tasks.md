# Tasks: Repository Memory Inference

**Input**: Design documents from `/specs/001-repo-memory-inference/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are REQUIRED. Every user story includes deterministic unit and
integration coverage tasks, and changed code must reach 100% unit coverage.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the repo, fixtures, and docs for Python Playwright output
and feature-correlation work.

- [X] T001 Update implementation notes and Python Playwright expectations in `README.md`, `tests/README.md`, and `AGENTS.md`
- [X] T002 [P] Expand repository-analysis fixtures for feature-correlation scenarios in `tests/fixtures/sample_app/index.html`, `tests/fixtures/sample_app/app.js`, and `tests/conftest.py`
- [X] T003 [P] Create task-target test modules for the feature in `tests/unit/test_feature_map.py` and `tests/integration/test_feature_memory_pipeline.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared domain model and compatibility layers that all
stories depend on.

**CRITICAL**: No user story work should begin until this phase is complete.

- [X] T004 Create the shared feature-correlation domain model in `playwright_god/feature_map.py`
- [X] T005 [P] Add deterministic unit coverage for feature entities, evidence records, and confidence scoring in `tests/unit/test_feature_map.py`
- [X] T006 Extend memory-map schema helpers for feature-aware metadata in `playwright_god/memory_map.py`
- [X] T007 [P] Add backward-compatible memory-map serialization tests in `tests/unit/test_memory_map.py`
- [X] T008 Add Python Playwright output helpers and prompt-format utilities in `playwright_god/generator.py`
- [X] T009 [P] Add generator regression tests for Python Playwright output shape in `tests/unit/test_generator.py`

**Checkpoint**: Shared feature-memory model and Python generation foundations
are ready for story work.

---

## Phase 3: User Story 1 - Build Repository Understanding (Priority: P1) MVP

**Goal**: Read a repository and return feature-oriented understanding with
artifact relationships a reviewer can inspect.

**Independent Test**: Run repository analysis on the sample repo and on
`playwright-god` itself, then verify the output groups files into distinct
feature areas with traceable evidence references.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US1] Add CLI coverage for feature-oriented repository analysis in `tests/unit/test_cli.py`
- [X] T011 [P] [US1] Add integration coverage for repository feature grouping in `tests/integration/test_pipeline.py` and `tests/integration/test_feature_memory_pipeline.py`
- [X] T012 [P] [US1] Extend self-analysis regression coverage for feature summaries in `tests/integration/test_self.py`

### Implementation for User Story 1

- [X] T013 [US1] Implement repository artifact discovery and feature grouping in `playwright_god/feature_map.py`
- [ ] T014 [US1] Feed crawler and chunk metadata into feature inference in `playwright_god/crawler.py` and `playwright_god/indexer.py`
- [X] T015 [US1] Integrate feature-oriented analysis into the `index` workflow in `playwright_god/cli.py`
- [X] T016 [US1] Add reviewable feature summary formatting for CLI output in `playwright_god/feature_map.py` and `playwright_god/cli.py`

**Checkpoint**: Repository analysis produces inspectable feature areas and
artifact correlations without requiring downstream generation work.

---

## Phase 4: User Story 2 - Infer Test Opportunities (Priority: P2)

**Goal**: Infer evidence-backed Python Playwright tests from repository
understanding.

**Independent Test**: Generate test recommendations from the analyzed sample
repo and verify they are grouped by feature, written as user journeys, cite
evidence, and output Python Playwright code.

### Tests for User Story 2

- [X] T017 [P] [US2] Add unit coverage for evidence-backed Python Playwright generation in `tests/unit/test_generator.py`
- [X] T018 [P] [US2] Add CLI coverage for feature-aware `generate` and `plan` behavior in `tests/unit/test_cli.py`
- [X] T019 [P] [US2] Extend integration coverage for inferred test opportunities in `tests/integration/test_pipeline.py` and `tests/integration/test_self.py`

### Implementation for User Story 2

- [X] T020 [US2] Implement test-opportunity ranking and uncertainty labeling in `playwright_god/feature_map.py`
- [X] T021 [US2] Rewrite offline templates and system prompts for Python Playwright output in `playwright_god/generator.py`
- [X] T022 [US2] Update `generate` and `plan` command behavior for feature-aware Python outputs in `playwright_god/cli.py`
- [X] T023 [US2] Add evidence and confidence formatting for generated plans and prompts in `playwright_god/memory_map.py` and `playwright_god/generator.py`

**Checkpoint**: The CLI can generate Python Playwright tests and plans that are
backed by repository feature evidence and visibly communicate uncertainty.

---

## Phase 5: User Story 3 - Save and Reuse Streamlined Memory Maps (Priority: P3)

**Goal**: Save compact feature-aware memory maps and reuse them efficiently in
later planning and generation flows.

**Independent Test**: Save a feature-aware memory map, reuse it in later
`generate` and `plan` runs, and verify the reused output remains consistent
while avoiding a full rebuild.

### Tests for User Story 3

- [X] T024 [P] [US3] Add unit coverage for persisted feature-memory snapshots in `tests/unit/test_memory_map.py`
- [X] T025 [P] [US3] Add CLI persistence and reload coverage in `tests/unit/test_cli.py`
- [X] T026 [P] [US3] Extend integration coverage for memory-map reuse in `tests/integration/test_feature_memory_pipeline.py` and `tests/integration/test_self.py`

### Implementation for User Story 3

- [X] T027 [US3] Extend saved memory-map schema with features, correlations, and test opportunities in `playwright_god/memory_map.py`
- [X] T028 [US3] Load and reuse streamlined feature memory in `playwright_god/cli.py` and `playwright_god/generator.py`
- [X] T029 [US3] Preserve compact file-index compatibility and reusable generator hints in `playwright_god/memory_map.py` and `playwright_god/feature_map.py`

**Checkpoint**: Saved memory maps remain compact, reusable, and consistent with
the feature model produced during indexing.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finish docs, validation, performance checks, and final UX
consistency work across all stories.

- [X] T030 [P] Update user-facing docs and examples for Python Playwright output in `README.md` and `tests/README.md`
- [X] T031 [P] Capture coverage verification steps for changed modules in `specs/001-repo-memory-inference/quickstart.md`
- [X] T032 [P] Validate local performance and saved-memory reuse guidance in `specs/001-repo-memory-inference/quickstart.md` and `specs/001-repo-memory-inference/research.md`
- [X] T033 Review CLI help text, generated-output wording, and feature naming consistency in `playwright_god/cli.py`, `README.md`, and `tests/README.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can begin immediately
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on Foundational completion and benefits from User Story 1 feature summaries
- **User Story 3 (Phase 5)**: Depends on Foundational completion and on feature/test-opportunity structures from User Stories 1 and 2
- **Polish (Phase 6)**: Depends on completion of all desired user stories

### User Story Dependencies

- **User Story 1 (P1)**: First deliverable and MVP; no dependency on later stories
- **User Story 2 (P2)**: Builds on the feature model from User Story 1
- **User Story 3 (P3)**: Reuses outputs introduced by User Stories 1 and 2

### Within Each User Story

- Tests MUST be written and fail before implementation
- Shared model/schema changes land before CLI wiring
- CLI behavior lands before docs and polish
- Each story should be independently testable before moving on

### Parallel Opportunities

- `T002` and `T003` can run in parallel after `T001`
- `T005`, `T007`, and `T009` can run in parallel with their paired implementation tasks once scaffolding exists
- Within US1, `T010`, `T011`, and `T012` can run in parallel
- Within US2, `T017`, `T018`, and `T019` can run in parallel
- Within US3, `T024`, `T025`, and `T026` can run in parallel
- `T030`, `T031`, and `T032` can run in parallel during the polish phase

---

## Parallel Example: User Story 1

```bash
Task: "Add CLI coverage for feature-oriented repository analysis in tests/unit/test_cli.py"
Task: "Add integration coverage for repository feature grouping in tests/integration/test_pipeline.py and tests/integration/test_feature_memory_pipeline.py"
Task: "Extend self-analysis regression coverage for feature summaries in tests/integration/test_self.py"
```

## Parallel Example: User Story 2

```bash
Task: "Add unit coverage for evidence-backed Python Playwright generation in tests/unit/test_generator.py"
Task: "Add CLI coverage for feature-aware generate and plan behavior in tests/unit/test_cli.py"
Task: "Extend integration coverage for inferred test opportunities in tests/integration/test_pipeline.py and tests/integration/test_self.py"
```

## Parallel Example: User Story 3

```bash
Task: "Add unit coverage for persisted feature-memory snapshots in tests/unit/test_memory_map.py"
Task: "Add CLI persistence and reload coverage in tests/unit/test_cli.py"
Task: "Extend integration coverage for memory-map reuse in tests/integration/test_feature_memory_pipeline.py and tests/integration/test_self.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate repository feature understanding on the sample repo and self-repo flow
5. Pause for review before adding inference and persistence layers

### Incremental Delivery

1. Deliver repository understanding and feature summaries
2. Add evidence-backed Python Playwright inference
3. Add streamlined memory-map persistence and reuse
4. Finish docs, coverage verification, and performance validation

### Parallel Team Strategy

1. One contributor owns foundational schema and memory-map updates
2. One contributor owns generator and CLI output changes after the schema stabilizes
3. One contributor owns integration/docs/quickstart validation once story code is in place

---

## Notes

- [P] tasks are safe to parallelize only when they do not edit the same files
- User Story 1 is the recommended MVP scope
- The feature-correlation module is intentionally a new focused module instead of a broad refactor
- The most important regression risk is the shift from TypeScript generation to Python Playwright output, so generator and CLI tests should stay ahead of implementation
