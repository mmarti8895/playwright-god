"""Command-line interface for playwright-god."""

from __future__ import annotations

import os
import sys

import click

from .crawler import RepositoryCrawler
from .chunker import FileChunker
from .embedder import DefaultEmbedder
from .generator import OpenAIClient, PlaywrightTestGenerator, TemplateLLMClient
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
    default="gpt-4o",
    show_default=True,
    help="OpenAI model to use (ignored if OPENAI_API_KEY is not set).",
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
    model: str,
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

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        click.echo(f"Using OpenAI model: {model}", err=True)
        llm_client = OpenAIClient(api_key=api_key, model=model)
    else:
        click.echo(
            "OPENAI_API_KEY not set – using offline template generator.",
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
