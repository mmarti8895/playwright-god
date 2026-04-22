"""Framework-neutral test indexing for duplicate detection and coverage planning."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re

from .spec_index import extract_heuristic_node_ids, parse_pg_tags


@dataclass(frozen=True, slots=True)
class TestIndexEntry:
    """A normalized test entry across supported test frameworks."""

    path: str
    owner_framework: str
    covered_nodes: tuple[str, ...]
    covered_journeys: tuple[str, ...]
    assertion_types: tuple[str, ...]
    target_urls: tuple[str, ...]
    content_hash: str
    pinned: bool = False
    tag_source: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "owner_framework": self.owner_framework,
            "covered_nodes": list(self.covered_nodes),
            "covered_journeys": list(self.covered_journeys),
            "assertion_types": list(self.assertion_types),
            "target_urls": list(self.target_urls),
            "content_hash": self.content_hash,
            "pinned": self.pinned,
            "tag_source": self.tag_source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestIndexEntry":
        return cls(
            path=str(data.get("path", "")),
            owner_framework=str(data.get("owner_framework", "unknown")),
            covered_nodes=tuple(data.get("covered_nodes", [])),
            covered_journeys=tuple(data.get("covered_journeys", [])),
            assertion_types=tuple(data.get("assertion_types", [])),
            target_urls=tuple(data.get("target_urls", [])),
            content_hash=str(data.get("content_hash", "")),
            pinned=bool(data.get("pinned", False)),
            tag_source=bool(data.get("tag_source", False)),
        )


@dataclass
class TestIndex:
    """A normalized index over browser and browser-adjacent tests."""

    entries: dict[str, TestIndexEntry] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.entries.values())

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, path: str) -> TestIndexEntry | None:
        return self.entries.get(path)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": "1.0",
            "entries": [entry.to_dict() for entry in self.entries.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestIndex":
        return cls(
            entries={
                str(item["path"]): TestIndexEntry.from_dict(item)
                for item in data.get("entries", [])
                if isinstance(item, dict) and "path" in item
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "TestIndex":
        return cls.from_dict(json.loads(text))

    @classmethod
    def build(
        cls,
        test_root: Path,
        *,
        cache_path: Path | None = None,
        flow_graph=None,
    ) -> "TestIndex":
        cached = _load_cache(cache_path)
        entries: dict[str, TestIndexEntry] = {}
        patterns = ("*.spec.ts", "*.cy.ts", "*.cy.js", "test_*.py", "*test.py")
        seen_files: list[Path] = []
        for pattern in patterns:
            seen_files.extend(test_root.rglob(pattern))
        for test_path in sorted({path for path in seen_files if path.is_file()}):
            try:
                content = test_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(test_path.relative_to(test_root))
            content_hash = _hash_content(content)
            if rel in cached and cached[rel].content_hash == content_hash:
                entries[rel] = cached[rel]
                continue
            entries[rel] = _parse_test_entry(rel, content, content_hash, flow_graph)
        index = cls(entries=entries)
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(index.to_json(), encoding="utf-8")
        return index

    def covered_nodes(self) -> set[str]:
        covered: set[str] = set()
        for entry in self.entries.values():
            covered.update(entry.covered_nodes)
        return covered

    def covered_journeys(self) -> set[str]:
        covered: set[str] = set()
        for entry in self.entries.values():
            covered.update(entry.covered_journeys)
        return covered

    def duplicates_for(
        self,
        *,
        covered_nodes: tuple[str, ...] = (),
        covered_journeys: tuple[str, ...] = (),
    ) -> list[str]:
        """Return paths whose node/journey coverage fully overlaps the candidate."""

        wanted_nodes = set(covered_nodes)
        wanted_journeys = set(covered_journeys)
        matches: list[str] = []
        if not wanted_nodes and not wanted_journeys:
            return matches
        for entry in self.entries.values():
            nodes_hit = wanted_nodes.issubset(set(entry.covered_nodes)) if wanted_nodes else True
            journeys_hit = wanted_journeys.issubset(set(entry.covered_journeys)) if wanted_journeys else True
            if nodes_hit and journeys_hit:
                matches.append(entry.path)
        return matches


SpecIndex = TestIndex
SpecEntry = TestIndexEntry


def infer_test_journeys(content: str) -> tuple[str, ...]:
    urls = _extract_urls(content)
    journeys = [f"visit:{url}" for url in urls]
    selectors = _extract_selector_tokens(content)
    journeys.extend(f"assert:{token}" for token in selectors[:8])
    return tuple(dict.fromkeys(journeys))


def _parse_test_entry(
    rel: str,
    content: str,
    content_hash: str,
    flow_graph=None,
) -> TestIndexEntry:
    framework = _detect_framework(rel, content)
    tag_ids, pinned = parse_pg_tags(content)
    heuristic_nodes = extract_heuristic_node_ids(content, flow_graph)
    node_ids = tuple(tag_ids or heuristic_nodes)
    return TestIndexEntry(
        path=rel,
        owner_framework=framework,
        covered_nodes=node_ids,
        covered_journeys=infer_test_journeys(content),
        assertion_types=_assertion_types(content),
        target_urls=_extract_urls(content),
        content_hash=content_hash,
        pinned=pinned,
        tag_source=bool(tag_ids),
    )


def _detect_framework(rel: str, content: str) -> str:
    lower_rel = rel.lower()
    lower = content.lower()
    if lower_rel.endswith(".spec.ts") or "@playwright/test" in lower:
        return "playwright"
    if ".cy." in lower_rel or "cy.visit" in lower:
        return "cypress"
    if "webdriverio" in lower or "browser.url(" in lower:
        return "webdriverio"
    if "selenium" in lower or "driver.get(" in lower:
        return "selenium"
    if "playwright" in lower and lower_rel.endswith(".py"):
        return "pytest-browser"
    return "unknown"


def _assertion_types(content: str) -> tuple[str, ...]:
    found: list[str] = []
    markers = (
        ("toBeVisible", "visible"),
        ("toHaveURL", "url"),
        ("toContainText", "text"),
        ("expect(", "expect"),
        ("assert ", "assert"),
        (".should(", "should"),
    )
    for needle, label in markers:
        if needle in content and label not in found:
            found.append(label)
    return tuple(found)


def _extract_urls(content: str) -> tuple[str, ...]:
    patterns = [
        r'page\.goto\(\s*["`\']([^"`\']+)["`\']',
        r'cy\.visit\(\s*["`\']([^"`\']+)["`\']',
        r'browser\.url\(\s*["`\']([^"`\']+)["`\']',
        r'driver\.get\(\s*["`\']([^"`\']+)["`\']',
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, content, re.IGNORECASE):
            if match not in found:
                found.append(match)
    return tuple(found)


def _extract_selector_tokens(content: str) -> tuple[str, ...]:
    patterns = [
        r'getByRole\(\s*["`\']([^"`\']+)["`\']',
        r'getByText\(\s*["`\']([^"`\']+)["`\']',
        r'locator\(\s*["`\']([^"`\']+)["`\']',
        r'querySelector\(\s*["`\']([^"`\']+)["`\']',
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, content):
            token = match.strip()
            if token and token not in found:
                found.append(token)
    return tuple(found)


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _load_cache(cache_path: Path | None) -> dict[str, TestIndexEntry]:
    if cache_path is None or not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return {
            str(item["path"]): TestIndexEntry.from_dict(item)
            for item in data.get("entries", [])
            if isinstance(item, dict) and "path" in item
        }
    except (OSError, json.JSONDecodeError, KeyError):
        return {}
