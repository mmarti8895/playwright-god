## 1. FlowGraph core

- [x] 1.1 Create `playwright_god/flow_graph.py` with `FlowGraph`, `Route`, `View`, `Action`, `Edge`, `Evidence`
- [x] 1.2 Implement content-addressed ID generation (route/view/action shapes)
- [x] 1.3 Implement deterministic JSON serialization + load (round-trip tested)
- [x] 1.4 Implement evidence cap (default 3) and ranking

## 2. Extractors

- [x] 2.1 Create `playwright_god/extractors/__init__.py` with the orchestrator
- [x] 2.2 `extractors/python.py`: FastAPI, Flask, Django route decorators (stdlib `ast`)
- [x] 2.3 `extractors/js_ts.py`: React Router v6, Next.js `pages/` + `app/`, Vue Router (`tree-sitter`)
- [x] 2.4 `extractors/html.py`: `<form>`, `<a href>`, `<button>` (`selectolax`)
- [x] 2.5 Graceful degradation when optional extras are missing (one warning per run, install hint included)

## 3. Memory map schema 2.2

- [x] 3.1 Add optional `flow_graph` field; bump default `schema_version` to `"2.2"`
- [x] 3.2 Loader accepts any `2.x`; `flow_graph` defaults to `None`
- [x] 3.3 Add `MemoryMap.with_flow_graph(graph)` and round-trip tests

## 4. Coverage integration

- [x] 4.1 Extend `merge(frontend, backend, flow_graph=...)` with the `routes` block
- [x] 4.2 Map per-file coverage to per-route coverage via handler evidence
- [x] 4.3 Update `coverage report` text/JSON/HTML formats to include routes when present

## 5. Planner & generator

- [x] 5.1 `plan` annotates feature areas with uncovered routes/actions when a graph is present
- [x] 5.2 Add `--prioritize routes` to `plan`
- [x] 5.3 `generate` includes a `Relevant routes & actions` subgraph block (cap M, default 5)

## 6. CLI

- [x] 6.1 Add `playwright-god graph extract [PATH] [--output PATH] [--check]` subcommand
- [x] 6.2 `--check` exits non-zero on drift and prints a unified ID diff
- [x] 6.3 Add `[js-extract]` and `[html-extract]` extras to `pyproject.toml`

## 7. Tests

- [x] 7.1 `tests/unit/test_flow_graph.py`: ID stability + serialization
- [x] 7.2 `tests/unit/test_extractor_python.py`: FastAPI + Flask + Django snippets
- [x] 7.3 `tests/unit/test_extractor_js.py`: React Router v6 + Next.js + Vue Router snippets
- [x] 7.4 `tests/unit/test_extractor_html.py`: form/anchor/button snippets
- [x] 7.5 `tests/unit/test_memory_map.py`: 2.1 → 2.2 round-trip + backward compatibility
- [x] 7.6 `tests/unit/test_coverage.py`: routes block populated when graph supplied; absent otherwise
- [x] 7.7 `tests/integration/test_flow_graph_pipeline.py`: extract against `tests/fixtures/sample_app/` and `saml_app/`
- [x] 7.8 `tests/unit/test_cli.py`: `graph extract`, `--check`, `--prioritize routes`

## 8. Docs & polish

- [x] 8.1 README "Flow graph" section with example IDs and an extract command
- [x] 8.2 README Memory Map section: bump example to `schema_version: "2.2"` and add `flow_graph` block
- [x] 8.3 Document the `playwright-god.toml` manual route declaration extension point
- [x] 8.4 Verify `pytest --cov=playwright_god` ≥ 99% with the new modules
