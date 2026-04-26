# Desktop Shell

## Purpose

Capability added by the `tauri-desktop-ui` change (archived). See the change for the original proposal and design notes.
## Requirements
### Requirement: Native macOS-style window chrome
The desktop application SHALL present a window with a hidden-inset titlebar (traffic-light controls overlaying the content), a frosted/vibrancy sidebar background on macOS, and a non-frosted but visually consistent fallback on Linux.

#### Scenario: Window opens with native chrome on macOS
- **WHEN** the user launches the desktop app on macOS
- **THEN** the window opens with `titleBarStyle: "Overlay"` (or platform equivalent), the traffic-light controls are inset over the sidebar, and the sidebar background uses NSVisualEffectView vibrancy

#### Scenario: Window opens with consistent chrome on Linux
- **WHEN** the user launches the desktop app on Linux
- **THEN** the window opens with a borderless or minimal-decoration frame and the sidebar uses an opaque muted background that visually matches the macOS frosted look

### Requirement: Sidebar + main + output layout
The desktop application SHALL render a three-region layout: a fixed-width left sidebar listing navigation sections, a central main panel that swaps content based on the active sidebar section, and a collapsible bottom output pane that streams CLI run output.

#### Scenario: User switches sections
- **WHEN** the user clicks a section entry in the sidebar
- **THEN** the main panel swaps to that section's view within 100 ms and the active entry is visually highlighted

#### Scenario: User toggles the output pane
- **WHEN** the user clicks the output-pane toggle in the status bar
- **THEN** the output pane collapses or expands and its current state is persisted across app restarts

### Requirement: Sidebar navigation entries
The sidebar SHALL expose, in order: Repository, Memory Map, Flow Graph, Coverage & Gaps, Generation, Codegen Stream, Dry Run / Inspect, Audit Log, and Settings.

#### Scenario: All sections are reachable
- **WHEN** the user opens the app for the first time
- **THEN** all nine sidebar entries are visible and each navigates to a distinct main-panel view when clicked

### Requirement: Visual design tokens
The desktop application SHALL use a single set of design tokens (color palette, spacing scale, radius scale, shadow scale, typography scale) defined in one Tailwind/CSS configuration file and applied consistently to every panel, button, input, table, and graph view.

#### Scenario: Tokens are centralized
- **WHEN** a developer inspects the styling source
- **THEN** every color, spacing, radius, and shadow used in components references the central token file rather than inlined literal values

### Requirement: Recent repositories persistence
The desktop application SHALL persist the list of recently opened repositories (most-recent first, capped at 10 entries) to the platform's app-config directory and surface them in the Repository section.

#### Scenario: Repository is remembered across restarts
- **WHEN** the user opens a repository, closes the app, and reopens it
- **THEN** that repository appears at the top of the Recent Repositories list

#### Scenario: Recent list is capped
- **WHEN** the user has opened more than 10 distinct repositories
- **THEN** only the 10 most-recently-opened repositories are retained

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

