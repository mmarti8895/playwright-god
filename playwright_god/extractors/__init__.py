"""Flow-graph extractors for Python, JS/TS, and HTML sources.

Public entry point: :func:`extract`.

Each language-specific extractor is wrapped in a ``try/except ImportError``
so that the package imports cleanly even when optional extras
(``[js-extract]`` for tree-sitter, ``[html-extract]`` for selectolax) are
missing.  When an extractor would have run but its extra is not installed,
a single :func:`warnings.warn` is emitted per process with an install hint.
"""

from __future__ import annotations

from dataclasses import dataclass
import warnings
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..flow_graph import Action, Edge, FlowGraph, Node, Route, View
from . import html as _html
from . import js_ts as _js_ts
from . import python as _python

_PY_EXTS = {".py"}
_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".vue", ".mjs", ".cjs"}
_HTML_EXTS = {".html", ".htm"}

_WARNED: set[str] = set()


@dataclass(frozen=True)
class ExtractorCapability:
    """Capability metadata for a registered surface extractor."""

    name: str
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]
    supported_extensions: tuple[str, ...]
    confidence: float
    requires_extra_dep: bool = False
    availability_check: Callable[[], bool] | None = None

    @property
    def available(self) -> bool:
        return self.availability_check() if self.availability_check is not None else True

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "languages": list(self.languages),
            "frameworks": list(self.frameworks),
            "supported_extensions": list(self.supported_extensions),
            "confidence": round(self.confidence, 3),
            "requires_extra_dep": self.requires_extra_dep,
            "available": self.available,
        }


_CAPABILITIES: tuple[ExtractorCapability, ...] = (
    ExtractorCapability(
        name="python-web",
        languages=("python",),
        frameworks=("fastapi", "flask", "django"),
        supported_extensions=tuple(sorted(_PY_EXTS)),
        confidence=0.85,
    ),
    ExtractorCapability(
        name="js-ts-ui",
        languages=("javascript", "typescript", "vue"),
        frameworks=("react", "react-router", "nextjs", "vue"),
        supported_extensions=tuple(sorted(_JS_EXTS)),
        confidence=0.8,
        requires_extra_dep=True,
        availability_check=_js_ts.is_available,
    ),
    ExtractorCapability(
        name="html-surface",
        languages=("html",),
        frameworks=("server-rendered-html", "static-site"),
        supported_extensions=tuple(sorted(_HTML_EXTS)),
        confidence=0.7,
        requires_extra_dep=True,
        availability_check=_html.is_available,
    ),
)


def _warn_once(category: str, message: str) -> None:
    if category in _WARNED:
        return
    _WARNED.add(category)
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def _reset_warnings() -> None:
    """Test hook: clear the per-process "warned once" registry."""

    _WARNED.clear()


def extractor_capabilities() -> list[dict[str, object]]:
    """Return capability metadata for all registered extractors."""

    return [item.to_dict() for item in _CAPABILITIES]


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


__all__ = [
    "extract",
    "extractor_capabilities",
    "ExtractorCapability",
    "Action",
    "Edge",
    "FlowGraph",
    "Node",
    "Route",
    "View",
]
