"""Flow-graph extractors for Python, JS/TS, and HTML sources.

Public entry point: :func:`extract`.

Each language-specific extractor is wrapped in a ``try/except ImportError``
so that the package imports cleanly even when optional extras
(``[js-extract]`` for tree-sitter, ``[html-extract]`` for selectolax) are
missing.  When an extractor would have run but its extra is not installed,
a single :func:`warnings.warn` is emitted per process with an install hint.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Iterable, Sequence

from ..flow_graph import Action, Edge, FlowGraph, Node, Route, View
from . import html as _html
from . import js_ts as _js_ts
from . import python as _python

_PY_EXTS = {".py"}
_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".vue", ".mjs", ".cjs"}
_HTML_EXTS = {".html", ".htm"}

_WARNED: set[str] = set()


def _warn_once(category: str, message: str) -> None:
    if category in _WARNED:
        return
    _WARNED.add(category)
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def _reset_warnings() -> None:
    """Test hook: clear the per-process "warned once" registry."""

    _WARNED.clear()


def _walk(root: Path, excluded: set[str]) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.parts):
            continue
        yield path


def extract(
    root: str | Path,
    *,
    excluded_dirs: Sequence[str] = (
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
    ),
) -> FlowGraph:
    """Walk *root* and assemble a :class:`FlowGraph` from all extractors.

    Files outside the supported extension sets are silently skipped.  When an
    optional extractor dependency is missing for a file class that *would*
    have been processed, a one-shot warning is emitted with an install hint.
    """

    root_path = Path(root).resolve()
    excluded = set(excluded_dirs)
    nodes: list[Node] = []
    edges: list[Edge] = []

    js_files: list[Path] = []
    html_files: list[Path] = []

    for file_path in _walk(root_path, excluded):
        ext = file_path.suffix.lower()
        rel = _relpath(file_path, root_path)
        if ext in _PY_EXTS:
            n, e = _python.extract_file(file_path, rel)
            nodes.extend(n)
            edges.extend(e)
        elif ext in _JS_EXTS:
            js_files.append(file_path)
        elif ext in _HTML_EXTS:
            html_files.append(file_path)

    if js_files:
        if _js_ts.is_available():
            for fp in js_files:
                rel = _relpath(fp, root_path)
                n, e = _js_ts.extract_file(fp, rel, root=root_path)
                nodes.extend(n)
                edges.extend(e)
        else:
            _warn_once(
                "js-extract",
                "tree-sitter not installed; skipping JS/TS flow extraction. "
                "Install with: pip install 'playwright-god[js-extract]'",
            )

    if html_files:
        if _html.is_available():
            for fp in html_files:
                rel = _relpath(fp, root_path)
                n, e = _html.extract_file(fp, rel)
                nodes.extend(n)
                edges.extend(e)
        else:
            _warn_once(
                "html-extract",
                "selectolax not installed; skipping HTML flow extraction. "
                "Install with: pip install 'playwright-god[html-extract]'",
            )

    return FlowGraph.from_iterables(nodes, edges)


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


__all__ = ["extract", "Action", "Edge", "FlowGraph", "Node", "Route", "View"]
