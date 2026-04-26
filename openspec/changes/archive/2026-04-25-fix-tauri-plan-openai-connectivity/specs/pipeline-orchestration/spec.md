## MODIFIED Requirements

### Requirement: Settings flow into CLI invocations
The desktop application SHALL pass the user's configured LLM provider, model, API key, Ollama URL, and Playwright-CLI timeout to every CLI invocation either via environment variables (`PLAYWRIGHT_GOD_PROVIDER`, `PLAYWRIGHT_GOD_MODEL`, `OPENAI_API_KEY`, etc.) or via the corresponding CLI flags.

#### Scenario: Provider override is honored
- **WHEN** the user sets the provider to `template` in Settings and runs the pipeline
- **THEN** the spawned CLI subprocesses receive `PLAYWRIGHT_GOD_PROVIDER=template` (or the equivalent flag) and use the offline template generator

#### Scenario: Plan step receives OpenAI runtime settings
- **WHEN** provider=`openai`, model=`gpt-5.4`, and an OpenAI key source is available
- **THEN** the `plan` step subprocess is spawned with `PLAYWRIGHT_GOD_PROVIDER=openai`, `PLAYWRIGHT_GOD_MODEL=gpt-5.4`, and `OPENAI_API_KEY` present in its runtime environment

## ADDED Requirements

### Requirement: LLM connectivity diagnostics for LLM-dependent steps
The desktop pipeline orchestrator SHALL emit classified diagnostics for LLM-dependent steps (`plan`, `generate`) so users can distinguish configuration issues from upstream/API/network failures.

#### Scenario: Missing OpenAI key fails fast with actionable message
- **WHEN** provider=`openai` is selected and no effective `OPENAI_API_KEY` source is available at plan-step start
- **THEN** the run fails that step with a clear configuration diagnostic describing the missing key source and next actions

#### Scenario: Upstream/API error is classified distinctly
- **WHEN** the `plan` step exits non-zero due to OpenAI auth/quota/network response errors
- **THEN** the run output classifies the failure as upstream/API connectivity rather than local settings absence
