## MODIFIED Requirements

### Requirement: A FlowGraph SHALL model routes, views, and actions with stable IDs

The `playwright_god.flow_graph.FlowGraph` SHALL contain three node types — `Route`, `View`, and `Action` — and SHALL assign each node a stable, content-addressed ID derived from method/path (routes), file+symbol (views), or file+line+role (actions). Re-extracting the graph from unchanged source SHALL produce byte-identical IDs. **Each node SHALL additionally carry an optional `covering_specs: list[str]` field listing the spec paths that exercise it, populated by `SpecIndex` when one is supplied.**

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

#### Scenario: covering_specs is populated when a SpecIndex is supplied

- **WHEN** `FlowGraph.attach_spec_index(spec_index)` is called and a spec at `tests/login.spec.ts` maps to `route:GET:/login`
- **THEN** the node for `route:GET:/login` has `covering_specs == ["tests/login.spec.ts"]`

#### Scenario: covering_specs defaults to empty when no SpecIndex is supplied

- **WHEN** a flow graph is constructed without attaching a spec index
- **THEN** every node's `covering_specs` is `[]`
