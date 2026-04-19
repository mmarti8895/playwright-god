"""Unit tests for playwright_god.crawler."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from playwright_god.crawler import (
    EXTENSION_TO_LANGUAGE,
    FileInfo,
    RepositoryCrawler,
    _BINARY_EXTENSIONS,
    _DEFAULT_SKIP_PATTERNS,
)


# ---------------------------------------------------------------------------
# FileInfo
# ---------------------------------------------------------------------------


class TestFileInfo:
    def test_attributes(self):
        fi = FileInfo(
            path="src/app.py",
            absolute_path="/repo/src/app.py",
            content="print('hello')\n",
            language="python",
            size=16,
        )
        assert fi.path == "src/app.py"
        assert fi.language == "python"
        assert fi.size == 16

    def test_repr_does_not_raise(self):
        fi = FileInfo("a.py", "/a.py", "", "python", 0)
        assert "a.py" in repr(fi)


# ---------------------------------------------------------------------------
# RepositoryCrawler
# ---------------------------------------------------------------------------


class TestRepositoryCrawlerInit:
    def test_default_skip_patterns(self):
        crawler = RepositoryCrawler()
        assert crawler.skip_patterns == _DEFAULT_SKIP_PATTERNS

    def test_custom_skip_patterns(self):
        crawler = RepositoryCrawler(skip_patterns=["foo", "bar"])
        assert crawler.skip_patterns == ("foo", "bar")

    def test_max_file_size(self):
        crawler = RepositoryCrawler(max_file_size=42)
        assert crawler.max_file_size == 42


class TestRepositoryCrawlerShouldSkip:
    def setup_method(self):
        self.crawler = RepositoryCrawler()
        self.root = Path("/fake/root")

    def test_skip_dot_git(self):
        assert self.crawler._should_skip(Path("/fake/root/.git"), self.root) is True

    def test_skip_node_modules(self):
        assert self.crawler._should_skip(Path("/fake/root/node_modules"), self.root) is True

    def test_skip_pycache(self):
        assert self.crawler._should_skip(Path("/fake/root/__pycache__"), self.root) is True

    def test_skip_pyc(self):
        assert self.crawler._should_skip(Path("/fake/root/app.pyc"), self.root) is True

    def test_skip_jpg(self):
        assert self.crawler._should_skip(Path("/fake/root/photo.jpg"), self.root) is True

    def test_skip_png(self):
        assert self.crawler._should_skip(Path("/fake/root/logo.png"), self.root) is True

    def test_skip_lock_file(self):
        # .lock extension is in _BINARY_EXTENSIONS
        assert self.crawler._should_skip(Path("/fake/root/package.lock"), self.root) is True

    def test_allow_python_file(self):
        assert self.crawler._should_skip(Path("/fake/root/app.py"), self.root) is False

    def test_allow_js_file(self):
        assert self.crawler._should_skip(Path("/fake/root/app.js"), self.root) is False

    def test_allow_html_file(self):
        assert self.crawler._should_skip(Path("/fake/root/index.html"), self.root) is False

    def test_custom_pattern(self):
        crawler = RepositoryCrawler(skip_patterns=["secret.txt"])
        assert crawler._should_skip(Path("/root/secret.txt"), Path("/root")) is True
        assert crawler._should_skip(Path("/root/public.txt"), Path("/root")) is False


class TestRepositoryCrawlerDetectLanguage:
    def setup_method(self):
        self.crawler = RepositoryCrawler()

    def test_python(self):
        assert self.crawler._detect_language(Path("app.py")) == "python"

    def test_javascript(self):
        assert self.crawler._detect_language(Path("app.js")) == "javascript"

    def test_typescript(self):
        assert self.crawler._detect_language(Path("app.ts")) == "typescript"

    def test_html(self):
        assert self.crawler._detect_language(Path("index.html")) == "html"

    def test_css(self):
        assert self.crawler._detect_language(Path("style.css")) == "css"

    def test_unknown(self):
        assert self.crawler._detect_language(Path("data.xyz")) == "unknown"

    def test_uppercase_extension(self):
        # Extensions are compared lower-cased
        assert self.crawler._detect_language(Path("App.PY")) == "python"


class TestRepositoryCrawlerCrawl:
    def test_crawl_sample_app(self, sample_repo_path, tmp_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        paths = [f.path for f in files]
        # The sample app has index.html, app.js, styles.css
        assert any("index.html" in p for p in paths)
        assert any("app.js" in p for p in paths)
        assert any("styles.css" in p for p in paths)

    def test_crawl_returns_file_info_objects(self, sample_repo_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        for f in files:
            assert isinstance(f, FileInfo)
            assert f.content  # non-empty

    def test_crawl_sorted_by_path(self, sample_repo_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        paths = [f.path for f in files]
        assert paths == sorted(paths)

    def test_crawl_raises_for_file(self, tmp_path):
        f = tmp_path / "notadir.txt"
        f.write_text("x")
        with pytest.raises(ValueError, match="not a directory"):
            RepositoryCrawler().crawl(str(f))

    def test_skip_directory(self, tmp_path):
        # Create a skip-worthy directory
        skip_dir = tmp_path / "node_modules"
        skip_dir.mkdir()
        (skip_dir / "lodash.js").write_text("module.exports = {};")
        (tmp_path / "main.js").write_text("console.log(1);")

        crawler = RepositoryCrawler()
        files = crawler.crawl(str(tmp_path))
        paths = [f.path for f in files]
        assert "main.js" in paths
        assert not any("node_modules" in p for p in paths)

    def test_max_file_size(self, tmp_path):
        big_file = tmp_path / "huge.txt"
        big_file.write_text("x" * 200)
        small_file = tmp_path / "small.txt"
        small_file.write_text("tiny")

        crawler = RepositoryCrawler(max_file_size=100)
        files = crawler.crawl(str(tmp_path))
        paths = [f.path for f in files]
        assert "small.txt" in paths
        assert "huge.txt" not in paths

    def test_language_detection_in_crawl(self, sample_repo_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        by_path = {f.path: f for f in files}
        html_files = [v for k, v in by_path.items() if k.endswith(".html")]
        assert html_files
        assert html_files[0].language == "html"

    def test_crawl_empty_directory(self, tmp_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(str(tmp_path))
        assert files == []


class TestBuildStructureSummary:
    def test_summary_contains_file_names(self, sample_repo_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        summary = crawler.build_structure_summary(files)
        assert "index.html" in summary
        assert "app.js" in summary

    def test_summary_contains_language(self, sample_repo_path):
        crawler = RepositoryCrawler()
        files = crawler.crawl(sample_repo_path)
        summary = crawler.build_structure_summary(files)
        assert "html" in summary
        assert "javascript" in summary

    def test_summary_empty_files(self):
        crawler = RepositoryCrawler()
        summary = crawler.build_structure_summary([])
        assert summary == ""


class TestReadFileOSError:
    """Cover the `except OSError: return None` branch in `_read_file`."""

    def test_unreadable_file_is_skipped_via_chmod(self, tmp_path):
        """A real file with mode 000 is silently skipped on the crawl."""
        # Skip when running as root: chmod 000 doesn't restrict reads for uid 0.
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("chmod 000 has no effect when running as root")

        unreadable = tmp_path / "secret.py"
        unreadable.write_text("print('hi')\n", encoding="utf-8")
        readable = tmp_path / "ok.py"
        readable.write_text("print('ok')\n", encoding="utf-8")

        os.chmod(unreadable, 0o000)
        try:
            crawler = RepositoryCrawler()
            files = crawler.crawl(str(tmp_path))
        finally:
            # Restore so pytest's tmp_path cleanup can remove the file.
            os.chmod(unreadable, 0o644)

        paths = {Path(f.path).name for f in files}
        assert "ok.py" in paths
        assert "secret.py" not in paths

    def test_oserror_during_read_is_skipped(self, tmp_path, monkeypatch):
        """Monkeypatch fallback: forces OSError on read for portability."""
        target = tmp_path / "problematic.py"
        target.write_text("print('hi')\n", encoding="utf-8")
        sibling = tmp_path / "fine.py"
        sibling.write_text("print('fine')\n", encoding="utf-8")

        original_read_text = Path.read_text

        def fake_read_text(self, *args, **kwargs):
            if self.name == "problematic.py":
                raise OSError("simulated read failure")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fake_read_text)

        crawler = RepositoryCrawler()
        files = crawler.crawl(str(tmp_path))

        names = {Path(f.path).name for f in files}
        assert "fine.py" in names
        assert "problematic.py" not in names
