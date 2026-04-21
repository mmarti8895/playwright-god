"""Command-line interface for playwright-god."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env file if it exists.
# `override=False` ensures shell/CI environment variables take precedence over .env,
# which is important for test isolation and for CI overrides to work as expected.
load_dotenv(override=False)

from .chunker import FileChunker
from .crawler import FileInfo, RepositoryCrawler
from .embedder import DefaultEmbedder
from .feature_map import format_feature_summary, infer_repository_feature_map
from .generator import (
    AnthropicClient,
    GeminiClient,
    OllamaClient,
    OpenAIClient,
    PlaywrightCLIClient,
    PlaywrightCLIError,
    PlaywrightTestGenerator,
    TemplateLLMClient,
)
from .indexer import RepositoryIndexer
from .memory_map import (
    build_memory_map,
    format_memory_map_for_prompt,
    load_memory_map,
    save_memory_map,
)
from .runner import PlaywrightRunner, RunResult, RunnerSetupError


def _resolve_provider_config(
    provider: str | None,
    model: str | None,
    api_key: str | None,
    ollama_url: str,
) -> tuple[str, str | None, str | None, str]:
    """Resolve LLM provider configuration from CLI args, env vars, and defaults.

    Priority order (highest to lowest):
    1. Explicit CLI arguments (--provider, --model, --api-key, --ollama-url)
    2. PLAYWRIGHT_GOD_* environment variables from .env or shell
    3. Provider-specific API key env vars (OPENAI_API_KEY, etc.) for auto-detection
    4. Fallback to "template" provider

    Returns:
        Tuple of (provider, model, api_key, ollama_url)
    """
    # Resolve provider: CLI arg > PLAYWRIGHT_GOD_PROVIDER env > auto-detect from API keys
    resolved_provider = provider
    if resolved_provider is None:
        env_provider = os.environ.get("PLAYWRIGHT_GOD_PROVIDER", "").strip().lower()
        # Only accept providers here that are supported by all commands using this
        # shared resolver. `playwright-cli` is command-specific and must not be
        # enabled globally via environment configuration.
        if env_provider in ("openai", "anthropic", "gemini", "ollama", "template"):
            resolved_provider = env_provider

    # If still no provider, auto-detect from API keys
    if resolved_provider is None:
        if api_key or os.environ.get("OPENAI_API_KEY"):
            resolved_provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            resolved_provider = "anthropic"
        elif os.environ.get("GOOGLE_API_KEY"):
            resolved_provider = "gemini"
        else:
            resolved_provider = "template"

    # Resolve model: CLI arg > PLAYWRIGHT_GOD_MODEL env > provider default (handled later)
    resolved_model = model
    if resolved_model is None:
        env_model = os.environ.get("PLAYWRIGHT_GOD_MODEL", "").strip()
        if env_model:
            resolved_model = env_model

    # Resolve API key: CLI arg > existing env vars (already loaded by dotenv)
    resolved_api_key = api_key  # CLI arg takes precedence, env vars already in os.environ

    # Resolve Ollama URL: CLI arg (if non-default) > OLLAMA_URL env > default
    resolved_ollama_url = ollama_url
    if ollama_url == "http://localhost:11434":  # default value, check env
        env_ollama_url = os.environ.get("OLLAMA_URL", "").strip()
        if env_ollama_url:
            resolved_ollama_url = env_ollama_url

    return resolved_provider, resolved_model, resolved_api_key, resolved_ollama_url


@click.group()
@click.version_option()
def cli() -> None:
    """Playwright God - AI-powered Playwright test generator.

    \b
    Workflow:
      1. playwright-god index <repo-path>   # index the repository
      2. playwright-god generate "..."      # generate a TypeScript Playwright test
    """


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--persist-dir",
    "-d",
    default=".playwright_god_index",
    show_default=True,
    help="Directory to persist the vector index.",
)
@click.option(
    "--collection",
    "-c",
    default="repo",
    show_default=True,
    help="ChromaDB collection name.",
)
@click.option(
    "--chunk-size",
    default=80,
    show_default=True,
    help="Maximum number of lines per chunk.",
)
@click.option(
    "--overlap",
    default=10,
    show_default=True,
    help="Overlapping lines between adjacent chunks.",
)
@click.option(
    "--extra-files",
    "-e",
    multiple=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Additional files to include in the index that live outside REPO_PATH "
        "(e.g. IdP metadata XML, SAML config). May be specified multiple times."
    ),
)
@click.option(
    "--memory-map",
    "-m",
    default=None,
    type=click.Path(dir_okay=False),
    help=(
        "Write a JSON memory map of the indexed chunks to this file. The map can later "
        "be passed to `generate --memory-map` or `plan` to give the AI a concise overview "
        "of the codebase structure and inferred feature relationships."
    ),
)
@click.option(
    "--mock-embedder",
    is_flag=True,
    default=False,
    hidden=True,
    help="Use the deterministic mock embedder (for testing without network access).",
)
def index(
    repo_path: str,
    persist_dir: str,
    collection: str,
    chunk_size: int,
    overlap: int,
    extra_files: tuple[str, ...],
    memory_map: str | None,
    mock_embedder: bool,
) -> None:
    """Crawl REPO_PATH and build a vector index for test generation.

    REPO_PATH defaults to the current directory.
    """
    click.echo(f"Crawling repository: {os.path.abspath(repo_path)}")
    crawler = RepositoryCrawler()
    files = crawler.crawl(repo_path)
    click.echo(f"  Found {len(files)} files")

    for extra_path in extra_files:
        path = Path(extra_path).resolve()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            language = crawler._detect_language(path)
            files.append(
                FileInfo(
                    path=str(path),
                    absolute_path=str(path),
                    content=content,
                    language=language,
                    size=len(content.encode("utf-8")),
                )
            )
            click.echo(f"  Added extra file: {path} ({language})")
        except OSError as exc:
            click.echo(f"  Warning: could not read {extra_path!r}: {exc}", err=True)

    if not files:
        click.echo("  No files found - nothing to index.", err=True)
        sys.exit(1)

    click.echo("Building structure summary...")
    click.echo(crawler.build_structure_summary(files))

    click.echo("Chunking files...")
    chunker = FileChunker(chunk_size=chunk_size, overlap=overlap)
    chunks = chunker.chunk_files(files)
    click.echo(f"  Created {len(chunks)} chunks")

    click.echo("Inferring repository features...")
    feature_map = infer_repository_feature_map(
        files,
        chunks=chunks,
        source_root=os.path.abspath(repo_path),
    )
    click.echo(format_feature_summary(feature_map))

    click.echo("Embedding and indexing...")
    from .embedder import MockEmbedder as _MockEmbedder

    embedder = _MockEmbedder() if mock_embedder else DefaultEmbedder()
    indexer = RepositoryIndexer(
        collection_name=collection,
        persist_dir=persist_dir,
        embedder=embedder,
    )
    indexer.add_chunks(chunks)
    click.echo(f"  Index saved to: {persist_dir!r}  ({indexer.count()} vectors)")

    if memory_map:
        map_data = build_memory_map(chunks, repository_feature_map=feature_map)
        save_memory_map(map_data, memory_map)
        click.echo(f"  Memory map saved to: {memory_map!r}")

    click.echo("Done.")


@cli.command()
@click.argument("description")
@click.option(
    "--persist-dir",
    "-d",
    default=".playwright_god_index",
    show_default=True,
    help="Directory with the persisted vector index.",
)
@click.option(
    "--collection",
    "-c",
    default="repo",
    show_default=True,
    help="ChromaDB collection name.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(dir_okay=False),
    help="Write generated test to this file (default: stdout).",
)
@click.option(
    "--n-context",
    default=10,
    show_default=True,
    help="Number of context chunks to retrieve.",
)
@click.option(
    "--model",
    default=None,
    show_default=True,
    help=(
        "Model name to use with the selected provider "
        "(e.g. gpt-4o, claude-3-5-sonnet-20241022, gemini-1.5-pro, llama3)."
    ),
)
@click.option(
    "--provider",
    default=None,
    type=click.Choice(
        ["openai", "anthropic", "gemini", "ollama", "template", "playwright-cli"],
        case_sensitive=False,
    ),
    help=(
        "LLM provider to use. Auto-detected from environment variables when "
        "not set (OPENAI_API_KEY -> openai, ANTHROPIC_API_KEY -> anthropic, "
        "GOOGLE_API_KEY -> gemini). Falls back to the offline template "
        "generator when no key is found. Use 'playwright-cli' to record "
        "tests interactively with `npx playwright codegen`."
    ),
)
@click.option(
    "--api-key",
    default=None,
    help="API key for the selected provider (overrides the environment variable).",
)
@click.option(
    "--ollama-url",
    default="http://localhost:11434",
    show_default=True,
    help="Base URL of the Ollama server (used only when --provider=ollama).",
)
@click.option(
    "--playwright-cli-url",
    default=None,
    help=(
        "Base URL passed to `npx playwright codegen` when "
        "--provider=playwright-cli. Overrides any URL found in the prompt "
        "or memory map. Example: http://localhost:3000"
    ),
)
@click.option(
    "--playwright-cli-timeout",
    default=PlaywrightCLIClient.DEFAULT_TIMEOUT,
    show_default=True,
    type=int,
    help=(
        "Seconds to wait for the Playwright Inspector window to be closed "
        "when --provider=playwright-cli. "
        "Increase for long recording sessions."
    ),
)
@click.option(
    "--auth-type",
    default=None,
    type=click.Choice(
        ["saml", "ntlm", "oidc", "basic", "logging", "none"],
        case_sensitive=False,
    ),
    help=(
        "Authentication mechanism used by the system under test. Injects "
        "the relevant auth hint and Python template snippet into the prompt "
        "so the LLM produces correct auth and logging test code. "
        "Choices: saml, ntlm, oidc, basic, logging, none."
    ),
)
@click.option(
    "--auth-config",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a JSON or YAML file with non-secret auth metadata "
        "(e.g. IdP URL, SP entity ID, callback URL, LDAP domain). "
        "Its contents are appended to the prompt as extra context."
    ),
)
@click.option(
    "--env-file",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a .env file listing the credential environment-variable "
        "names used by the test suite (e.g. TEST_USERNAME, TEST_PASSWORD). "
        "Only the variable names are forwarded to the prompt - values are "
        "never included."
    ),
)
@click.option(
    "--redact-secrets/--no-redact-secrets",
    default=True,
    show_default=True,
    help=(
        "Replace hardcoded credential literals in the generated output with "
        "os.environ placeholders (enabled by default)."
    ),
)
@click.option(
    "--memory-map",
    "-m",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a memory map JSON file (produced by `index --memory-map`). "
        "Its structured file and feature inventory is injected into the prompt so "
        "the AI understands the indexed codebase."
    ),
)
@click.option(
    "--mock-embedder",
    is_flag=True,
    default=False,
    hidden=True,
    help="Use the deterministic mock embedder (for testing without network access).",
)
@click.option(
    "--run",
    "run_after_generate",
    is_flag=True,
    default=False,
    help=(
        "After generation, execute the produced spec via `npx playwright test "
        "--reporter=json` and exit non-zero if any test fails. Requires --output "
        "(or a temp file is created)."
    ),
)
@click.option(
    "--target-dir",
    "run_target_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Playwright project directory used when --run is set.",
)
@click.option(
    "--artifact-dir",
    "run_artifact_dir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Artifact root directory used when --run is set.",
)
@click.option(
    "--coverage",
    "coverage_flag",
    is_flag=True,
    default=False,
    help=(
        "Enable V8 frontend coverage capture during --run (sets "
        "PLAYWRIGHT_GOD_COVERAGE_DIR for the bundled fixture)."
    ),
)
@click.option(
    "--backend-coverage",
    "backend_coverage_cmd",
    default=None,
    help=(
        "Shell command that starts the backend under coverage. When set, "
        "the backend is started before --run and stopped afterwards. "
        "Implies --coverage."
    ),
)
@click.option(
    "--coverage-report",
    "coverage_report_path",
    default=None,
    type=click.Path(file_okay=True, dir_okay=False),
    help=(
        "Path to an existing coverage report JSON to inject as 'Uncovered "
        "code (gaps)' excerpts into the generation prompt."
    ),
)
@click.option(
    "--coverage-cap",
    default=12,
    show_default=True,
    type=int,
    help="Maximum uncovered excerpts to include in the prompt.",
)
def generate(
    description: str,
    persist_dir: str,
    collection: str,
    output: str | None,
    n_context: int,
    model: str | None,
    provider: str | None,
    api_key: str | None,
    ollama_url: str,
    playwright_cli_url: str | None,
    playwright_cli_timeout: int,
    auth_type: str | None,
    auth_config: str | None,
    env_file: str | None,
    redact_secrets: bool,
    memory_map: str | None,
    mock_embedder: bool,
    run_after_generate: bool,
    run_target_dir: str | None,
    run_artifact_dir: str | None,
    coverage_flag: bool,
    backend_coverage_cmd: str | None,
    coverage_report_path: str | None,
    coverage_cap: int,
) -> None:
    """Generate a Playwright test for the given DESCRIPTION.

    Retrieves relevant code context from the index built with the
    `index` command, then calls an LLM (or the template fallback) to
    produce a TypeScript Playwright test.
    """
    from .embedder import MockEmbedder as _MockEmbedder

    embedder = _MockEmbedder() if mock_embedder else DefaultEmbedder()
    indexer = RepositoryIndexer(
        collection_name=collection,
        persist_dir=persist_dir,
        embedder=embedder,
    )

    if indexer.count() == 0:
        click.echo(
            f"Warning: index at {persist_dir!r} is empty or does not exist. "
            "Run `playwright-god index <repo-path>` first.",
            err=True,
        )

    # Resolve provider config from CLI args, env vars, and defaults
    provider, model, api_key, ollama_url = _resolve_provider_config(
        provider, model, api_key, ollama_url
    )

    llm_client: OpenAIClient | AnthropicClient | GeminiClient | OllamaClient | TemplateLLMClient | PlaywrightCLIClient
    if provider == "openai":
        resolved_model = model or "gpt-4o"
        click.echo(f"Using OpenAI model: {resolved_model}", err=True)
        llm_client = OpenAIClient(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            model=resolved_model,
        )
    elif provider == "anthropic":
        resolved_model = model or "claude-3-5-sonnet-20241022"
        click.echo(f"Using Anthropic model: {resolved_model}", err=True)
        llm_client = AnthropicClient(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            model=resolved_model,
        )
    elif provider == "gemini":
        resolved_model = model or "gemini-1.5-pro"
        click.echo(f"Using Google Gemini model: {resolved_model}", err=True)
        llm_client = GeminiClient(
            api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""),
            model=resolved_model,
        )
    elif provider == "ollama":
        resolved_model = model or "llama3"
        click.echo(f"Using Ollama model: {resolved_model} at {ollama_url}", err=True)
        llm_client = OllamaClient(model=resolved_model, base_url=ollama_url)
    elif provider == "playwright-cli":
        click.echo(
            "Using playwright-cli backend (npx playwright codegen). "
            "A browser window will open — record your interactions, then close "
            "the Playwright Inspector to capture the spec.",
            err=True,
        )
        llm_client = PlaywrightCLIClient(
            url=playwright_cli_url,
            timeout=playwright_cli_timeout,
        )
    else:
        click.echo(
            "No LLM provider detected - using offline template generator.",
            err=True,
        )
        llm_client = TemplateLLMClient()

    extra_parts: list[str] = []

    if memory_map:
        try:
            map_data = load_memory_map(memory_map)
            extra_parts.append(format_memory_map_for_prompt(map_data))
            click.echo(f"Memory map loaded from: {memory_map!r}", err=True)
        except (FileNotFoundError, ValueError) as exc:
            click.echo(f"Warning: could not load --memory-map {memory_map!r}: {exc}", err=True)

    if auth_config:
        try:
            with open(auth_config, encoding="utf-8") as fh:
                raw = fh.read()
            extra_parts.append(f"Auth configuration ({auth_config}):\n{raw}")
        except OSError as exc:
            click.echo(f"Warning: could not read --auth-config {auth_config!r}: {exc}", err=True)

    if env_file:
        try:
            env_var_names: list[str] = []
            with open(env_file, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        var_name = line.split("=", 1)[0].strip()
                        if var_name:
                            env_var_names.append(var_name)
            if env_var_names:
                extra_parts.append(
                    "Credential environment variable names available in this project "
                    "(use these in generated tests instead of hardcoded values):\n"
                    + "\n".join(f"  process.env.{name} ?? \"\"" for name in env_var_names)
                )
        except OSError as exc:
            click.echo(f"Warning: could not read --env-file {env_file!r}: {exc}", err=True)

    extra_context = "\n\n".join(extra_parts) if extra_parts else None

    # Optional uncovered-code excerpts loaded from a prior coverage report.
    uncovered_excerpts: list[tuple[str, int, int, str]] | None = None
    if coverage_report_path:
        from .coverage import coverage_from_dict

        try:
            with open(coverage_report_path, "r", encoding="utf-8") as fh:
                _cov_payload = json.load(fh)
            _cov_report = coverage_from_dict(_cov_payload)
            uncovered_excerpts = _build_uncovered_excerpts(
                _cov_report, cap=coverage_cap
            )
            click.echo(
                f"Coverage report loaded from: {coverage_report_path!r} "
                f"({len(uncovered_excerpts)} uncovered excerpt(s))",
                err=True,
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            click.echo(
                f"Warning: could not load --coverage-report {coverage_report_path!r}: {exc}",
                err=True,
            )

    generator = PlaywrightTestGenerator(
        llm_client=llm_client,
        indexer=indexer,
        n_context=n_context,
    )

    click.echo(f"Generating test for: {description!r}", err=True)
    if auth_type:
        click.echo(f"Auth type: {auth_type}", err=True)

    try:
        test_code = generator.generate(
            description,
            extra_context=extra_context,
            auth_type=auth_type,
            redact_secrets=redact_secrets,
            uncovered_excerpts=uncovered_excerpts,
            uncovered_cap=coverage_cap,
        )
    except PlaywrightCLIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(test_code)
        click.echo(f"Test written to: {output}", err=True)
    else:
        click.echo(test_code)

    if run_after_generate:
        spec_path = output
        if spec_path is None:
            import tempfile

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".spec.ts", delete=False, encoding="utf-8"
            )
            tmp.write(test_code)
            tmp.close()
            spec_path = tmp.name
            click.echo(f"Wrote temp spec to: {spec_path}", err=True)

        runner = PlaywrightRunner(
            target_dir=run_target_dir,
            artifact_dir=run_artifact_dir,
            coverage=coverage_flag or bool(backend_coverage_cmd),
        )
        try:
            if backend_coverage_cmd:
                from .coverage import CoverageCollector

                collector = CoverageCollector(
                    frontend=True,
                    backend_cmd=backend_coverage_cmd,
                )
                captured: dict[str, RunResult] = {}

                def _run() -> None:
                    captured["r"] = runner.run(spec_path)

                merged = collector.collect(_run)
                result = captured["r"]
                # Persist the merged report alongside the run artifacts.
                if result.report_dir is not None:
                    from .coverage import coverage_to_dict

                    cov_path = Path(result.report_dir) / "coverage_merged.json"
                    cov_path.write_text(
                        json.dumps(coverage_to_dict(merged), indent=2),
                        encoding="utf-8",
                    )
                    click.echo(f"Coverage report: {cov_path}", err=True)
            else:
                result = runner.run(spec_path)
        except RunnerSetupError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(2)
        _print_run_summary(result)
        sys.exit(0 if result.status == "passed" else 1)


@cli.command()
@click.option(
    "--memory-map",
    "-m",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a memory map JSON file (produced by `index --memory-map`). "
        "Required unless --persist-dir contains an indexed collection."
    ),
)
@click.option(
    "--persist-dir",
    "-d",
    default=".playwright_god_index",
    show_default=True,
    help=(
        "Directory with the persisted vector index. Used to build an "
        "on-the-fly memory map when --memory-map is not provided."
    ),
)
@click.option(
    "--collection",
    "-c",
    default="repo",
    show_default=True,
    help="ChromaDB collection name (used when building the map from the index).",
)
@click.option(
    "--focus",
    default=None,
    help=(
        "Optional free-text hint to narrow the plan to a specific area "
        "(e.g. 'authentication flows' or 'checkout process')."
    ),
)
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(dir_okay=False),
    help="Write the test plan to this file (default: stdout).",
)
@click.option(
    "--provider",
    default=None,
    type=click.Choice(
        ["openai", "anthropic", "gemini", "ollama", "template"],
        case_sensitive=False,
    ),
    help=(
        "LLM provider to use. Auto-detected from environment variables when "
        "not set. Falls back to the offline template generator."
    ),
)
@click.option(
    "--model",
    default=None,
    help="Model name to use with the selected provider.",
)
@click.option(
    "--api-key",
    default=None,
    help="API key for the selected provider (overrides the environment variable).",
)
@click.option(
    "--ollama-url",
    default="http://localhost:11434",
    show_default=True,
    help="Base URL of the Ollama server (used only when --provider=ollama).",
)
@click.option(
    "--mock-embedder",
    is_flag=True,
    default=False,
    hidden=True,
    help="Use the deterministic mock embedder (for testing without network access).",
)
@click.option(
    "--coverage-report",
    "coverage_report_path",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a coverage report JSON (from `playwright-god run --coverage`). "
        "Adds a `## Coverage Delta` section and prioritises feature areas by "
        "uncovered code."
    ),
)
@click.option(
    "--prioritize",
    type=click.Choice(["absolute", "percent", "routes"], case_sensitive=False),
    default="absolute",
    show_default=True,
    help=(
        "How to rank uncovered files in the Coverage Delta section: "
        "'absolute' (most uncovered lines first), 'percent' (lowest "
        "covered percentage first), or 'routes' (files referenced by the "
        "most uncovered flow-graph routes first)."
    ),
)
@click.option(
    "--flow-graph",
    "flow_graph_path",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a flow_graph.json (from `playwright-god graph extract`). "
        "Annotates the plan with uncovered routes/actions."
    ),
)
def plan(
    memory_map: str | None,
    persist_dir: str,
    collection: str,
    focus: str | None,
    output: str | None,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    ollama_url: str,
    mock_embedder: bool,  # noqa: ARG001
    coverage_report_path: str | None,
    prioritize: str,
    flow_graph_path: str | None,
) -> None:
    """Generate an AI-powered Playwright test plan from the indexed codebase.

    \b
    The plan command analyses the memory map of the indexed repository and
    asks the AI to suggest comprehensive test scenarios grouped by feature
    area. The result is a Markdown document that can guide manual or
    automated test authoring.

    \b
    Typical workflow:
      playwright-god index . --memory-map .playwright_god_index/memory_map.json
      playwright-god plan --memory-map .playwright_god_index/memory_map.json
      playwright-god plan --memory-map ... --focus "authentication" -o plan.md
    """
    map_data: dict | None = None

    if memory_map:
        try:
            map_data = load_memory_map(memory_map)
            click.echo(f"Memory map loaded from: {memory_map!r}", err=True)
        except (FileNotFoundError, ValueError) as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)
    else:
        click.echo(
            f"No --memory-map provided; building from index at {persist_dir!r} ...",
            err=True,
        )
        from .embedder import MockEmbedder as _MockEmbedder

        indexer = RepositoryIndexer(
            collection_name=collection,
            persist_dir=persist_dir,
            embedder=_MockEmbedder(),
        )
        if indexer.count() == 0:
            click.echo(
                f"Error: index at {persist_dir!r} is empty or does not exist. "
                "Run `playwright-god index <repo-path>` first.",
                err=True,
            )
            sys.exit(1)

        chunks = indexer.get_chunk_stubs()
        map_data = build_memory_map(chunks)
        click.echo(
            f"  Built memory map: {map_data['total_files']} files, "
            f"{map_data['total_chunks']} chunks",
            err=True,
        )

    memory_map_text = format_memory_map_for_prompt(map_data)

    # Resolve provider config from CLI args, env vars, and defaults
    provider, model, api_key, ollama_url = _resolve_provider_config(
        provider, model, api_key, ollama_url
    )

    llm_client: OpenAIClient | AnthropicClient | GeminiClient | OllamaClient | TemplateLLMClient
    if provider == "openai":
        resolved_model = model or "gpt-4o"
        click.echo(f"Using OpenAI model: {resolved_model}", err=True)
        llm_client = OpenAIClient(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            model=resolved_model,
        )
    elif provider == "anthropic":
        resolved_model = model or "claude-3-5-sonnet-20241022"
        click.echo(f"Using Anthropic model: {resolved_model}", err=True)
        llm_client = AnthropicClient(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            model=resolved_model,
        )
    elif provider == "gemini":
        resolved_model = model or "gemini-1.5-pro"
        click.echo(f"Using Google Gemini model: {resolved_model}", err=True)
        llm_client = GeminiClient(
            api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""),
            model=resolved_model,
        )
    elif provider == "ollama":
        resolved_model = model or "llama3"
        click.echo(f"Using Ollama model: {resolved_model} at {ollama_url}", err=True)
        llm_client = OllamaClient(model=resolved_model, base_url=ollama_url)
    else:
        click.echo(
            "No LLM provider detected - using offline template planner.",
            err=True,
        )
        llm_client = TemplateLLMClient()

    generator = PlaywrightTestGenerator(llm_client=llm_client)

    click.echo("Generating test plan...", err=True)
    if focus:
        click.echo(f"Focus: {focus}", err=True)

    coverage_payload: dict | None = None
    if coverage_report_path:
        try:
            with open(coverage_report_path, "r", encoding="utf-8") as fh:
                coverage_payload = _coverage_payload_for_plan(json.load(fh))
            click.echo(
                f"Coverage report loaded from: {coverage_report_path!r}", err=True
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            click.echo(
                f"Warning: could not load --coverage-report {coverage_report_path!r}: {exc}",
                err=True,
            )

    plan_text = generator.plan(
        memory_map_text,
        focus=focus,
        coverage=coverage_payload,
        prioritize=prioritize.lower(),
        flow_graph=_load_flow_graph(flow_graph_path) if flow_graph_path else None,
    )

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(plan_text)
        click.echo(f"Test plan written to: {output}", err=True)
    else:
        click.echo(plan_text)


def _print_run_summary(result: RunResult, *, json_output: bool = False) -> None:
    """Render a ``RunResult`` to stderr (human) or stdout (json)."""

    if json_output:
        payload = {
            "status": result.status,
            "duration_ms": result.duration_ms,
            "exit_code": result.exit_code,
            "spec_path": str(result.spec_path) if result.spec_path else None,
            "report_dir": str(result.report_dir) if result.report_dir else None,
            "tests": [
                {
                    "title": t.title,
                    "status": t.status,
                    "duration_ms": t.duration_ms,
                    "error_message": t.error_message,
                    "trace_path": t.trace_path,
                }
                for t in result.tests
            ],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    icon = {"passed": "PASS", "failed": "FAIL", "error": "ERROR"}.get(result.status, "?")
    click.echo(
        f"[{icon}] {len(result.tests)} test(s) in {result.duration_ms} ms "
        f"(exit={result.exit_code})",
        err=True,
    )
    for t in result.tests:
        line = f"  - {t.status:<8} {t.title} ({t.duration_ms} ms)"
        click.echo(line, err=True)
        if t.error_message and t.status not in ("passed", "skipped"):
            for err_line in t.error_message.splitlines()[:5]:
                click.echo(f"      {err_line}", err=True)
    if result.report_dir:
        click.echo(f"Artifacts: {result.report_dir}", err=True)


@cli.command(name="run")
@click.argument("spec_path", type=click.Path(exists=True, file_okay=True, dir_okay=True))
@click.option(
    "--target-dir",
    "-t",
    default=None,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help=(
        "Directory containing the Playwright project's package.json. "
        "Defaults to walking up from SPEC_PATH until a package.json is found."
    ),
)
@click.option(
    "--reporter",
    default="json",
    show_default=True,
    help="Playwright reporter to request (only 'json' is parsed).",
)
@click.option(
    "--artifact-dir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True),
    help=(
        "Root directory for per-run artifact subdirectories. "
        "Defaults to '<target-dir>/.pg_runs'."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit the RunResult as JSON on stdout (in addition to artifacts on disk).",
)
@click.option(
    "--coverage",
    "coverage_flag",
    is_flag=True,
    default=False,
    help="Enable V8 frontend coverage capture (Chromium only).",
)
@click.option(
    "--backend-coverage",
    "backend_coverage_cmd",
    default=None,
    help=(
        "Shell command that starts the backend under `coverage run`. "
        "Implies --coverage."
    ),
)
def run(
    spec_path: str,
    target_dir: str | None,
    reporter: str,
    artifact_dir: str | None,
    json_output: bool,
    coverage_flag: bool,
    backend_coverage_cmd: str | None,
) -> None:
    """Execute a generated Playwright SPEC_PATH and report results.

    Shells out to ``npx playwright test --reporter=json`` and writes
    artifacts under ``<artifact-dir>/<UTC-timestamp>/``. Exits non-zero
    when any test fails or the runner could not start.
    """

    runner = PlaywrightRunner(
        target_dir=target_dir,
        artifact_dir=artifact_dir,
        reporter=reporter,
        coverage=coverage_flag or bool(backend_coverage_cmd),
    )
    try:
        if backend_coverage_cmd:
            from .coverage import CoverageCollector, coverage_to_dict

            collector = CoverageCollector(
                frontend=True, backend_cmd=backend_coverage_cmd
            )
            captured: dict[str, RunResult] = {}

            def _run() -> None:
                captured["r"] = runner.run(spec_path)

            merged = collector.collect(_run)
            result = captured["r"]
            if result.report_dir is not None:
                cov_path = Path(result.report_dir) / "coverage_merged.json"
                cov_path.write_text(
                    json.dumps(coverage_to_dict(merged), indent=2),
                    encoding="utf-8",
                )
                click.echo(f"Coverage report: {cov_path}", err=True)
        else:
            result = runner.run(spec_path)
    except RunnerSetupError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    _print_run_summary(result, json_output=json_output)
    sys.exit(0 if result.status == "passed" else 1)


# ---------------------------------------------------------------------------
# Coverage helpers + `coverage` command group
# ---------------------------------------------------------------------------


def _coverage_payload_for_plan(report_dict: dict) -> dict:
    """Convert a serialized CoverageReport dict into the shape `plan` expects."""

    files_in = report_dict.get("files") or {}
    out_files: list[dict] = []
    total_covered = 0
    total_uncovered = 0
    for path, entry in sorted(files_in.items()):
        if not isinstance(entry, dict):
            continue
        total = int(entry.get("total_lines", 0))
        covered = int(entry.get("covered_lines", 0))
        uncovered = max(0, total - covered)
        total_covered += covered
        total_uncovered += uncovered
        percent = entry.get("percent")
        if percent is None:
            percent = (covered / total * 100.0) if total else 100.0
        out_files.append(
            {
                "path": path,
                "covered_lines": list(range(1, covered + 1)),
                "uncovered_lines": list(range(1, uncovered + 1)),
                "percent": round(float(percent), 2),
            }
        )
    total = total_covered + total_uncovered
    return {
        "summary": {
            "files": len(out_files),
            "covered_lines": total_covered,
            "uncovered_lines": total_uncovered,
            "percent": round((total_covered / total * 100.0) if total else 100.0, 2),
        },
        "files": out_files,
    }


def _build_uncovered_excerpts(report, *, cap: int = 12, workdir: Path | None = None):
    """Build (path, start, end, body) tuples from a CoverageReport's gaps."""

    base = Path(workdir) if workdir else Path.cwd()
    out: list[tuple[str, int, int, str]] = []
    files = getattr(report, "files", {}) or {}
    ranked = sorted(
        files.values(),
        key=lambda fc: -sum((end - start + 1) for start, end in fc.missing_line_ranges),
    )
    for fc in ranked:
        if len(out) >= cap:
            break
        if not fc.missing_line_ranges:
            continue
        candidate = Path(fc.path)
        path = candidate if candidate.is_absolute() else base / candidate
        if not path.is_file():
            continue
        try:
            source_lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for start, end in fc.missing_line_ranges:
            if len(out) >= cap:
                break
            snippet = "\n".join(source_lines[start - 1 : end])
            out.append((fc.path, start, end, snippet))
    return out


