## ADDED Requirements

### Requirement: Repository indexing controls
The Repository section SHALL show the active repository's indexing status and SHALL expose a dedicated "Run Index" action alongside the existing full-pipeline workflow.

#### Scenario: Repository shows missing-index state
- **WHEN** the user selects a repository that does not yet have index artifacts
- **THEN** the Repository section shows that indexing is required and enables a "Run Index" action for that repository

#### Scenario: Repository shows active indexing state
- **WHEN** an index-only run is in progress for the active repository
- **THEN** the Repository section reflects that indexing is running and the action state matches the active run controls
