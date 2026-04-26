# Desktop Settings

## Purpose

Capability added by the `tauri-desktop-ui` change (archived). See the change for the original proposal and design notes.

## Requirements

### Requirement: LLM provider configuration widget
The Settings section SHALL expose form controls for selecting the LLM provider (`openai`, `anthropic`, `gemini`, `ollama`, `template`, `playwright-cli`), entering the model name, entering the API key (masked input), entering the Ollama base URL, and entering the Playwright-CLI timeout (seconds, integer ≥ 1).

#### Scenario: Provider selection is persisted
- **WHEN** the user selects a provider, enters values, and clicks "Save"
- **THEN** the values are persisted to the desktop app's config file and pre-populated on the next app launch

#### Scenario: Invalid timeout is rejected
- **WHEN** the user enters a Playwright-CLI timeout less than 1 or non-integer
- **THEN** the form shows an inline validation error and the Save button is disabled

### Requirement: API keys are stored securely
The desktop application SHALL store API keys in the platform's secure credential store (Keychain on macOS, libsecret on Linux) when available, and SHALL fall back to a 0600-permission file in the app-config directory only when no secure store is available.

#### Scenario: Keychain storage on macOS
- **WHEN** the user saves an API key on macOS
- **THEN** the key is written to the macOS Keychain under a service identifier scoped to this app and is not written to any plaintext config file

#### Scenario: Plaintext fallback is restricted
- **WHEN** the secure credential store is unavailable
- **THEN** the key is written to a file with file-mode 0600 in the app-config directory and a warning is shown to the user in the Settings panel

### Requirement: Settings are exported into CLI invocations
The desktop application SHALL, when spawning a `playwright-god` subprocess, inject the configured provider, model, API key, Ollama URL, and Playwright-CLI timeout into the subprocess environment using the same environment variable names the CLI already reads (`PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_URL`).

#### Scenario: Saved settings reach the CLI
- **WHEN** the user saves provider=`anthropic`, model=`claude-3-5-sonnet-20241022`, and an API key, then runs the pipeline
- **THEN** the spawned CLI subprocess receives `PLAYWRIGHT_GOD_PROVIDER=anthropic`, `PLAYWRIGHT_GOD_MODEL=claude-3-5-sonnet-20241022`, and `ANTHROPIC_API_KEY=<key>` in its environment

#### Scenario: OpenAI settings resolve deterministically
- **WHEN** provider=`openai` and model=`gpt-5.4` are configured and both desktop settings/secrets and repository `.env` may contain values
- **THEN** the desktop app resolves effective runtime values with deterministic precedence (desktop settings/secrets first, then repository `.env` fallback, then process environment) and injects the resolved values into subprocesses

#### Scenario: Effective key source is surfaced without secret disclosure
- **WHEN** a pipeline run starts for an OpenAI-backed step
- **THEN** the UI/run diagnostics show which source supplied credentials (`settings`, `repo-dotenv`, `process-env`, or `missing`) without logging or rendering key contents

### Requirement: Reset to defaults
The Settings widget SHALL provide a "Reset to defaults" action that clears all stored values (including secure-store entries owned by this app) after a confirmation dialog.

#### Scenario: User resets settings
- **WHEN** the user clicks "Reset to defaults" and confirms
- **THEN** all settings are cleared, the form returns to the empty/default state, and any stored API keys for this app are removed from the secure store

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
