# Implementation Plan: Repository Memory Inference

**Branch**: `001-repo-memory-inference` | **Date**: 2026-04-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-repo-memory-inference/spec.md`

## Summary

Extend the existing Python CLI RAG pipeline so it can infer feature-level
relationships from repository evidence, save a streamlined feature-aware memory
map, and generate high-quality Playwright tests in Python instead of
TypeScript. The implementation will keep the current crawl, chunk, index, and
memory-map flow intact while adding a compact feature-correlation model,
evidence-backed test opportunities, Python-oriented prompt/template generation,
and aligned CLI/tests/docs.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `click`, `chromadb`, optional LLM SDKs
(`openai`, `anthropic`, `google-generativeai`, `requests`), Playwright for
Python and pytest-based test tooling
**Storage**: Local filesystem for persisted ChromaDB index and JSON memory maps
**Testing**: `pytest`, `pytest-cov`, Click `CliRunner`, existing integration
tests, and Playwright-for-Python-oriented generator/CLI tests
**Target Platform**: Local CLI on Windows, macOS, and Linux
**Project Type**: Python library + CLI tool
**Performance Goals**: Preserve interactive local workflows; representative
repository analysis plus saved memory map within 5 minutes; saved-memory reuse
should cut later planning/generation time by at least 50%
**Constraints**: Offline-friendly template mode, deterministic tests, minimal
CLI surface drift, compact memory-map output, no real network calls in tests,
bounded timeouts for external providers
**Scale/Scope**: Single repository analysis for small-to-medium codebases with
dozens to low thousands of source files and mixed source/config/test artifacts

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Code Quality**: PASS. Scope stays concentrated in
  `playwright_god/generator.py`, `playwright_god/memory_map.py`,
  `playwright_god/cli.py`, and one new feature-correlation module plus focused
  tests and docs. The plan avoids replacing the working crawl/index pipeline.
- **Testing**: PASS. Add or update deterministic unit coverage for feature
  correlation, memory-map serialization, Python template generation, and CLI
  behavior. Extend integration coverage for self-index/generate flows and
  memory-map reuse. Run coverage on changed modules to preserve the repo rule of
  100% unit coverage for changed code.
- **User Experience Consistency**: PASS. `index`, `generate`, and `plan` remain
  the core workflow. User-visible changes are limited to Python-focused
  generation output, richer feature-aware summaries, and aligned docs/help text.
- **Performance**: PASS. Feature inference is layered on top of existing file
  and chunk data, saved memory maps remain compact, and reuse is explicitly part
  of the verification plan.
- **Documentation Sync**: PASS. Update `README.md`, `tests/README.md`, and the
  spec artifacts to reflect Python Playwright output and feature-aware memory
  behavior.

### Post-Design Constitution Check

- **Code Quality**: PASS. Research, data model, quickstart, and CLI contract all
  keep the design centered on minimal extensions to the current architecture.
- **Testing**: PASS. The planned artifacts identify the unit, integration, and
  coverage work needed before implementation is considered done.
- **User Experience Consistency**: PASS. The CLI contract requires consistent
  feature naming and reviewable confidence signaling across outputs.
- **Performance**: PASS. Saved-memory reuse and compact JSON structure remain
  explicit design constraints.
- **Documentation Sync**: PASS. The generated planning artifacts identify the
  files and workflows that must be updated during implementation.

## Project Structure

### Documentation (this feature)

```text
specs/001-repo-memory-inference/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- cli-contract.md
`-- tasks.md
```

### Source Code (repository root)

```text
playwright_god/
|-- cli.py
|-- crawler.py
|-- chunker.py
|-- embedder.py
|-- indexer.py
|-- memory_map.py
|-- generator.py
|-- auth_templates.py
`-- <new feature-correlation module>

tests/
|-- unit/
|   |-- test_cli.py
|   |-- test_generator.py
|   |-- test_memory_map.py
|   `-- <new correlation-focused unit tests>
|-- integration/
|   |-- test_pipeline.py
|   `-- test_self.py
`-- e2e/
    `-- existing sample-app browser coverage
```

**Structure Decision**: Keep the existing single-package Python CLI structure.
Add one focused module for feature correlation rather than introducing a new
service or package boundary.

## Complexity Tracking

No constitution violations or justified complexity exceptions were identified in
this planning pass.
