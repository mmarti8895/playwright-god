## MODIFIED Requirements

### Requirement: Frontend and backend reports SHALL be mergeable into a single MergedCoverageReport

The `coverage` module SHALL provide `merge(frontend, backend) -> MergedCoverageReport` whose per-file entries union the two sources without double-counting and whose top-level totals are recomputed from the merged file set. **When a flow graph is supplied via `merge(frontend, backend, flow_graph=graph)`, the merged report SHALL additionally include a `routes` block summarizing per-route coverage (`covered_routes / total_routes` plus the list of uncovered route IDs).**

#### Scenario: Disjoint file sets are concatenated

- **WHEN** frontend covers `["app.js"]` and backend covers `["api/users.py"]`
- **THEN** the merged report has both files and `merged.total_files == 2`

#### Scenario: Overlapping files are unioned line-wise

- **WHEN** both reports include `shared.ts` and frontend covers lines `{1,2,3}` while backend covers lines `{3,4}`
- **THEN** the merged `shared.ts` entry has `covered_lines == 4` (lines 1,2,3,4) with no double-counting

#### Scenario: Routes block is populated when a flow graph is supplied

- **WHEN** `merge(frontend, backend, flow_graph=g)` is called and `g` contains routes `route:GET:/a`, `route:GET:/b`, `route:GET:/c`, and the merged file coverage indicates the handlers for `/a` and `/b` were exercised
- **THEN** the merged report's `routes.covered == 2`, `routes.total == 3`, and `routes.uncovered == ["route:GET:/c"]`

#### Scenario: Routes block is omitted when no flow graph is supplied

- **WHEN** `merge(frontend, backend)` is called without a `flow_graph`
- **THEN** the merged report has no `routes` field (or it is `None`), preserving the `coverage-aware-planning` baseline shape
