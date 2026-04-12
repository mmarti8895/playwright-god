# AGENTS.md

Repository-specific working notes for `playwright-god`.

## Stack

- Python 3.11+
- Click CLI
- ChromaDB-backed local indexing
- pytest for unit and integration tests
- Playwright for Python for generated and e2e test flows

## Commands

Install runtime dependencies:

```bash
pip install -e .
```

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

Run the focused unit suite for the feature-memory workflow:

```bash
pytest tests/unit/test_feature_map.py tests/unit/test_memory_map.py tests/unit/test_generator.py tests/unit/test_cli.py -q
```

Run the focused integration suite:

```bash
pytest tests/integration/test_pipeline.py tests/integration/test_feature_memory_pipeline.py tests/integration/test_self.py -q
pytest tests/integration/test_auth_pipeline.py tests/integration/test_logging_pipeline.py -q
```

Run coverage:

```bash
pytest --cov=playwright_god --cov-report=term-missing
```

## Conventions

- Generated Playwright code should target Python sync API patterns.
- Keep offline template behavior deterministic so the test suite runs without network access.
- Prefer extending `feature_map.py`, `memory_map.py`, `generator.py`, and `cli.py` over introducing new package layers.
- Saved memory maps should stay compact and should not store full chunk text.

## Gaps

- No repo-managed formatter or linter command is configured in `pyproject.toml` yet.
- If those tools are added later, update this file with the exact commands instead of placeholders.
