# Data Model: Repository Memory Inference

## RepositoryFeatureMap

- **Purpose**: Top-level representation of repository understanding used by
  generation, planning, and saved memory maps.
- **Fields**:
  - `generated_at`: timestamp for when analysis completed
  - `source_root`: analyzed repository path
  - `total_files`: number of indexed files
  - `total_chunks`: number of indexed chunks
  - `languages`: language frequency summary
  - `features`: collection of `FeatureArea`
  - `correlations`: collection of `FeatureCorrelation`
  - `test_opportunities`: collection of `TestOpportunity`
  - `file_index`: existing compact file-and-line inventory retained for prompt
    and inspection use
- **Validation rules**:
  - Must preserve existing file inventory fields needed by current memory-map
    consumers
  - Every feature, correlation, and test opportunity must reference known
    evidence items or file locations

## FeatureArea

- **Purpose**: Represents a user-visible capability or workflow inferred from
  repository evidence.
- **Fields**:
  - `feature_id`: stable identifier
  - `name`: concise feature name
  - `summary`: short human-readable explanation
  - `confidence`: normalized confidence score
  - `artifacts`: collection of `ArtifactEvidence` references
  - `entry_points`: routes, files, commands, or selectors that expose the
    feature
  - `workflows`: summarized user journeys associated with the feature
- **Validation rules**:
  - Must contain at least one evidence reference
  - Confidence must be between `0.0` and `1.0`
  - Names must be stable enough to reuse across memory maps and generated plans

## ArtifactEvidence

- **Purpose**: Captures repository proof that supports a feature area or test
  opportunity.
- **Fields**:
  - `artifact_id`: stable identifier
  - `file_path`: repository-relative file path
  - `language`: detected file language
  - `start_line`: first supporting line, when available
  - `end_line`: last supporting line, when available
  - `signal_type`: category such as route, selector, form, config, test, or
    content match
  - `summary`: short explanation of why the artifact matters
- **Validation rules**:
  - `file_path` must point to an indexed file
  - Line ranges must align with known chunks when line information is present

## FeatureCorrelation

- **Purpose**: Describes how feature areas or artifacts work together.
- **Fields**:
  - `correlation_id`: stable identifier
  - `source_feature_id`: originating feature
  - `target_feature_id`: related feature
  - `relationship_type`: dependency, navigation, shared-data-flow,
    auth-boundary, or similar
  - `confidence`: normalized confidence score
  - `evidence_ids`: supporting artifact references
  - `summary`: explanation of the relationship
- **Validation rules**:
  - Must reference at least one evidence item
  - Source and target features must exist in the same feature map

## TestOpportunity

- **Purpose**: Represents a candidate Python Playwright test derived from the
  repository understanding.
- **Fields**:
  - `opportunity_id`: stable identifier
  - `feature_id`: owning feature
  - `title`: user-journey-style name
  - `priority`: relative importance such as high, medium, low
  - `confidence`: normalized confidence score
  - `evidence_ids`: repository evidence supporting the recommendation
  - `preconditions`: required state such as auth or setup
  - `assertions`: expected user-visible outcomes to verify
  - `uncertainty_notes`: optional reviewer guidance for ambiguous cases
- **Validation rules**:
  - Must reference one feature and at least one evidence item
  - Must read as a user-visible behavior, not an internal implementation check

## MemoryMapSnapshot

- **Purpose**: Persisted artifact used for reuse across `generate` and `plan`
  workflows.
- **Fields**:
  - `schema_version`: snapshot format version
  - `repository_feature_map`: compact serialized `RepositoryFeatureMap`
  - `saved_at`: timestamp of persistence
  - `generator_hints`: optional summary guidance for downstream prompts
- **Validation rules**:
  - Must remain compact enough for prompt reuse
  - Must preserve enough context for later planning without requiring full
    repository re-analysis

## State Transitions

- `discovered` -> `correlated`: files and chunks are grouped into feature areas
- `correlated` -> `ranked`: test opportunities receive evidence and priority
- `ranked` -> `persisted`: streamlined memory map is saved for reuse
- `persisted` -> `reused`: downstream generation or planning workflows consume
  the saved memory snapshot
