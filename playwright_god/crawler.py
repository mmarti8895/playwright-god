"""Repository crawler: walks a directory tree and reads file contents."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".txt": "text",
    ".sh": "shell",
    ".bash": "shell",
    ".rb": "ruby",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".vue": "vue",
    ".svelte": "svelte",
    ".graphql": "graphql",
    ".sql": "sql",
    ".toml": "toml",
    ".xml": "xml",
}


@dataclass
class FileInfo:
    """Represents a single file in the repository."""

    path: str           # relative path from repo root
    absolute_path: str  # absolute path on disk
    content: str        # full text content
    language: str       # programming language detected by extension
    size: int           # byte size of content

    def __repr__(self) -> str:  # pragma: no cover
        return f"FileInfo(path={self.path!r}, language={self.language!r}, size={self.size})"


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------

_DEFAULT_SKIP_PATTERNS: tuple[str, ...] = (
    ".git",
    ".github",
    "node_modules",
    "__pycache__",
    "*.pyc",
    ".env",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "*.egg-info",
    "htmlcov",
    "coverage.xml",
    ".coverage",
)

_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".bin",
        ".mp3", ".mp4", ".avi", ".mov", ".wav",
        ".ttf", ".woff", ".woff2", ".eot",
        ".lock",          # package-lock.json, yarn.lock, uv.lock
        ".min.js",        # minified JS (by convention, not a real ext)
    }
)


class RepositoryCrawler:
    """Walks a repository directory tree and returns :class:`FileInfo` objects."""

    def __init__(
        self,
        skip_patterns: Sequence[str] | None = None,
        max_file_size: int = 100_000,
    ) -> None:
        """
        Parameters
        ----------
        skip_patterns:
            Glob patterns for *names* (not paths) that should be skipped.
            Defaults to :data:`_DEFAULT_SKIP_PATTERNS`.
        max_file_size:
            Files larger than this number of bytes are skipped.
        """
        self.skip_patterns: tuple[str, ...] = (
            tuple(skip_patterns) if skip_patterns is not None else _DEFAULT_SKIP_PATTERNS
        )
        self.max_file_size = max_file_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self, repo_path: str) -> list[FileInfo]:
        """Return a list of :class:`FileInfo` for every readable file in *repo_path*.

        Files / directories matching :attr:`skip_patterns` or larger than
        :attr:`max_file_size` bytes are silently skipped.
        """
        root = Path(repo_path).resolve()
        if not root.is_dir():
            raise ValueError(f"repo_path is not a directory: {repo_path!r}")

        files: list[FileInfo] = []
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            current_dir = Path(dirpath)
            # Prune skip directories in-place so os.walk won't descend into them
            dirnames[:] = [
                d for d in dirnames
                if not self._should_skip(current_dir / d, root)
            ]

            for filename in filenames:
                file_path = current_dir / filename
                if self._should_skip(file_path, root):
                    continue
                info = self._read_file(file_path, root)
                if info is not None:
                    files.append(info)

        files.sort(key=lambda f: f.path)
        return files

    def build_structure_summary(self, files: list[FileInfo]) -> str:
        """Return a tree-like text summary of the repository structure.

        Example output::

            src/
              app.py (python)
              utils.py (python)
            tests/
              test_app.py (python)
        """
        # Group files by their parent directory
        dirs: dict[str, list[FileInfo]] = {}
        for f in files:
            parent = str(Path(f.path).parent)
            dirs.setdefault(parent, []).append(f)

        lines: list[str] = []
        for dir_name in sorted(dirs.keys()):
            prefix = "" if dir_name == "." else f"{dir_name}/"
            lines.append(f"{prefix}")
            for file_info in sorted(dirs[dir_name], key=lambda x: x.path):
                name = Path(file_info.path).name
                lines.append(f"  {name} ({file_info.language})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _should_skip(self, path: Path, root: Path) -> bool:
        """Return True if *path* matches any skip pattern or has a binary extension."""
        name = path.name
        # Check name-based patterns
        for pattern in self.skip_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        # Check binary file extensions
        suffix = path.suffix.lower()
        if suffix in _BINARY_EXTENSIONS:
            return True
        return False

    def _detect_language(self, path: Path) -> str:
        """Return a language string based on the file extension."""
        suffix = path.suffix.lower()
        return EXTENSION_TO_LANGUAGE.get(suffix, "unknown")

    def _read_file(self, path: Path, root: Path) -> FileInfo | None:
        """Read a file and return a :class:`FileInfo`, or None if it cannot be read."""
        try:
            stat = path.stat()
            if stat.st_size > self.max_file_size:
                return None
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        relative = str(path.relative_to(root))
        return FileInfo(
            path=relative,
            absolute_path=str(path),
            content=content,
            language=self._detect_language(path),
            size=len(content.encode("utf-8")),
        )
