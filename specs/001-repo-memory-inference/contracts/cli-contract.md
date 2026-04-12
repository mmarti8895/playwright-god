# CLI Contract: Repository Memory Inference

## Purpose

Define the public command behavior for repository analysis, streamlined memory
maps, and Python Playwright test generation.

## `playwright-god index`

- **Intent**: Analyze a repository and persist both searchable memory and a
  streamlined reusable memory map.
- **Inputs**:
  - repository path
  - persisted index directory
  - collection name
  - optional extra files
  - optional memory-map output path
- **Behavior contract**:
  - Must report crawl, chunk, and persistence progress in a consistent CLI flow
  - Must save a memory map that retains file inventory and adds compact
    feature-correlation data
  - Must remain usable in offline local workflows
- **Output contract**:
  - Human-readable summary on stdout
  - Persisted vector index on disk
  - JSON memory map on disk when requested

## `playwright-god generate`

- **Intent**: Produce Python Playwright test code from repository understanding.
- **Inputs**:
  - free-text test description
  - persisted index or saved memory map
  - optional output file
  - optional auth and environment context
- **Behavior contract**:
  - Must retrieve repository evidence relevant to the request
  - Must use feature correlations and saved memory when available
  - Must emit Python Playwright tests that read as user journeys and include
    evidence-backed assertions
  - Must distinguish low-confidence inferences from strong recommendations
- **Output contract**:
  - Python Playwright test code on stdout or in the requested file
  - Consistent user-facing status messages on stderr

## `playwright-god plan`

- **Intent**: Produce a feature-oriented Playwright coverage plan from saved
  repository understanding.
- **Inputs**:
  - saved memory map or persisted index
  - optional focus hint
  - optional output file
- **Behavior contract**:
  - Must group proposed coverage by inferred feature area
  - Must preserve feature naming consistency with `index` and `generate`
  - Must remain useful when only partial repository evidence is available
- **Output contract**:
  - Markdown planning artifact on stdout or in the requested file

## Memory Map JSON Contract

- **Required top-level fields**:
  - `generated_at`
  - `total_files`
  - `total_chunks`
  - `languages`
  - `files`
- **Extended top-level fields for this feature**:
  - `schema_version`
  - `features`
  - `correlations`
  - `test_opportunities`
- **Behavior contract**:
  - Existing file inventory remains present for compatibility
  - Added feature metadata remains compact and reviewable
  - Evidence references point back to indexed files and line ranges whenever
    possible
