"""JS/TS flow-graph extractor (React Router v6, Next.js, Vue Router).

Uses ``tree-sitter`` + ``tree-sitter-typescript`` (TSX grammar) when
available.  Vue ``<script>`` blocks are extracted via the same TSX grammar
after a coarse ``<script>...</script>`` slice.

Public surface:
    * :func:`is_available` — True when tree-sitter is importable.
    * :func:`extract_file` — return ``(nodes, edges)`` for a single file.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..flow_graph import Edge, Evidence, Node, Route, View

try:  # pragma: no cover — optional dep
    import tree_sitter as _ts
    import tree_sitter_typescript as _tts

    _TSX_LANG = _ts.Language(_tts.language_tsx())
    _PARSER = _ts.Parser(_TSX_LANG)
    _AVAILABLE = True
except ImportError:  # pragma: no cover — missing extra
    _AVAILABLE = False
    _PARSER = None
    _TSX_LANG = None


def is_available() -> bool:
    """Return True if tree-sitter (the JS/TS extractor's only extra) is importable."""

    return _AVAILABLE


def extract_file(
    path: Path,
    rel: str,
    *,
    root: Path | None = None,
) -> tuple[list[Node], list[Edge]]:
    """Return (nodes, edges) extracted from a single JS/TS/Vue file."""

    if not _AVAILABLE:
        return [], []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [], []

    nodes: list[Node] = []
    edges: list[Edge] = []

    # 1. Filesystem-based routing (Next.js pages/ + app/)
    fs_nodes, fs_edges = _nextjs_fs_route(rel)
    nodes.extend(fs_nodes)
    edges.extend(fs_edges)

    # 2. Vue SFC: extract just the <script> block for the TS parser
    parse_source = source
    if path.suffix.lower() == ".vue":
        parse_source = _extract_vue_script(source) or ""
        if not parse_source:
            return nodes, edges

    tree = _PARSER.parse(parse_source.encode("utf-8"))
    src_bytes = parse_source.encode("utf-8")

    # 3. View nodes: default-exported components
    default_view = _default_export_view(tree.root_node, src_bytes, rel)
    if default_view is not None:
        nodes.append(default_view)

    # 4. React Router v6 <Route path=... element={<X/>} />
    nodes.extend(_react_router_routes(tree.root_node, src_bytes, rel))

    # 5. Vue Router routes: { path: "/x", component: X }
    nodes.extend(_vue_router_routes(tree.root_node, src_bytes, rel))

    return nodes, edges


# ---------------------------------------------------------------------------
# Next.js filesystem routing
# ---------------------------------------------------------------------------

_NEXT_PAGE_EXTS = {".js", ".jsx", ".ts", ".tsx"}


def _nextjs_fs_route(rel: str) -> tuple[list[Node], list[Edge]]:
    parts = rel.split("/")
    # pages/  -> Pages router
    # app/page.tsx, app/foo/page.tsx -> App router
    if "pages" in parts:
        idx = parts.index("pages")
        sub = parts[idx + 1:]
        if not sub:
            return [], []
        ext = "." + sub[-1].rsplit(".", 1)[-1].lower()
        if ext not in _NEXT_PAGE_EXTS:
            return [], []
        # Strip extension
        sub[-1] = sub[-1].rsplit(".", 1)[0]
        # Skip private files like _app, _document
        if sub[-1].startswith("_"):
            return [], []
        path = _join_next_segments(sub)
        evidence = (Evidence(file=rel, line_range=(1, 1)),)
        route = Route(method="GET", path=path, handler=rel, evidence=evidence)
        view = View(file=rel, symbol="default", evidence=evidence)
        return [route, view], [Edge(route.id, view.id, "renders")]
    if "app" in parts and parts[-1].rsplit(".", 1)[0] == "page":
        idx = parts.index("app")
        sub = parts[idx + 1:-1]  # drop "page.tsx"
        path = _join_next_segments(sub) if sub else "/"
        evidence = (Evidence(file=rel, line_range=(1, 1)),)
        route = Route(method="GET", path=path, handler=rel, evidence=evidence)
        view = View(file=rel, symbol="default", evidence=evidence)
        return [route, view], [Edge(route.id, view.id, "renders")]
    return [], []


def _join_next_segments(segs: list[str]) -> str:
    out: list[str] = []
    for s in segs:
        if s == "index":
            continue
        # Next.js dynamic segment [id] -> {id}; catch-all [...slug] -> {slug*}
        if s.startswith("[...") and s.endswith("]"):
            out.append("{" + s[4:-1] + "*}")
        elif s.startswith("[") and s.endswith("]"):
            out.append("{" + s[1:-1] + "}")
        else:
            out.append(s)
    return "/" + "/".join(out) if out else "/"


# ---------------------------------------------------------------------------
# Vue SFC: pull out <script> contents
# ---------------------------------------------------------------------------

_VUE_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE
)


