## Why

`feature_map.py` infers test opportunities from text chunks, filenames, and keyword evidence — useful, but shallow. It cannot enumerate "every route in the app," "every form on this page," or "every event handler reachable from the navbar." That means the planner can ask the LLM to test things that don't exist and miss things that do. To converge on real coverage, the tool needs a deterministic, structural map of the app's testable surface that complements (not replaces) the heuristic feature map.

## What Changes

- Add a `FlowGraph` data structure with three node types: `Route`, `View`, `Action` (forms, buttons, event handlers, API call sites).
- Add per-language extractors that populate the graph from source:
  - **JS/TS frontend** via Babel/SWC AST parsing (router configs for React Router, Next.js, Vue Router; JSX/TSX form & button discovery).
  - **Python backend** via `ast` walking (FastAPI/Flask/Django route decorators; form definitions where applicable).
  - **HTML templates** via a lightweight parser for `<form>`, `<a href>`, `<button>`.
- Persist the graph alongside the memory map (new `flow_graph.json` artifact, schema bumped to `2.2`).
- Surface the graph in:
  - `plan` — group scenarios by route/action with deterministic IDs (`route:/login → action:submit-login-form`).
  - `generate` — include the relevant `Route`/`Action` subgraph for the requested description as RAG context (so the LLM is told *what* to call, not asked to guess).
  - `coverage report` — show per-route coverage (covered routes / total routes) in addition to per-file.
- Add a `playwright-god graph extract` subcommand that runs the extractors standalone and prints/saves the graph.

## Capabilities

### New Capabilities
- `flow-graph`: Deterministically extracting routes, views, and actions from a repository into a typed graph that downstream features (planner, generator, coverage) can query.

### Modified Capabilities
- `coverage-driven-planning`: planner consumes flow-graph node IDs (in addition to feature areas) so per-route coverage becomes a first-class prioritization signal.
- `coverage-collection`: merged report gains an optional `routes` block summarizing per-route coverage when a flow graph is present.

## Impact

- **Code**: new `playwright_god/flow_graph.py`, new `playwright_god/extractors/` package (`js_ts.py`, `python.py`, `html.py`); updates to `memory_map.py` (schema 2.2 + optional `flow_graph` field), `cli.py` (`graph extract` subcommand + new flags), `generator.py` (subgraph injection).
- **Dependencies**: new optional extras — `[js-extract]` pulling `tree-sitter` + `tree-sitter-typescript` (deterministic, no Node required), `[html-extract]` pulling `selectolax`. Python AST is stdlib.
- **Tests**: new `tests/unit/test_flow_graph.py`, `tests/unit/test_extractor_js.py`, `tests/unit/test_extractor_python.py`, `tests/unit/test_extractor_html.py`; integration test against `tests/fixtures/sample_app/` and `tests/fixtures/saml_app/`.
- **Docs**: README "Flow graph" section; example `flow_graph.json`; schema doc bump to `2.2`.
- **Downstream**: `spec-aware-update` consumes graph-node IDs to know which existing spec covers which route/action.
