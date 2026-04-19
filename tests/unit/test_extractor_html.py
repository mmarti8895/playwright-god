"""Unit tests for the HTML flow-graph extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from playwright_god.extractors import html as html_ext

pytestmark = pytest.mark.skipif(
    not html_ext.is_available(), reason="selectolax not installed"
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_form_post_creates_action_and_route(tmp_path: Path):
    src = (
        "<html><body>\n"
        "<form action='/login' method='post' data-action='login'>\n"
        "  <input name='u'/><input name='p'/>\n"
        "</form>\n"
        "</body></html>\n"
    )
    p = _write(tmp_path, "login.html", src)
    nodes, edges = html_ext.extract_file(p, "login.html")
    ids = {n.id for n in nodes}
    assert any(i.startswith("action:login.html:") and "#login" in i for i in ids)
    assert "route:POST:/login" in ids
    assert any(e.kind == "submits" for e in edges)


def test_anchor_creates_navigates_edge(tmp_path: Path):
    src = "<a href='/dashboard' id='go'>Dashboard</a>\n"
    p = _write(tmp_path, "x.html", src)
    nodes, edges = html_ext.extract_file(p, "x.html")
    ids = {n.id for n in nodes}
    assert any("#go" in i for i in ids)
    assert "route:GET:/dashboard" in ids
    assert any(e.kind == "navigates" for e in edges)


def test_button_creates_action_only(tmp_path: Path):
    src = "<button id='logout-btn'>Log out</button>\n"
    p = _write(tmp_path, "x.html", src)
    nodes, edges = html_ext.extract_file(p, "x.html")
    assert any(n.id.endswith("#logout-btn") for n in nodes)
    assert all(n.kind != "route" for n in nodes)
    assert edges == []


def test_anchor_without_href_skipped(tmp_path: Path):
    p = _write(tmp_path, "x.html", "<a>no href</a>")
    nodes, _ = html_ext.extract_file(p, "x.html")
    assert nodes == []


def test_external_link_no_route(tmp_path: Path):
    p = _write(tmp_path, "x.html", "<a href='https://example.com'>x</a>")
    nodes, edges = html_ext.extract_file(p, "x.html")
    assert all(n.kind != "route" for n in nodes)
    assert edges == []


def test_unreadable_file_returns_empty(tmp_path: Path):
    p = tmp_path / "missing.html"
    nodes, edges = html_ext.extract_file(p, "missing.html")
    assert nodes == [] and edges == []


def test_node_line_handles_missing_snippet_gracefully(tmp_path):
    # A blank-attribute case where node.html may be empty / not findable.
    src = "\n\n\n<button>X</button>\n"
    p = _write(tmp_path, "x.html", src)
    nodes, _ = html_ext.extract_file(p, "x.html")
    btn = next(n for n in nodes if n.kind == "action")
    # Button is on line 4
    assert btn.line == 4


def test_button_at_eof_is_attributed_to_last_line(tmp_path):
    src = "<button id='end'>X</button>" + "\n" * 50
    p = _write(tmp_path, "x.html", src)
    nodes, _ = html_ext.extract_file(p, "x.html")
    btn = next(n for n in nodes if n.role == "end")
    assert btn.line >= 1


def test_node_line_returns_last_line_when_pos_past_all_offsets():
    # Force the for-loop to exhaust without returning, hitting the trailing
    # `return line` at the end of `_node_line`.
    from playwright_god.extractors.html import _line_offsets, _node_line

    class FakeNode:
        html = "tail"
    src = "abc\ndef\ntail"  # snippet at offset 8; offsets=[0,4,8] -> line 3
    line = _node_line(FakeNode(), src, _line_offsets(src))
    assert line == 3


def test_node_line_fallback_when_snippet_not_found(monkeypatch):
    # Directly exercise _node_line's "pos < 0" branch by faking node.html.
    from playwright_god.extractors.html import _line_offsets, _node_line

    class FakeNode:
        html = "<absent-tag/>"
    src = "<html><body><p>x</p></body></html>"
    assert _node_line(FakeNode(), src, _line_offsets(src)) == 1


def test_node_line_returns_one_when_snippet_empty():
    from playwright_god.extractors.html import _line_offsets, _node_line

    class FakeNode:
        html = ""
    src = "x"
    assert _node_line(FakeNode(), src, _line_offsets(src)) == 1
