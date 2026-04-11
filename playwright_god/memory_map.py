"""Memory map: a structured JSON snapshot of the indexed chunk inventory.

A *memory map* records every file that has been chunked and indexed, along
with the line ranges of each chunk.  It is a compact, human-readable (and
LLM-readable) manifest that can be:

* Saved alongside the vector index (``playwright-god index --memory-map``).
* Loaded and injected into a generation prompt so the AI understands the full
  scope of the indexed codebase without re-sending every chunk's text
  (``playwright-god generate --memory-map``).
* Summarised into a test plan by the AI (``playwright-god plan``).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .chunker import Chunk


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_memory_map(chunks: Sequence[Chunk]) -> dict:
    """Build a memory map dict from a sequence of :class:`~playwright_god.chunker.Chunk` objects.

    Parameters
    ----------
    chunks:
        All chunks that were indexed (output of
        :meth:`~playwright_god.chunker.FileChunker.chunk_files`).

    Returns
    -------
    dict
        A serialisable dict with the following structure::

            {
                "generated_at": "<ISO-8601 timestamp>",
                "total_files": <int>,
                "total_chunks": <int>,
                "languages": {"typescript": 12, "python": 8, ...},
                "files": [
                    {
                        "path": "src/auth.ts",
                        "language": "typescript",
                        "chunks": [
                            {"chunk_id": "abc123", "start_line": 1, "end_line": 80},
                            ...
                        ]
                    },
                    ...
                ]
            }
    """
    # Group chunks by file path
    by_file: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        by_file[chunk.file_path].append(chunk)

    # Language frequency counter
    lang_count: dict[str, int] = defaultdict(int)

    files: list[dict] = []
    for path in sorted(by_file.keys()):
        file_chunks = sorted(by_file[path], key=lambda c: c.start_line)
        language = file_chunks[0].language if file_chunks else "unknown"
        lang_count[language] += 1
        files.append(
            {
                "path": path,
                "language": language,
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                    }
                    for c in file_chunks
                ],
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(files),
        "total_chunks": len(chunks),
        "languages": dict(lang_count),
        "files": files,
    }


def save_memory_map(memory_map: dict, path: str) -> None:
    """Serialise *memory_map* to a JSON file at *path*.

    Parent directories are created automatically.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(memory_map, indent=2), encoding="utf-8")


def load_memory_map(path: str) -> dict:
    """Load and return a memory map from the JSON file at *path*.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file cannot be decoded as JSON.
    """
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Memory map not found: {path!r}")
    try:
        return json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in memory map {path!r}: {exc}") from exc


def format_memory_map_for_prompt(memory_map: dict) -> str:
    """Return a compact, human-readable summary of *memory_map* for LLM prompts.

    The summary intentionally omits chunk IDs (not useful to an LLM) and
    presents the file tree with line-range annotations so the model knows
    which portions of each file are indexed.

    Example output::

        Indexed codebase memory map
        ===========================
        Total files : 5
        Total chunks: 42
        Languages   : typescript (3), python (2)

        File index
        ----------
        src/auth.ts  [typescript]
          lines 1-80, 71-150, 141-180
        src/login.ts  [typescript]
          lines 1-80
        ...
    """
    total_files = memory_map.get("total_files", 0)
    total_chunks = memory_map.get("total_chunks", 0)
    languages = memory_map.get("languages", {})
    files = memory_map.get("files", [])

    lang_summary = ", ".join(
        f"{lang} ({count})"
        for lang, count in sorted(languages.items(), key=lambda kv: -kv[1])
    )

    lines: list[str] = [
        "Indexed codebase memory map",
        "===========================",
        f"Total files : {total_files}",
        f"Total chunks: {total_chunks}",
        f"Languages   : {lang_summary or 'n/a'}",
        "",
        "File index",
        "----------",
    ]

    for file_entry in files:
        path = file_entry.get("path", "?")
        language = file_entry.get("language", "unknown")
        chunks = file_entry.get("chunks", [])
        range_parts = [f"{c['start_line']}-{c['end_line']}" for c in chunks]
        ranges = ", ".join(range_parts) if range_parts else "(no chunks)"
        lines.append(f"{path}  [{language}]")
        lines.append(f"  lines {ranges}")

    return "\n".join(lines)
