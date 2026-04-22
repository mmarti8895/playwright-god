## ADDED Requirements

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
