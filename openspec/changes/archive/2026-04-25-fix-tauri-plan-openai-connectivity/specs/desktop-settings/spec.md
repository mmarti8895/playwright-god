## MODIFIED Requirements

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
