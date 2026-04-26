## ADDED Requirements

### Requirement: LLM retry configuration fields
The Settings schema SHALL include `llm_retry_max` (integer, minimum 0, default 3) and `llm_retry_delay_s` (float, minimum 0.0, default 2.0) fields that control retry behaviour for LLM-dependent pipeline steps.

#### Scenario: Retry fields persisted and restored
- **WHEN** the user sets `llm_retry_max=1` and `llm_retry_delay_s=5.0` and saves
- **THEN** the values are persisted and pre-populated on the next app launch

#### Scenario: Zero max disables retries
- **WHEN** the user sets `llm_retry_max=0` and saves
- **THEN** the pipeline passes `--retry-max 0` to `plan` and `generate`, disabling automatic retries

#### Scenario: Negative values rejected
- **WHEN** the user enters `llm_retry_max=-1` or `llm_retry_delay_s=-1.0`
- **THEN** the form shows an inline validation error and the Save button is disabled

### Requirement: Retry settings UI controls
The Settings section SHALL expose a numeric input for "Max LLM retries" and a numeric input for "Retry initial delay (s)", with descriptive hint text explaining their effect.

#### Scenario: Hint text shown for retry fields
- **WHEN** the user views the Settings section
- **THEN** both retry fields are visible with hint text: "Max LLM retries: number of automatic retry attempts on network errors (0 = disabled)" and "Retry initial delay: seconds before first retry; subsequent retries use exponential backoff"
