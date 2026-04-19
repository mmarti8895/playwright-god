## 1. FlowGraph core

- [ ] 1.1 Create `playwright_god/flow_graph.py` with `FlowGraph`, `Route`, `View`, `Action`, `Edge`, `Evidence`
- [ ] 1.2 Implement content-addressed ID generation (route/view/action shapes)
- [ ] 1.3 Implement deterministic JSON serialization + load (round-trip tested)
- [ ] 1.4 Implement evidence cap (default 3) and ranking

## 2. Extractors

- [ ] 2.1 Create `playwright_god/extractors/__init__.py` with the orchestrator
- [ ] 2.2 `extractors/python.py`: FastAPI, Flask, Django route decorators (stdlib `ast`)
- [ ] 2.3 `extractors/js_ts.py`: React Router v6, Next.js `pages/` + `app/`, Vue Router (`tree-sitter`)
- [ ] 2.4 `extractors/html.py`: `<form>`, `<a href>`, `<button>` (`selectolax`)
- [ ] 2.5 Graceful degradation when optional extras are missing (one warning per run, install hint included)

## 3. Memory map schema 2.2

- [ ] 3.1 Add optional `flow_graph` field; bump default `schema_version` to `"2.2"`
- [ ] 3.2 Loader accepts any `2.x`; `flow_graph` defaults to `None`
- [ ] 3.3 Add `MemoryMap.with_flow_graph(graph)` and round-trip tests

## 4. Coverage integration

- [ ] 4.1 Extend `merge(frontend, backend, flow_graph=...)` with the `routes` block
- [ ] 4.2 Map per-file coverage to per-route coverage via handler evidence
- [ ] 4.3 Update `coverage report` text/JSON/HTML formats to include routes when present

## 5. Planner & generator

- [ ] 5.1 `plan` annotates feature areas with uncovered routes/actions when a graph is present
- [ ] 5.2 Add `--prioritize routes` to `plan`
- [ ] 5.3 `generate` includes a `Relevant routes & actions` subgraph block (cap M, default 5)

## 6. CLI

- [ ] 6.1 Add `playwright-god graph extract [PATH] [--output PATH] [--check]` subcommand
- [ ] 6.2 `--check` exits non-zero on drift and prints a unified ID diff
- [ ] 6.3 Add `[js-extract]` and `[html-extract]` extras to `pyproject.toml`

## 7. Tests

- [ ] 7.1 `tests/unit/test_flow_graph.py`: ID stability + serialization
- [ ] 7.2 `tests/unit/test_extractor_python.py`: FastAPI + Flask + Django snippets
- [ ] 7.3 `tests/unit/test_extractor_js.py`: React Router v6 + Next.js + Vue Router snippets
- [ ] 7.4 `tests/unit/test_extractor_html.py`: form/anchor/button snippets
- [ ] 7.5 `tests/unit/test_memory_map.py`: 2.1 → 2.2 round-trip + backward compatibility
- [ ] 7.6 `tests/unit/test_coverage.py`: routes block populated when graph supplied; absent otherwise
- [ ] 7.7 `tests/integration/test_flow_graph_pipeline.py`: extract against `tests/fixtures/sample_app/` and `saml_app/`
- [ ] 7.8 `tests/unit/test_cli.py`: `graph extract`, `--check`, `--prioritize routes`

## 8. Docs & polish

- [ ] 8.1 README "Flow graph" section with example IDs and an extract command
- [ ] 8.2 README Memory Map section: bump example to `schema_version: "2.2"` and add `flow_graph` block
- [ ] 8.3 Document the `playwright-god.toml` manual route declaration extension point
- [ ] 8.4 Verify `pytest --cov=playwright_god` ≥ 99% with the new modules
