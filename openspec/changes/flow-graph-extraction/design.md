## Context

The current memory map is built from chunked text and keyword heuristics. That's enough to suggest themes (`auth`, `nav`) but not enough to enumerate the actual testable surface of an app: routes, mounted views, and the actions a user can take inside each view. Without that structure, the tool has no ground-truth list to drive toward 100% coverage and no way to deduplicate "tests we've already written for this exact action."

A real flow graph also unlocks better coverage attribution: a per-file line percentage is fine, but "27 of 31 routes are covered, here are the 4 missing" is the metric users actually want.

## Goals / Non-Goals

**Goals:**
- Deterministic extraction (same input → same graph) that does not require running the target app.
- Coverage of the dominant frameworks: React (incl. React Router + Next.js), Vue (Vue Router), FastAPI, Flask, Django, and plain HTML.
- A typed `FlowGraph` with stable, content-addressed node IDs so they can be referenced from specs, prompts, and audit logs.
- Backward-compatible memory-map evolution (`schema_version` 2.2, `flow_graph` optional).
- Clear failure modes: extractors degrade gracefully when a framework isn't recognized.

**Non-Goals:**
- Dynamic flow discovery via execution. We do static extraction only.
- Arbitrary framework support out of the gate. We ship the listed frameworks; others go through a documented extension point.
- Modeling app state machines. v1 captures structure (nodes + edges), not state.
- Selector mining (e.g., inferring `data-testid` discipline). Out of scope.

## Decisions

1. **`tree-sitter` for JS/TS, stdlib `ast` for Python, `selectolax` for HTML.** Tree-sitter gives us deterministic, fast, language-accurate parsing without spawning Node. Stdlib `ast` is sufficient for Python framework patterns. Selectolax is a tiny, fast HTML parser. All three are pure-Python-friendly install paths.
2. **Three node types only.** `Route` (URL pattern + handler reference), `View` (rendered component or template), `Action` (form submit, button click, fetch/axios call). Edges: `Route -> View`, `View -> Action`, `Action -> Route` (navigation), `Action -> Endpoint` (API call to a backend route). This is the minimum vocabulary that lets the planner say "test action X under route Y."
3. **Content-addressed node IDs.** `route:GET:/api/users` (method + path), `view:src/pages/Login.tsx#default` (file + symbol), `action:src/pages/Login.tsx:42#submit` (file + line + role). Stable across runs as long as the underlying source is stable; usable as audit-log keys.
4. **Per-framework adapters, one extractor per language.** `extractors/js_ts.py` knows React Router config, Next.js `pages/` and `app/` directories, and Vue Router; `extractors/python.py` knows FastAPI/Flask/Django decorator shapes. Each adapter is a function returning a partial graph; the orchestrator merges them.
5. **Extractors return both nodes and *evidence***. Every node carries `evidence: list[Evidence(file, line_range)]` so prompts can quote the relevant source verbatim and audits can prove where a node came from.
6. **Optional dependency model.** Extractors are optional; missing the relevant extra produces a structured warning, not a crash. The base install builds an empty graph (with a clear "install extras to enable" message).
7. **Schema bump is additive again.** `2.1 → 2.2`. Loader accepts any `2.x`; `flow_graph` field defaults to `None`. Same compatibility story as coverage.
8. **Generator subgraph selection is bounded.** The generator picks at most M routes (default 5) and their immediate views/actions, ranked by relevance to the user description (vector search over node `title` + `evidence`). Prevents prompt blowup.
9. **Graph extraction is independently runnable.** `playwright-god graph extract` writes `flow_graph.json` and prints a summary. Useful for debugging and for `spec-aware-update`.

## Risks / Trade-offs

- **Framework drift.** React Router v6 vs v5 vs Next.js `app/` router all have different shapes; each shape needs an adapter. Mitigated by a small registry pattern in `extractors/js_ts.py` with explicit version detection and graceful unknown-shape warnings.
- **Custom routing patterns.** Apps that build their own router (e.g. dynamic registration) will produce undercounts. Documented; partially mitigated by including a `Route(source="manual")` API for users to declare missing routes in `playwright-god.toml`.
- **AST extraction is brittle to stylistic edge cases.** Mitigated by extractor unit tests using real-world snippets from the existing `tests/fixtures/*_app/` directories.
- **Extra dependencies.** `tree-sitter` is a binary wheel; some platforms lack prebuilt wheels. Mitigated by making JS/TS extraction strictly opt-in (`pip install -e ".[js-extract]"`) and degrading gracefully when absent.
- **Evidence inflation.** Every node carries `evidence`, which grows the JSON. Mitigated by capping evidence to the first N (default 3) occurrences per node.
- **Graph staleness.** A flow graph is a snapshot; refactors invalidate it. Mitigated by `playwright-god graph extract --check` which compares against the persisted graph and exits non-zero on drift, suitable for CI.
