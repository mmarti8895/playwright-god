"""Command-line interface for playwright-god."""

from __future__ import annotations

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
    mock_embedder: bool,
) -> None:
    """Crawl REPO_PATH and build a vector index for test generation.

    REPO_PATH defaults to the current directory.
    """
    click.echo(f"Crawling repository: {os.path.abspath(repo_path)}")
    crawler = RepositoryCrawler()
    files = crawler.crawl(repo_path)
    click.echo(f"  Found {len(files)} files")

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

    generator = PlaywrightTestGenerator(
        llm_client=llm_client,
        indexer=indexer,
        n_context=n_context,
    )

    click.echo(f"Generating test for: {description!r}", err=True)
    test_code = generator.generate(description)

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(test_code)
        click.echo(f"Test written to: {output}", err=True)
    else:
        click.echo(test_code)


def main() -> None:
    """Entry point for the ``playwright-god`` CLI command."""
    cli()
