## ADDED Requirements

### Requirement: The plan and generate flows SHALL consume coverage to drive prioritization

When a coverage report is present in the active memory map, the `plan` command SHALL order output by gap size and the `generate` command SHALL inject uncovered excerpts into the prompt context, so that the user's next test naturally targets the largest remaining gap.

#### Scenario: A second `generate` after a covered run targets a different gap

- **GIVEN** a memory map whose first generated spec covered the entire `auth` feature
- **WHEN** the user runs `generate "next priority area"` against the updated memory map
- **THEN** the prompt no longer ranks `auth` first and the generated spec references at least one file from a still-uncovered feature

#### Scenario: Plan re-orders after coverage updates

- **GIVEN** a memory map updated with a new merged coverage report
- **WHEN** `plan` is re-run
- **THEN** feature areas appear in descending uncovered-line order and the `## Coverage Delta` section reflects the latest report's `generated_at` timestamp
