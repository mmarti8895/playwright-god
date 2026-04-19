# Test Suite

This directory contains deterministic validation for the `playwright-god` CLI, repository-analysis pipeline, and sample Playwright flows.

## Test Layers

`tests/unit/`
- fast module-level coverage for crawler, chunker, generator, CLI, memory map, and feature inference

`tests/integration/`
- end-to-end repository analysis and generation flows without real LLM network calls

`tests/e2e/`
- browser-driven Playwright-for-Python tests against the fixture app in [tests/fixtures/sample_app](/c:/Users/mmart/projects/playwright-god/tests/fixtures/sample_app)

## Current Focus

The suite now validates:

- TypeScript Playwright output from the offline template generator
- feature-aware repository summaries and correlations
- saved memory-map reuse
- auth and logging prompt helpers
- self-analysis of the `playwright-god` repository

## Helpful Commands

Run core unit coverage for changed behavior:

```bash
pytest tests/unit/test_feature_map.py tests/unit/test_memory_map.py tests/unit/test_generator.py tests/unit/test_cli.py -q
```

Run integration coverage for repository understanding and generation:

```bash
pytest tests/integration/test_pipeline.py tests/integration/test_feature_memory_pipeline.py tests/integration/test_self.py -q
pytest tests/integration/test_auth_pipeline.py tests/integration/test_logging_pipeline.py -q
```

Run browser tests against the fixture app:

```bash
pytest tests/e2e -q
```

Run coverage:

```bash
pytest --cov=playwright_god --cov-report=term-missing
```

## Fixture App

The sample application under [tests/fixtures/sample_app](/c:/Users/mmart/projects/playwright-god/tests/fixtures/sample_app) intentionally includes:

- login signals
- navigation links
- todo interactions
- profile and logout elements

Those signals let the repository-analysis layer infer meaningful feature groupings and suggest evidence-backed test opportunities.