@cli.group(name="coverage")
def coverage_group() -> None:
    """Coverage-report inspection commands."""


@coverage_group.command(name="report")
@click.argument("report_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json", "html"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(dir_okay=False),
    help="Write the rendered report to this file (default: stdout).",
)
def coverage_report_cmd(report_path: str, fmt: str, output: str | None) -> None:
    """Render a coverage report (read-only)."""

    try:
        with open(report_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        click.echo(f"Error: could not load {report_path!r}: {exc}", err=True)
        sys.exit(1)

    fmt = fmt.lower()
    if fmt == "json":
        rendered = json.dumps(payload, indent=2)
    elif fmt == "html":
        rendered = _render_coverage_html(payload)
    else:
        rendered = _render_coverage_text(payload)

    if output:
        Path(output).write_text(rendered, encoding="utf-8")
        click.echo(f"Coverage report written to: {output}", err=True)
    else:
        click.echo(rendered)


def _render_coverage_text(payload: dict) -> str:
    totals = payload.get("totals") or {}
    files = payload.get("files") or {}
    lines: list[str] = [
        "Coverage report",
        "===============",
        f"Source       : {payload.get('source', '?')}",
        f"Generated at : {payload.get('generated_at', '?')}",
        f"Files        : {totals.get('total_files', len(files))}",
        f"Lines        : {totals.get('covered_lines', 0)}/"
        f"{totals.get('total_lines', 0)} ({totals.get('percent', 0.0)}%)",
        "",
        "Per file (least covered first):",
    ]
    rows = []
    for path, entry in files.items():
        if not isinstance(entry, dict):
            continue
        rows.append(
            (
                float(entry.get("percent", 100.0)),
                path,
                int(entry.get("covered_lines", 0)),
                int(entry.get("total_lines", 0)),
                entry.get("missing_line_ranges") or [],
            )
        )
    rows.sort(key=lambda r: (r[0], -r[3]))
    for percent, path, covered, total, missing in rows[:50]:
        miss_str = ", ".join(
            f"{a}-{b}" if a != b else f"{a}" for a, b in missing[:6]
        )
        if len(missing) > 6:
            miss_str += f", +{len(missing) - 6} more"
        lines.append(
            f"  {percent:6.2f}%  {covered}/{total}  {path}"
            + (f"  missing: {miss_str}" if miss_str else "")
        )
    routes = payload.get("routes") or {}
    if isinstance(routes, dict) and routes:
        covered_ids = list(routes.get("covered") or [])
        uncovered_ids = list(routes.get("uncovered") or [])
        total = int(routes.get("total") or (len(covered_ids) + len(uncovered_ids)))
        lines.extend([
            "",
            "Routes",
            "------",
            f"Covered  : {len(covered_ids)}/{total}",
        ])
        for rid in uncovered_ids[:25]:
            lines.append(f"  uncovered: {rid}")
        if len(uncovered_ids) > 25:
            lines.append(f"  +{len(uncovered_ids) - 25} more uncovered")
    return "\n".join(lines)


def _render_coverage_html(payload: dict) -> str:
    totals = payload.get("totals") or {}
    files = payload.get("files") or {}
    rows = []
    valid_items = [(p, e) for p, e in files.items() if isinstance(e, dict)]
    for path, entry in sorted(
        valid_items, key=lambda kv: float(kv[1].get("percent", 100.0))
    ):
        rows.append(
            "<tr><td>{p}</td><td>{pct:.2f}%</td><td>{c}/{t}</td></tr>".format(
                p=path,
                pct=float(entry.get("percent", 0.0)),
                c=int(entry.get("covered_lines", 0)),
                t=int(entry.get("total_lines", 0)),
            )
        )
    return (
        "<!doctype html><meta charset='utf-8'><title>playwright-god coverage</title>"
        "<style>body{font-family:sans-serif;margin:2em}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:4px 8px}</style>"
        f"<h1>Coverage report ({payload.get('source', '?')})</h1>"
        f"<p>Overall: {totals.get('percent', 0.0)}% — "
        f"{totals.get('covered_lines', 0)}/{totals.get('total_lines', 0)} lines, "
        f"{totals.get('total_files', len(files))} files.</p>"
        "<table><tr><th>File</th><th>Percent</th><th>Covered/Total</th></tr>"
        + "".join(rows)
        + "</table>"
        + _render_coverage_routes_html(payload)
    )


def _render_coverage_routes_html(payload: dict) -> str:
    routes = payload.get("routes") or {}
    if not isinstance(routes, dict) or not routes:
        return ""
    covered_ids = list(routes.get("covered") or [])
    uncovered_ids = list(routes.get("uncovered") or [])
    total = int(routes.get("total") or (len(covered_ids) + len(uncovered_ids)))
    rows = "".join(
        f"<tr><td>{rid}</td><td>covered</td></tr>" for rid in covered_ids
    ) + "".join(
        f"<tr><td>{rid}</td><td>uncovered</td></tr>" for rid in uncovered_ids
    )
    return (
        f"<h2>Routes ({len(covered_ids)}/{total})</h2>"
        "<table><tr><th>Route</th><th>Status</th></tr>"
        + rows
        + "</table>"
    )


# ---------------------------------------------------------------------------
# `refine` subcommand (iterative-refinement)
# ---------------------------------------------------------------------------


@cli.command(name="refine")
@click.argument("description")
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(dir_okay=False),
    help="Path for the final spec file (overwritten on every attempt).",
)
@click.option(
    "--persist-dir",
    "-d",
    default=".playwright_god_index",
    show_default=True,
)
@click.option("--collection", "-c", default="repo", show_default=True)
@click.option(
    "--memory-map",
    "-m",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.option(
    "--target-dir",
    default=None,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--artifact-dir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Root directory for per-run artifacts and the refinement audit log.",
)
@click.option(
    "--max-attempts",
    default=3,
    show_default=True,
    type=int,
    help="Maximum generate→run cycles (hard cap: 8).",
)
@click.option(
    "--stop-on",
    type=click.Choice(["passed", "covered", "stable"], case_sensitive=False),
    default="passed",
    show_default=True,
)
@click.option("--coverage-target", default=0.95, show_default=True, type=float)
@click.option("--retry-on-flake", default=0, show_default=True, type=int)
@click.option(
    "--provider",
    default=None,
    type=click.Choice(
        ["openai", "anthropic", "gemini", "ollama", "template"],
        case_sensitive=False,
    ),
)
@click.option("--model", default=None)
@click.option("--api-key", default=None)
@click.option("--ollama-url", default="http://localhost:11434", show_default=True)
@click.option("--mock-embedder", is_flag=True, default=False, hidden=True)
def refine(
    description: str,
    output: str,
    persist_dir: str,
    collection: str,
    memory_map: str | None,
    target_dir: str | None,
    artifact_dir: str | None,
    max_attempts: int,
    stop_on: str,
    coverage_target: float,
    retry_on_flake: int,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    ollama_url: str,
    mock_embedder: bool,
) -> None:
    """Iteratively generate, run, and refine a spec until it passes (or the cap is hit)."""

    from .refinement import (
        HIGH_ATTEMPT_WARN_THRESHOLD,
        MAX_ATTEMPTS_HARD_CAP,
        RefinementConfigError,
        RefinementLoop,
    )

    if max_attempts > MAX_ATTEMPTS_HARD_CAP:
        click.echo(
            f"Error: --max-attempts {max_attempts} exceeds the hard cap of "
            f"{MAX_ATTEMPTS_HARD_CAP}.",
            err=True,
        )
        sys.exit(2)
    if max_attempts > HIGH_ATTEMPT_WARN_THRESHOLD:
        click.echo(
            f"Warning: high attempt cap ({max_attempts}); LLM cost grows linearly. "
            "Consider --max-attempts <= 5.",
            err=True,
        )

    provider, model, api_key, ollama_url = _resolve_provider_config(
        provider, model, api_key, ollama_url
    )
    from .embedder import MockEmbedder as _MockEmbedder

    embedder = _MockEmbedder() if mock_embedder else DefaultEmbedder()
    indexer = RepositoryIndexer(
        collection_name=collection,
        persist_dir=persist_dir,
        embedder=embedder,
    )

    if provider == "openai":
        llm_client = OpenAIClient(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            model=model or "gpt-4o",
        )
    elif provider == "anthropic":
        llm_client = AnthropicClient(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            model=model or "claude-3-5-sonnet-20241022",
        )
    elif provider == "gemini":
        llm_client = GeminiClient(
            api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""),
            model=model or "gemini-1.5-pro",
        )
    elif provider == "ollama":
        llm_client = OllamaClient(model=model or "llama3", base_url=ollama_url)
    else:
        llm_client = TemplateLLMClient()

    generator = PlaywrightTestGenerator(llm_client=llm_client, indexer=indexer)

    extra_context: str | None = None
    if memory_map:
        try:
            map_data = load_memory_map(memory_map)
            extra_context = format_memory_map_for_prompt(map_data)
        except (FileNotFoundError, ValueError) as exc:
            click.echo(f"Warning: could not load --memory-map {memory_map!r}: {exc}", err=True)

    runner = PlaywrightRunner(target_dir=target_dir, artifact_dir=artifact_dir)
    log_dir = Path(artifact_dir) if artifact_dir else None

    try:
        loop = RefinementLoop(
            generator=generator,
            runner=runner,
            spec_path=Path(output),
            max_attempts=max_attempts,
            stop_on=stop_on.lower(),  # type: ignore[arg-type]
            coverage_target=coverage_target,
            retry_on_flake=retry_on_flake,
            log_dir=log_dir,
            generator_kwargs=({"extra_context": extra_context} if extra_context else {}),
        )
    except RefinementConfigError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    try:
        result = loop.run(description)
    except RunnerSetupError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    click.echo(
        f"Refinement: {len(result.attempts)} attempt(s); "
        f"final outcome={result.final_outcome}; stop_reason={result.stop_reason}; "
        f"final spec={result.final_spec_path}",
        err=True,
    )
    if result.log_path is not None:
        click.echo(f"Audit log: {result.log_path}", err=True)

    sys.exit(0 if result.final_outcome == "passed" else 1)


