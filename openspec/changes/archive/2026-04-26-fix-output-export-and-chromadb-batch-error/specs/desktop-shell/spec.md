## ADDED Requirements

### Requirement: OUTPUT pane export writes timestamped text snapshots
The desktop application SHALL export the current OUTPUT pane buffer to a UTF-8 text file named `output_<DATETIME>.txt` when the user triggers Export from the OUTPUT pane.

#### Scenario: Export saves visible OUTPUT buffer
- **WHEN** the OUTPUT pane contains run logs and the user clicks Export
- **THEN** the application writes a file named `output_<DATETIME>.txt` and the file content exactly matches the OUTPUT pane text at export time

#### Scenario: Export file name is deterministic and sortable
- **WHEN** the user exports output
- **THEN** the filename follows the `output_<DATETIME>.txt` pattern using a sortable timestamp format so multiple exports are chronologically ordered in the filesystem

### Requirement: OUTPUT export behavior is verified by automated tests
The desktop test suite SHALL include automated coverage that validates export naming, content integrity, and failure handling.

#### Scenario: Export test verifies naming and content parity
- **WHEN** the export command is invoked in an automated test with known pane text
- **THEN** the test asserts the generated filename pattern and exact text parity (including line breaks)

#### Scenario: Export test verifies write failure surfacing
- **WHEN** the export write operation fails (for example, insufficient permissions)
- **THEN** the test asserts the UI surfaces an explicit export failure message and does not report a false success