def _extract_vue_script(source: str) -> str:
    m = _VUE_SCRIPT_RE.search(source)
    return m.group("body") if m else ""


# ---------------------------------------------------------------------------
# Default-export View
# ---------------------------------------------------------------------------


def _default_export_view(root, src: bytes, rel: str) -> View | None:
    for node in _walk(root):
        if node.type == "export_statement":
            text = src[node.start_byte:node.end_byte].decode("utf-8", "ignore")
            if "default" not in text.split("\n", 1)[0]:
                continue
            line = node.start_point[0] + 1
            end = node.end_point[0] + 1
            return View(
                file=rel,
                symbol="default",
                evidence=(Evidence(file=rel, line_range=(line, end)),),
            )
    return None


# ---------------------------------------------------------------------------
# React Router v6
# ---------------------------------------------------------------------------


def _react_router_routes(root, src: bytes, rel: str) -> list[Route]:
    routes: list[Route] = []
    for node in _walk(root):
        if node.type not in ("jsx_self_closing_element", "jsx_opening_element"):
            continue
        name_node = node.child_by_field_name("name")
        if name_node is None or src[name_node.start_byte:name_node.end_byte] != b"Route":
            continue
        path_value: str | None = None
        for attr in node.children:
            if attr.type != "jsx_attribute":
                continue
            attr_name = attr.children[0] if attr.children else None
            if attr_name is None:
                continue
            if src[attr_name.start_byte:attr_name.end_byte] != b"path":
                continue
            # Find string literal
            for sub in attr.children:
                if sub.type == "string":
                    raw = src[sub.start_byte:sub.end_byte].decode("utf-8", "ignore")
                    path_value = raw.strip("\"'`")
                    break
        if not path_value:
            continue
        line = node.start_point[0] + 1
        end = node.end_point[0] + 1
        routes.append(Route(
            method="GET",
            path=path_value,
            handler=rel,
            evidence=(Evidence(file=rel, line_range=(line, end)),),
        ))
    return routes


# ---------------------------------------------------------------------------
# Vue Router: { path: "/x", component: Foo }
# ---------------------------------------------------------------------------


def _vue_router_routes(root, src: bytes, rel: str) -> list[Route]:
    routes: list[Route] = []
    for node in _walk(root):
        if node.type != "object":
            continue
        path_value: str | None = None
        for child in node.children:
            if child.type != "pair":
                continue
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            if key_node is None or val_node is None:
                continue
            key_text = src[key_node.start_byte:key_node.end_byte].decode(
                "utf-8", "ignore"
            ).strip("\"'`")
            if key_text == "path" and val_node.type == "string":
                path_value = src[val_node.start_byte:val_node.end_byte].decode(
                    "utf-8", "ignore"
                ).strip("\"'`")
                break
        if not path_value or not path_value.startswith("/"):
            continue
        line = node.start_point[0] + 1
        end = node.end_point[0] + 1
        routes.append(Route(
            method="GET",
            path=path_value,
            handler=rel,
            evidence=(Evidence(file=rel, line_range=(line, end)),),
        ))
    return routes


# ---------------------------------------------------------------------------
# Walk helper
# ---------------------------------------------------------------------------


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


__all__ = ["extract_file", "is_available"]
