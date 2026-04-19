## ADDED Requirements

### Requirement: A FlowGraph SHALL model routes, views, and actions with stable IDs

The `playwright_god.flow_graph.FlowGraph` SHALL contain three node types — `Route`, `View`, and `Action` — and SHALL assign each node a stable, content-addressed ID derived from method/path (routes), file+symbol (views), or file+line+role (actions). Re-extracting the graph from unchanged source SHALL produce byte-identical IDs.

#### Scenario: Route IDs include method and path

- **WHEN** a FastAPI route `@app.get("/users/{id}")` is extracted
- **THEN** the resulting node has `id == "route:GET:/users/{id}"`

#### Scenario: View IDs include file and symbol

- **WHEN** a React component exported as `default` from `src/pages/Login.tsx` is extracted
- **THEN** the resulting node has `id == "view:src/pages/Login.tsx#default"`

#### Scenario: Action IDs include file, line, and role

- **WHEN** a `<button data-action="submit-login">` at `src/pages/Login.tsx:42` is extracted
- **THEN** the resulting node has `id == "action:src/pages/Login.tsx:42#submit-login"`

#### Scenario: Re-extraction of unchanged source produces identical IDs

- **WHEN** the same source tree is extracted twice
- **THEN** every node ID in the second graph appears in the first and vice versa

### Requirement: Each node SHALL carry source evidence

Every node SHALL include an `evidence: list[Evidence]` field where each `Evidence` references a source file and a line range that justifies the node's existence. The evidence list SHALL be capped at 3 entries per node by default.

#### Scenario: Evidence references the originating source

- **WHEN** a route is extracted from `app/api/users.py:17`
- **THEN** the node's `evidence[0]` has `file == "app/api/users.py"` and `line_range == (17, 17)` (or the decorator span, whichever is wider)

#### Scenario: Evidence is capped

- **WHEN** an action is referenced 10 times across the codebase
- **THEN** the node's `evidence` list has length 3 (highest-relevance first)

### Requirement: Per-language extractors SHALL populate the graph deterministically

The `playwright_god.extractors` package SHALL provide `js_ts`, `python`, and `html` extractors, each producing a partial `FlowGraph` from a source tree. The orchestrator SHALL merge partials into a single graph.

#### Scenario: FastAPI routes are extracted by the python extractor

- **WHEN** the python extractor scans a file containing `@app.get("/healthz")` and `@router.post("/items")`
- **THEN** both routes appear as `Route` nodes in the partial graph with the correct method and path

#### Scenario: React Router v6 routes are extracted by the js_ts extractor

- **WHEN** the js_ts extractor scans a file containing `<Route path="/login" element={<Login />} />`
- **THEN** a `Route` node `route:GET:/login` and a `View` node referencing `Login` are produced, connected by a `Route -> View` edge

#### Scenario: Next.js file-system routing is extracted

- **WHEN** the js_ts extractor scans a `pages/` or `app/` directory
- **THEN** each conventional route file produces the corresponding `Route` and `View` nodes

#### Scenario: HTML form actions are extracted

- **WHEN** the html extractor scans a template containing `<form action="/login" method="post">`
- **THEN** an `Action` node referencing the form is produced with an `Action -> Endpoint(POST /login)` edge

### Requirement: Missing optional extras SHALL degrade gracefully

When the optional extras for an extractor are not installed, the orchestrator SHALL skip that extractor with a single structured warning per run rather than failing. The resulting graph SHALL be valid (possibly empty) and the warning SHALL include the install command.

#### Scenario: js_ts extras missing

- **WHEN** `tree-sitter` is not importable and a JS/TS file is encountered
- **THEN** a warning containing `pip install -e ".[js-extract]"` is logged exactly once per run and JS/TS files are skipped

#### Scenario: html extras missing

- **WHEN** `selectolax` is not importable and an HTML file is encountered
- **THEN** a warning containing `pip install -e ".[html-extract]"` is logged exactly once per run and HTML files are skipped

### Requirement: MemoryMap SHALL gain an optional flow_graph field at schema_version 2.2

`MemoryMap` SHALL accept an optional `flow_graph` field carrying a serialized `FlowGraph`, SHALL bump `schema_version` to `"2.2"` when written with a graph, and the loader SHALL accept any `2.x` schema for backward compatibility.

#### Scenario: New memory map is written with a flow graph

- **WHEN** `MemoryMap.with_flow_graph(graph).save(path)` is called
- **THEN** the on-disk JSON has `schema_version == "2.2"` and a `flow_graph` object whose `nodes` and `edges` round-trip to the in-memory graph

#### Scenario: Older 2.1 memory map still loads

- **WHEN** a memory map written by a previous version with `schema_version == "2.1"` is loaded
- **THEN** loading succeeds and `memory_map.flow_graph is None`

### Requirement: A `graph extract` CLI subcommand SHALL run extractors standalone

The CLI SHALL provide `playwright-god graph extract [PATH] [--output PATH] [--check]` that runs the configured extractors and writes a `flow_graph.json` artifact (default `<persist-dir>/flow_graph.json`).

#### Scenario: Default invocation extracts and saves the graph

- **WHEN** `playwright-god graph extract .` is invoked
- **THEN** `flow_graph.json` is written under the persist dir and a one-line summary (`<R> routes, <V> views, <A> actions`) is printed

#### Scenario: --check exits non-zero on drift

- **WHEN** `playwright-god graph extract --check` is invoked and the freshly extracted graph differs from the persisted one
- **THEN** a unified diff of the IDs is printed and the CLI exits non-zero
