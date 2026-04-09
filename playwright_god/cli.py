"""Command-line interface for playwright-god."""

from __future__ import annotations

import json
import os
import sys

import click

from .crawler import RepositoryCrawler
from .chunker import FileChunker
from .embedder import DefaultEmbedder
from .generator import (
    AnthropicClient,
    GeminiClient,
    OllamaClient,
    OpenAIClient,
    PlaywrightTestGenerator,
    TemplateLLMClient,
)
from .indexer import RepositoryIndexer


@click.group()
@click.version_option()
def cli() -> None:
    """Playwright God – AI-powered Playwright test generator.

    \b
    Workflow:
      1. playwright-god index <repo-path>   # index the repository
      2. playwright-god generate "..."      # generate a test
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
        "(e.g. IdP metadata XML, SAML config).  May be specified multiple times."
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
    mock_embedder: bool,
) -> None:
    """Crawl REPO_PATH and build a vector index for test generation.

    REPO_PATH defaults to the current directory.
    """
    from pathlib import Path
    from .crawler import FileInfo

    click.echo(f"Crawling repository: {os.path.abspath(repo_path)}")
    crawler = RepositoryCrawler()
    files = crawler.crawl(repo_path)
    click.echo(f"  Found {len(files)} files")

    # Append any manually specified extra files (e.g. IdP metadata, SAML config).
    for extra_path in extra_files:
        p = Path(extra_path).resolve()
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            lang = crawler._detect_language(p)
            files.append(
                FileInfo(
                    path=str(p),
                    absolute_path=str(p),
                    content=content,
                    language=lang,
                    size=len(content.encode("utf-8")),
                )
            )
            click.echo(f"  Added extra file: {p} ({lang})")
        except OSError as exc:
            click.echo(f"  Warning: could not read {extra_path!r}: {exc}", err=True)

    if not files:
        click.echo("  No files found – nothing to index.", err=True)
        sys.exit(1)

    click.echo("Building structure summary …")
    summary = crawler.build_structure_summary(files)
    click.echo(summary)

    click.echo("Chunking files …")
    chunker = FileChunker(chunk_size=chunk_size, overlap=overlap)
    chunks = chunker.chunk_files(files)
    click.echo(f"  Created {len(chunks)} chunks")

    click.echo("Embedding and indexing …")
    from .embedder import MockEmbedder as _MockEmbedder
    embedder = _MockEmbedder() if mock_embedder else DefaultEmbedder()
    indexer = RepositoryIndexer(
        collection_name=collection,
        persist_dir=persist_dir,
        embedder=embedder,
    )
    indexer.add_chunks(chunks)
    click.echo(f"  Index saved to: {persist_dir!r}  ({indexer.count()} vectors)")
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
    type=click.Path(),
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
        ["openai", "anthropic", "gemini", "ollama", "template"],
        case_sensitive=False,
    ),
    help=(
        "LLM provider to use.  Auto-detected from environment variables when "
        "not set (OPENAI_API_KEY → openai, ANTHROPIC_API_KEY → anthropic, "
        "GOOGLE_API_KEY → gemini).  Falls back to the offline template "
        "generator when no key is found."
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
    "--auth-type",
    default=None,
    type=click.Choice(
        ["saml", "ntlm", "oidc", "basic", "logging", "none"],
        case_sensitive=False,
    ),
    help=(
        "Authentication mechanism used by the system under test.  Injects "
        "the relevant auth hint and TypeScript template snippet into the prompt "
        "so the LLM produces correct auth/logging test code.  "
        "Choices: saml, ntlm, oidc, basic, logging, none."
    ),
)
@click.option(
    "--auth-config",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a JSON or YAML file with non-secret auth metadata "
        "(e.g. IdP URL, SP entity ID, callback URL, LDAP domain).  "
        "Its contents are appended to the prompt as extra context."
    ),
)
@click.option(
    "--env-file",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help=(
        "Path to a .env file listing the credential environment-variable "
        "names used by the test suite (e.g. TEST_USERNAME, TEST_PASSWORD).  "
        "Only the variable *names* are forwarded to the prompt — values are "
        "never included."
    ),
)
@click.option(
    "--redact-secrets/--no-redact-secrets",
    default=True,
    show_default=True,
    help=(
        "Replace hardcoded credential literals in the generated output with "
        "process.env.* placeholders (enabled by default)."
    ),
)
@click.option(
    "--mock-embedder",
    is_flag=True,
    default=False,
    hidden=True,
    help="Use the deterministic mock embedder (for testing without network access).",
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
    auth_type: str | None,
    auth_config: str | None,
    env_file: str | None,
    redact_secrets: bool,
    mock_embedder: bool,
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

    # Auto-detect provider from environment when not explicitly specified
    if provider is None:
        if api_key or os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("GOOGLE_API_KEY"):
            provider = "gemini"
        else:
            provider = "template"

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
            "No LLM provider detected – using offline template generator.",
            err=True,
        )
        llm_client = TemplateLLMClient()

    # Build extra_context from --auth-config and --env-file
    extra_parts: list[str] = []

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
                    + "\n".join(f"  process.env.{n}" for n in env_var_names)
                )
        except OSError as exc:
            click.echo(f"Warning: could not read --env-file {env_file!r}: {exc}", err=True)

    extra_context: str | None = "\n\n".join(extra_parts) if extra_parts else None

    generator = PlaywrightTestGenerator(
        llm_client=llm_client,
        indexer=indexer,
        n_context=n_context,
    )

    click.echo(f"Generating test for: {description!r}", err=True)
    if auth_type:
        click.echo(f"Auth type: {auth_type}", err=True)

    test_code = generator.generate(
        description,
        extra_context=extra_context,
        auth_type=auth_type,
        redact_secrets=redact_secrets,
    )

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(test_code)
        click.echo(f"Test written to: {output}", err=True)
    else:
        click.echo(test_code)


def main() -> None:
    """Entry point for the ``playwright-god`` CLI command."""
    cli()