# ---------------------------------------------------------------------------
# `graph` subcommand group (flow-graph extraction)
# ---------------------------------------------------------------------------


def _load_flow_graph(path: str):
    """Load a serialized FlowGraph; exits the CLI on failure."""

    from .flow_graph import FlowGraph

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        click.echo(f"Error: could not load flow graph {path!r}: {exc}", err=True)
        sys.exit(1)
    return FlowGraph.from_dict(data)


@cli.group(name="graph")
def graph_group() -> None:
    """Flow-graph extraction commands."""


@graph_group.command(name="extract")
@click.argument(
    "source_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--output",
    "-o",
    "output_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="Where to write flow_graph.json (default: <persist-dir>/flow_graph.json).",
)
@click.option(
    "--persist-dir",
    "-d",
    default=".playwright_god_index",
    show_default=True,
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help=(
        "Compare the freshly extracted graph against the persisted one and "
        "exit non-zero on drift (prints a unified ID diff)."
    ),
)
def graph_extract(
    source_path: str,
    output_path: str | None,
    persist_dir: str,
    check: bool,
) -> None:
    """Run extractors on SOURCE_PATH and write a flow_graph.json artifact."""

    from .extractors import extract as _extract
    from .flow_graph import FlowGraph

    graph = _extract(source_path)
    target = Path(output_path) if output_path else Path(persist_dir) / "flow_graph.json"

    if check:
        if not target.is_file():
            click.echo(
                f"Error: --check requires an existing graph at {target}.",
                err=True,
            )
            sys.exit(2)
        try:
            persisted = FlowGraph.from_dict(
                json.loads(target.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError) as exc:
            click.echo(f"Error: could not load {target}: {exc}", err=True)
            sys.exit(2)
        diff = _flow_graph_id_diff(persisted, graph)
        if diff:
            click.echo("Flow graph drift detected:")
            click.echo(diff)
            sys.exit(1)
        click.echo(
            f"Flow graph up to date: {len(graph.routes)} routes, "
            f"{len(graph.views)} views, {len(graph.actions)} actions."
        )
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(graph.to_json() + "\n", encoding="utf-8")
    click.echo(
        f"{len(graph.routes)} routes, {len(graph.views)} views, "
        f"{len(graph.actions)} actions written to {target}"
    )


def _flow_graph_id_diff(old, new) -> str:
    """Return a unified diff of node IDs between two graphs (empty if equal)."""

    import difflib

    old_ids = sorted(old.node_ids())
    new_ids = sorted(new.node_ids())
    if old_ids == new_ids:
        return ""
    diff = difflib.unified_diff(
        [i + "\n" for i in old_ids],
        [i + "\n" for i in new_ids],
        fromfile="persisted",
        tofile="extracted",
        lineterm="",
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# update command
# ---------------------------------------------------------------------------


@cli.command(name="update")
@click.option(
    "--spec-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("tests"),
    help="Directory containing Playwright spec files",
)
@click.option(
    "--persist-dir",
    "-d",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path(".playwright_god_index"),
    help="Directory for persisted artifacts (index, spec_index.json, update_plan.json)",
)
@click.option(
    "--flow-graph",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to flow_graph.json (or extract from persist-dir)",
)
@click.option(
    "--artifact-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory containing prior run artifacts for outcome lookup",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the plan without executing any refinement",
)
@click.option(
    "--strict-update",
    is_flag=True,
    default=False,
    help="Gate updates on coverage parity (reject specs that regress coverage)",
)
@click.option(
    "--allow-dirty",
    is_flag=True,
    default=False,
    help="Allow running with unstaged changes to spec files",
)
def update_command(
    spec_dir: Path,
    persist_dir: Path,
    flow_graph: Path | None,
    artifact_dir: Path | None,
    dry_run: bool,
    strict_update: bool,
    allow_dirty: bool,
) -> None:
    """Update existing Playwright specs based on flow graph changes.

    Builds an UpdatePlan by comparing the current FlowGraph against the
    SpecIndex and executes add/update operations via RefinementLoop.

    \b
    Workflow:
      1. Index existing specs in --spec-dir to build a SpecIndex
      2. Load or extract the current FlowGraph
      3. Diff graph vs index to produce an UpdatePlan (add/update/keep/review)
      4. Execute the plan (unless --dry-run)
      5. Print a per-bucket summary
    """
    from .flow_graph import FlowGraph
    from .spec_index import SpecIndex
    from .update_planner import DiffPlanner, UpdatePlan, load_prior_outcomes

    # Check for dirty spec files
    if not allow_dirty:
        dirty_files = _check_dirty_specs(spec_dir)
        if dirty_files:
            click.echo("Error: Dirty (unstaged) spec files detected:", err=True)
            for f in dirty_files[:10]:
                click.echo(f"  {f}", err=True)
            if len(dirty_files) > 10:
                click.echo(f"  ... and {len(dirty_files) - 10} more", err=True)
            click.echo(
                "\nCommit or stash changes before running update, "
                "or pass --allow-dirty to override.",
                err=True,
            )
            sys.exit(1)

    # Load flow graph
    fg: FlowGraph
    if flow_graph is not None:
        fg = _load_flow_graph(flow_graph)
    else:
        fg_path = persist_dir / "flow_graph.json"
        if fg_path.exists():
            fg = _load_flow_graph(fg_path)
        else:
            # Extract from current directory
            from . import extractors
            click.echo("Extracting flow graph from current directory...")
            fg = extractors.extract(Path("."))

    # Build spec index
    cache_path = persist_dir / "spec_index.json"
    click.echo(f"Indexing specs in {spec_dir}...")
    spec_index = SpecIndex.build(spec_dir, cache_path=cache_path, flow_graph=fg)
    click.echo(f"  Found {len(spec_index)} spec files")

    # Attach spec index to graph for covering_specs
    fg.attach_spec_index(spec_index)

    # Load prior outcomes
    prior_outcomes: dict[str, str] = {}
    if artifact_dir is not None:
        prior_outcomes = load_prior_outcomes(artifact_dir)
        click.echo(f"  Loaded {len(prior_outcomes)} prior run outcomes")

    # Build the plan
    planner = DiffPlanner(
        flow_graph=fg,
        spec_index=spec_index,
        prior_outcomes=prior_outcomes,
    )
    plan = planner.plan()

    # Save the plan
    persist_dir.mkdir(parents=True, exist_ok=True)
    plan_path = persist_dir / "update_plan.json"
    plan.save(plan_path)
    click.echo(f"\nUpdate plan saved to {plan_path}")

    # Print summary
    summary = plan.summary()
    click.echo("\n" + "=" * 60)
    click.echo("Update Plan Summary")
    click.echo("=" * 60)
    click.echo(f"  add:    {summary['add']} (new specs to generate)")
    click.echo(f"  update: {summary['update']} (existing specs to regenerate)")
    click.echo(f"  keep:   {summary['keep']} (unchanged)")
    click.echo(f"  review: {summary['review']} (need human review)")

    if dry_run:
        click.echo("\n--dry-run: No specs will be modified.")
        _print_plan_details(plan)
        return

    if plan.is_empty():
        click.echo("\nNothing to do - all specs are up to date.")
        return

    # Execute the plan
    click.echo("\n" + "=" * 60)
    click.echo("Executing Update Plan")
    click.echo("=" * 60)

    executed_add = 0
    executed_update = 0
    failed: list[str] = []

    # Process add entries
    for entry in plan.add:
        click.echo(f"\n[ADD] {entry.node_id}")
        try:
            _execute_add(entry, spec_dir, persist_dir, strict_update)
            executed_add += 1
        except Exception as e:
            click.echo(f"  FAILED: {e}", err=True)
            failed.append(f"add:{entry.node_id}")

    # Process update entries
    for entry in plan.update:
        click.echo(f"\n[UPDATE] {entry.spec_path}")
        try:
            _execute_update(entry, spec_dir, persist_dir, strict_update)
            executed_update += 1
        except Exception as e:
            click.echo(f"  FAILED: {e}", err=True)
            failed.append(f"update:{entry.spec_path}")

    # Final summary
    click.echo("\n" + "=" * 60)
    click.echo("Execution Complete")
    click.echo("=" * 60)
    click.echo(f"  Added:   {executed_add}/{summary['add']}")
    click.echo(f"  Updated: {executed_update}/{summary['update']}")
    if failed:
        click.echo(f"  Failed:  {len(failed)}")
        for f in failed:
            click.echo(f"    - {f}")
        sys.exit(1)


def _check_dirty_specs(spec_dir: Path) -> list[str]:
    """Check for unstaged changes to spec files in a git repository."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", str(spec_dir)],
            capture_output=True,
            text=True,
            cwd=spec_dir.parent if spec_dir.exists() else Path.cwd(),
        )
        if result.returncode != 0:
            return []  # Not a git repo or git not available
        dirty = []
        for line in result.stdout.splitlines():
            if line and not line.startswith(" ") and ".spec.ts" in line:
                # Has unstaged changes (first char is not space)
                dirty.append(line[3:].strip())
        return dirty
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _print_plan_details(plan) -> None:
    """Print detailed plan entries."""
    if plan.add:
        click.echo("\nAdd (generate new specs):")
        for e in plan.add[:20]:
            click.echo(f"  + {e.node_id}: {e.reason}")
        if len(plan.add) > 20:
            click.echo(f"  ... and {len(plan.add) - 20} more")

    if plan.update:
        click.echo("\nUpdate (regenerate existing):")
        for e in plan.update[:20]:
            click.echo(f"  ~ {e.spec_path}: {e.reason}")
        if len(plan.update) > 20:
            click.echo(f"  ... and {len(plan.update) - 20} more")

    if plan.review:
        click.echo("\nReview (needs human attention):")
        for e in plan.review[:20]:
            click.echo(f"  ? {e.spec_path or e.node_id}: {e.reason}")
        if len(plan.review) > 20:
            click.echo(f"  ... and {len(plan.review) - 20} more")


def _execute_add(entry, spec_dir: Path, persist_dir: Path, strict_update: bool) -> None:
    """Execute an ADD plan entry by generating a new spec."""
    # For now, just log - full implementation requires RefinementLoop integration
    click.echo(f"  Generating spec for {entry.node_id}...")
    click.echo(f"  (Full RefinementLoop integration pending)")


def _execute_update(entry, spec_dir: Path, persist_dir: Path, strict_update: bool) -> None:
    """Execute an UPDATE plan entry by refining an existing spec."""
    # For now, just log - full implementation requires RefinementLoop integration
    click.echo(f"  Refining {entry.spec_path}...")
    click.echo(f"  (Full RefinementLoop integration pending)")


def main() -> None:
    """Entry point for the ``playwright-god`` CLI command."""
    cli()
