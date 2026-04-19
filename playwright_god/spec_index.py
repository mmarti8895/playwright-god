"""SpecIndex: maps existing Playwright specs to FlowGraph node IDs.

The index scans a directory of `.spec.ts` files and determines which
flow-graph nodes (routes, views, actions) each spec exercises. Two signals
drive the mapping:

1. **Explicit `@pg-tags`** at the top of a spec — authoritative.
2. **Heuristic extraction** of `page.goto(...)` URLs and selectors — fallback.

The index is cached by content hash to `<persist-dir>/spec_index.json`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

__all__ = [
    "SpecEntry",
    "SpecIndex",
    "parse_pg_tags",
    "extract_heuristic_node_ids",
]

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpecEntry:
    """A single indexed spec file."""

    path: str
    """Relative path to the spec file."""

    node_ids: tuple[str, ...]
    """Flow-graph node IDs this spec exercises (from tags or heuristics)."""

    content_hash: str
    """SHA-256 of the spec file content (for cache invalidation)."""

    pinned: bool = False
    """True if the spec contains `@pg-pin`."""

    tag_source: bool = False
    """True if node_ids came from explicit @pg-tags (authoritative)."""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "node_ids": list(self.node_ids),
            "content_hash": self.content_hash,
            "pinned": self.pinned,
            "tag_source": self.tag_source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SpecEntry:
        return cls(
            path=data["path"],
            node_ids=tuple(data.get("node_ids", [])),
            content_hash=data.get("content_hash", ""),
            pinned=data.get("pinned", False),
            tag_source=data.get("tag_source", False),
        )


@dataclass
class SpecIndex:
    """Index of Playwright specs mapped to flow-graph node IDs."""

    entries: dict[str, SpecEntry] = field(default_factory=dict)
    """Mapping from spec path to SpecEntry."""

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries.values())

    def get(self, path: str) -> SpecEntry | None:
        return self.entries.get(path)

    def specs_covering(self, node_id: str) -> list[str]:
        """Return all spec paths that cover the given node ID."""
        return [
            e.path for e in self.entries.values() if node_id in e.node_ids
        ]

    def to_dict(self) -> dict:
        return {
            "version": "1.0",
            "entries": [e.to_dict() for e in self.entries.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SpecIndex:
        entries = {
            e["path"]: SpecEntry.from_dict(e)
            for e in data.get("entries", [])
        }
        return cls(entries=entries)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> SpecIndex:
        return cls.from_dict(json.loads(text))

    # -----------------------------------------------------------------------
    # Building
    # -----------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        spec_dir: Path,
        *,
        cache_path: Path | None = None,
        flow_graph=None,
    ) -> SpecIndex:
        """Build an index by scanning spec files in *spec_dir*.

        If *cache_path* is provided, specs whose content hash matches the
        cached entry are not re-parsed. The cache is written after building.

        *flow_graph* is optional and used by heuristic matching to validate
        extracted node IDs against the graph.
        """
        cached = _load_cache(cache_path)
        entries: dict[str, SpecEntry] = {}

        spec_files = list(spec_dir.rglob("*.spec.ts"))
        for spec_path in spec_files:
            try:
                content = spec_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            rel = str(spec_path.relative_to(spec_dir))
            content_hash = _hash_content(content)

            # Cache hit?
            if rel in cached and cached[rel].content_hash == content_hash:
                entries[rel] = cached[rel]
                continue

            # Parse the spec
            entry = _parse_spec(rel, content, content_hash, flow_graph)
            entries[rel] = entry

        index = cls(entries=entries)
        if cache_path is not None:
            _save_cache(cache_path, index)
        return index


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_PG_TAGS_RE = re.compile(r"//\s*@pg-tags\s+(.+)", re.IGNORECASE)
_PG_PIN_RE = re.compile(r"//\s*@pg-pin\b", re.IGNORECASE)
_NODE_ID_RE = re.compile(r"(?:route|view|action):[^\s]+", re.IGNORECASE)


def parse_pg_tags(content: str) -> tuple[list[str], bool]:
    """Parse @pg-tags and @pg-pin from spec content.

    Returns (node_ids, pinned).
    """
    node_ids: list[str] = []
    pinned = False

    for line in content.splitlines()[:20]:  # Only scan first 20 lines
        stripped = line.strip()
        if not stripped:
            continue
        if _PG_PIN_RE.search(stripped):
            pinned = True
        match = _PG_TAGS_RE.search(stripped)
        if match:
            tag_text = match.group(1)
            node_ids.extend(_NODE_ID_RE.findall(tag_text))

    return node_ids, pinned


def extract_heuristic_node_ids(
    content: str,
    flow_graph=None,
) -> list[str]:
    """Extract node IDs heuristically from spec content.

    Looks for:
    - `page.goto("/path")` → route:GET:/path
    - `page.goto(baseURL + "/path")` → route:GET:/path
    - URL patterns in navigation calls

    If *flow_graph* is provided, validates IDs against the graph.
    """
    node_ids: list[str] = []

    # Pattern: page.goto("/path") or page.goto('/path') or page.goto(`/path`)
    goto_pattern = re.compile(
        r'page\.goto\s*\(\s*["`\']([^"`\']+)["`\']',
        re.IGNORECASE,
    )
    for match in goto_pattern.finditer(content):
        path = match.group(1)
        if path.startswith("/"):
            node_id = f"route:GET:{path}"
            node_ids.append(node_id)

    # Pattern: page.goto(baseURL + "/path") or similar concatenations
    concat_pattern = re.compile(
        r'page\.goto\s*\([^)]*[+]\s*["`\']([^"`\']+)["`\']',
        re.IGNORECASE,
    )
    for match in concat_pattern.finditer(content):
        path = match.group(1)
        if path.startswith("/"):
            node_id = f"route:GET:{path}"
            if node_id not in node_ids:
                node_ids.append(node_id)

    # If flow_graph provided, filter to valid IDs
    if flow_graph is not None:
        valid_ids = {n.id for n in getattr(flow_graph, "nodes", [])}
        node_ids = [nid for nid in node_ids if nid in valid_ids]

    return node_ids


def _parse_spec(
    rel: str,
    content: str,
    content_hash: str,
    flow_graph=None,
) -> SpecEntry:
    """Parse a single spec file and return a SpecEntry."""
    tag_ids, pinned = parse_pg_tags(content)

    if tag_ids:
        # Tags are authoritative
        heuristic_ids = extract_heuristic_node_ids(content, flow_graph)
        # Log divergence at debug level
        if heuristic_ids and set(heuristic_ids) != set(tag_ids):
            _log.debug(
                "spec %s: @pg-tags %r diverge from heuristic %r; using tags",
                rel,
                tag_ids,
                heuristic_ids,
            )
        return SpecEntry(
            path=rel,
            node_ids=tuple(tag_ids),
            content_hash=content_hash,
            pinned=pinned,
            tag_source=True,
        )

    # Fall back to heuristics
    heuristic_ids = extract_heuristic_node_ids(content, flow_graph)
    return SpecEntry(
        path=rel,
        node_ids=tuple(heuristic_ids),
        content_hash=content_hash,
        pinned=pinned,
        tag_source=False,
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _load_cache(cache_path: Path | None) -> dict[str, SpecEntry]:
    if cache_path is None or not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return {e["path"]: SpecEntry.from_dict(e) for e in data.get("entries", [])}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def _save_cache(cache_path: Path, index: SpecIndex) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(index.to_json(), encoding="utf-8")
