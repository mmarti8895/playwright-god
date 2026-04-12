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
from .feature_map import RepositoryFeatureMap


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_memory_map(
    chunks: Sequence[Chunk],
    repository_feature_map: RepositoryFeatureMap | dict | None = None,
) -> dict:
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

    memory_map = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(files),
        "total_chunks": len(chunks),
        "languages": dict(lang_count),
        "files": files,
    }
    if repository_feature_map is not None:
        memory_map.update(_feature_map_payload(repository_feature_map))
    return memory_map


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
    _languages = memory_map.get("languages", {})
    languages: dict = _languages if isinstance(_languages, dict) else {}
    _files = memory_map.get("files", [])
    files: list = _files if isinstance(_files, list) else []

    valid_languages: list[tuple[str, int]] = []
    for lang, count in languages.items():
        try:
            valid_languages.append((lang, int(count)))
        except (TypeError, ValueError):
            continue

    lang_summary = ", ".join(
        f"{lang} ({count})"
        for lang, count in sorted(valid_languages, key=lambda kv: -kv[1])
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
        if not isinstance(file_entry, dict):
            continue
        path = file_entry.get("path", "?")
        language = file_entry.get("language", "unknown")
        chunks = file_entry.get("chunks", [])
        range_parts = [
            f"{c.get('start_line', '?')}-{c.get('end_line', '?')}"
            for c in chunks
            if isinstance(c, dict)
        ]
        ranges = ", ".join(range_parts) if range_parts else "(no chunks)"
        lines.append(f"{path}  [{language}]")
        lines.append(f"  lines {ranges}")

    feature_lines = _format_feature_sections(memory_map)
    if feature_lines:
        lines.extend(["", *feature_lines])

    return "\n".join(lines)


def _feature_map_payload(repository_feature_map: RepositoryFeatureMap | dict) -> dict[str, object]:
    if isinstance(repository_feature_map, RepositoryFeatureMap):
        payload = repository_feature_map.to_dict()
    else:
        payload = dict(repository_feature_map)
    return {
        "schema_version": payload.get("schema_version", "2.0"),
        "features": payload.get("features", []),
        "correlations": payload.get("correlations", []),
        "test_opportunities": payload.get("test_opportunities", []),
        "source_root": payload.get("source_root", "."),
    }


def _format_feature_sections(memory_map: dict) -> list[str]:
    feature_lines: list[str] = []
    features = memory_map.get("features", [])
    correlations = memory_map.get("correlations", [])
    opportunities = memory_map.get("test_opportunities", [])

    if isinstance(features, list) and features:
        feature_lines.extend(["Feature areas", "-------------"])
        for feature in features[:6]:
            if not isinstance(feature, dict):
                continue
            name = feature.get("name", feature.get("feature_id", "unknown"))
            confidence = feature.get("confidence", "?")
            summary = feature.get("summary", "")
            artifacts = feature.get("artifacts", [])
            evidence_paths = ", ".join(
                artifact.get("file_path", "?")
                for artifact in artifacts[:3]
                if isinstance(artifact, dict)
            )
            feature_lines.append(f"{name} [{confidence}]")
            if summary:
                feature_lines.append(f"  {summary}")
            if evidence_paths:
                feature_lines.append(f"  evidence: {evidence_paths}")

    if isinstance(correlations, list) and correlations:
        if feature_lines:
            feature_lines.append("")
        feature_lines.extend(["Feature correlations", "--------------------"])
        for correlation in correlations[:6]:
            if not isinstance(correlation, dict):
                continue
            source = correlation.get("source_feature_id", "?")
            target = correlation.get("target_feature_id", "?")
            relation = correlation.get("relationship_type", "related")
            feature_lines.append(f"{source} -> {target} [{relation}]")

    if isinstance(opportunities, list) and opportunities:
        if feature_lines:
            feature_lines.append("")
        feature_lines.extend(["Suggested test opportunities", "----------------------------"])
        for opportunity in opportunities[:8]:
            if not isinstance(opportunity, dict):
                continue
            title = opportunity.get("title", "Unknown scenario")
            feature_id = opportunity.get("feature_id", "?")
            confidence = opportunity.get("confidence", "?")
            feature_lines.append(f"{feature_id}: {title} [{confidence}]")

    return feature_lines
