# Quickstart: Repository Memory Inference

## Goal

Validate the new repository-memory workflow end to end:

1. Index a repository
2. Build a streamlined feature-aware memory map
3. Infer Python Playwright test opportunities from that memory
4. Reuse the saved memory map for later planning or generation

## Prerequisites

- Python 3.11+
- Project dependencies installed
- Local repository available for analysis

## 1. Run targeted tests during implementation

```bash
pytest tests/unit/test_auth_templates.py tests/unit/test_feature_map.py tests/unit/test_memory_map.py tests/unit/test_generator.py tests/unit/test_cli.py -q
pytest tests/integration/test_pipeline.py tests/integration/test_feature_memory_pipeline.py tests/integration/test_self.py -q
pytest tests/integration/test_auth_pipeline.py tests/integration/test_logging_pipeline.py -q
pytest tests/unit/test_auth_templates.py tests/unit/test_feature_map.py tests/unit/test_memory_map.py tests/unit/test_generator.py tests/unit/test_cli.py --cov=playwright_god.feature_map --cov=playwright_god.memory_map --cov=playwright_god.generator --cov=playwright_god.cli --cov=playwright_god.auth_templates --cov-report=term-missing -q
```

## 2. Index a repository and save the memory map

```bash
playwright-god index . -d .idx --memory-map .idx/memory_map.json
```

Expected outcome:

- Repository files are crawled and chunked
- Feature areas and correlations are summarized in the CLI output
- The index is persisted locally
- A streamlined memory-map artifact is written to `.idx/memory_map.json`

## 3. Generate Python Playwright tests from repository understanding

```bash
playwright-god generate "user login flow" -d .idx --memory-map .idx/memory_map.json -o tests/generated_login.spec.py
```

Expected outcome:

- Generated output is Python Playwright test code
- The recommendation reflects repository feature evidence rather than only raw
  file matches
- Low-confidence areas are surfaced clearly for review

## 4. Produce a feature-oriented planning artifact from the saved memory map

```bash
playwright-god plan --memory-map .idx/memory_map.json -o inferred_test_plan.md
```

Expected outcome:

- The plan groups scenarios by inferred feature area
- Suggested coverage aligns with saved repository correlations

## 5. Reuse saved memory instead of rebuilding from scratch

Repeat `generate` or `plan` using the saved memory map without re-running
`index` when the repository has not materially changed.

Expected outcome:

- Follow-up planning and generation runs complete faster than rebuilding the
  repository memory from scratch
- Feature naming and evidence references remain consistent across runs
- Reloaded memory maps still contain feature areas, correlations, and suggested
  test opportunities
