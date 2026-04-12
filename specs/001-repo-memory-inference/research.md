# Research: Repository Memory Inference

## Decision 1: Keep the existing crawl -> chunk -> index pipeline and add a feature-correlation layer

- **Decision**: Extend the current `RepositoryCrawler`, `FileChunker`,
  `RepositoryIndexer`, and memory-map workflow with a new feature-correlation
  pass that groups repository artifacts into feature areas and records the
  evidence for those groupings.
- **Rationale**: The current CLI already has a reliable local indexing pipeline,
  self-tests, and persisted memory-map support. Building the new capability as a
  layer on top of that flow keeps the change set focused and reduces the risk of
  regressions in indexing and retrieval behavior.
- **Alternatives considered**:
  - Replace the current RAG pipeline with a feature-only graph model.
    Rejected because it would discard working indexing and retrieval behavior.
  - Infer features only at generation time from raw search results.
    Rejected because it would make memory-map reuse weaker and less consistent.

## Decision 2: Standardize generated test output on Python Playwright tests

- **Decision**: Treat Python as the primary generated test language and align
  offline templates, prompts, CLI documentation, and tests around Playwright for
  Python.
- **Rationale**: The user requirement explicitly calls for Python Playwright
  tests, and the repository already uses Python for the CLI, data pipeline, and
  test harness. Aligning generation output with the host language reduces mental
  switching and fits the repo's existing pytest-based workflow.
- **Alternatives considered**:
  - Keep TypeScript as the generated output language.
    Rejected because it conflicts with the requested product direction.
  - Generate both languages by default.
    Rejected because it would complicate prompts, validation, and docs before
    the feature-correlation work is proven.
  - Use Playwright's async Python API as the default template style.
    Rejected because sync-style pytest examples are simpler to read and easier
    to validate in deterministic offline templates.

## Decision 3: Preserve backward-compatible memory-map structure while adding streamlined feature metadata

- **Decision**: Keep the existing file-and-line inventory as the foundation of
  the memory map and extend it with compact feature areas, correlations,
  evidence references, and inferred test opportunities.
- **Rationale**: Existing `plan` and `generate --memory-map` flows already
  depend on file inventory. Extending the schema rather than replacing it keeps
  current behavior available while adding the higher-level feature model needed
  for richer inference.
- **Alternatives considered**:
  - Replace the current JSON memory map with a completely new feature-only
    format.
    Rejected because it would break current consumers and lose line-range
    context.
  - Save full chunk text in the memory map.
    Rejected because it would bloat the artifact and undermine the goal of a
    streamlined reusable summary.

## Decision 4: Use evidence-backed heuristics for feature inference

- **Decision**: Infer feature areas and test opportunities from combined
  repository signals such as routes, forms, selectors, auth configuration,
  existing tests, file naming, and shared references rather than relying on
  semantic similarity alone.
- **Rationale**: The spec requires the system to explain why a recommendation
  exists and to handle incomplete or conflicting evidence. A mixed-signal
  approach provides traceable rationale and lets the system label uncertainty.
- **Alternatives considered**:
  - Use vector search results alone to infer features and test recommendations.
    Rejected because it produces weaker evidence trails and lower confidence for
    structural relationships.
  - Require manual feature annotations in the repository.
    Rejected because it would reduce usefulness for first-run analysis.

## Decision 5: Surface uncertainty explicitly instead of hiding low-confidence results

- **Decision**: Store confidence and evidence metadata for inferred feature
  relationships and test opportunities, and require user-facing outputs to
  distinguish confirmed evidence from inferred conclusions.
- **Rationale**: The feature spec and constitution both require actionable,
  reviewable outputs that avoid overclaiming. Confidence-aware results support
  trustworthy planning and generation.
- **Alternatives considered**:
  - Emit only high-confidence results and drop ambiguous findings entirely.
    Rejected because users would lose partial but still useful repository
    understanding.
  - Emit all findings without confidence labels.
    Rejected because reviewers would not know what to trust.

## Validation Note

- Local verification should prefer saved-memory reuse over rebuilding the
  repository model for repeated `generate` and `plan` runs.
- Coverage verification should stay focused on the changed Python modules:
  `feature_map.py`, `memory_map.py`, `generator.py`, `cli.py`, and
  `auth_templates.py`.
