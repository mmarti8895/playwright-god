"""HTML flow-graph extractor (forms, anchors, buttons).

Uses ``selectolax`` (lexbor-backed) for fast, lenient parsing.
"""

from __future__ import annotations

from pathlib import Path

from ..flow_graph import Action, Edge, Evidence, Node, Route

try:  # pragma: no cover — optional dep
    from selectolax.parser import HTMLParser  # type: ignore
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    HTMLParser = None  # type: ignore
    _AVAILABLE = False


def is_available() -> bool:
    """Return True if selectolax is importable."""

    return _AVAILABLE


def extract_file(path: Path, rel: str) -> tuple[list[Node], list[Edge]]:
    """Return (nodes, edges) parsed from a single HTML/template file."""

    if not _AVAILABLE:
        return [], []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [], []

    return _parse_source(source, rel)


def _parse_source(source: str, rel: str) -> tuple[list[Node], list[Edge]]:
    """Internal: parse a string buffer (used for unit tests)."""

    nodes: list[Node] = []
    edges: list[Edge] = []
    tree = HTMLParser(source)
    # Pre-compute line offsets so we can map a substring start to a 1-based line.
    line_offsets = _line_offsets(source)

    # ---- forms --------------------------------------------------------------
    for form in tree.css("form"):
        action = (form.attributes.get("action") or "").strip()
        method = (form.attributes.get("method") or "GET").upper()
        line = _node_line(form, source, line_offsets)
        role = (form.attributes.get("data-action")
                or form.attributes.get("name")
                or form.attributes.get("id")
                or "submit")
        evidence = (Evidence(file=rel, line_range=(line, line)),)
        action_node = Action(file=rel, line=line, role=role, evidence=evidence)
        nodes.append(action_node)
        if action.startswith("/"):
            route = Route(method=method, path=action, handler="", evidence=evidence)
            nodes.append(route)
            edges.append(Edge(action_node.id, route.id, "submits"))

    # ---- anchors ------------------------------------------------------------
    for a in tree.css("a"):
        href = (a.attributes.get("href") or "").strip()
        if not href:
            continue
        line = _node_line(a, source, line_offsets)
        role = (a.attributes.get("data-action")
                or a.attributes.get("id")
                or f"link-{href}")
        evidence = (Evidence(file=rel, line_range=(line, line)),)
        action_node = Action(file=rel, line=line, role=role, evidence=evidence)
        nodes.append(action_node)
        if href.startswith("/"):
            route = Route(method="GET", path=href, handler="", evidence=evidence)
            nodes.append(route)
            edges.append(Edge(action_node.id, route.id, "navigates"))

    # ---- buttons ------------------------------------------------------------
    for btn in tree.css("button"):
        line = _node_line(btn, source, line_offsets)
        role = (btn.attributes.get("data-action")
                or btn.attributes.get("id")
                or btn.attributes.get("name")
                or "button")
        evidence = (Evidence(file=rel, line_range=(line, line)),)
        nodes.append(Action(file=rel, line=line, role=role, evidence=evidence))

    return nodes, edges


# ---------------------------------------------------------------------------
# Line tracking
# ---------------------------------------------------------------------------


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _node_line(node, source: str, offsets: list[int]) -> int:
    # selectolax doesn't expose source positions; approximate by searching
    # for the first occurrence of the node's outer HTML in the source.
    snippet = (node.html or "")[:60]
    if not snippet:
        return 1
    pos = source.find(snippet)
    if pos < 0:
        return 1
    # Binary search would be ideal; linear is fine for fixture-sized HTML.
    line = 1
    for off in offsets[1:]:
        if off > pos:
            return line
        line += 1
    return line


__all__ = ["extract_file", "is_available"]
