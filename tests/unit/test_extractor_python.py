"""Unit tests for the Python flow-graph extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from playwright_god.extractors import python as py_ext


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_fastapi_decorator_routes(tmp_path: Path):
    src = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "router = object()\n"
        "@app.get('/healthz')\n"
        "def healthz():\n"
        "    return 'ok'\n"
        "\n"
        "@router.post('/items')\n"
        "async def create_item():\n"
        "    return {}\n"
    )
    path = _write(tmp_path, "api.py", src)
    nodes, edges = py_ext.extract_file(path, "api.py")
    ids = {n.id for n in nodes}
    assert "route:GET:/healthz" in ids
    assert "route:POST:/items" in ids
    healthz = next(n for n in nodes if n.id == "route:GET:/healthz")
    assert healthz.handler == "healthz"
    assert healthz.evidence[0].file == "api.py"
    assert healthz.evidence[0].line_range[0] >= 4


def test_flask_route_with_methods(tmp_path: Path):
    src = (
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.route('/login', methods=['GET', 'POST'])\n"
        "def login():\n"
        "    return ''\n"
    )
    path = _write(tmp_path, "app.py", src)
    nodes, _ = py_ext.extract_file(path, "app.py")
    ids = {n.id for n in nodes}
    assert "route:GET:/login" in ids
    assert "route:POST:/login" in ids


def test_flask_route_default_get(tmp_path: Path):
    src = (
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.route('/')\n"
        "def home():\n"
        "    return ''\n"
    )
    path = _write(tmp_path, "app.py", src)
    nodes, _ = py_ext.extract_file(path, "app.py")
    assert any(n.id == "route:GET:/" for n in nodes)


def test_django_urlpatterns(tmp_path: Path):
    src = (
        "from django.urls import path, re_path\n"
        "from . import views\n"
        "urlpatterns = [\n"
        "    path('users/', views.user_list),\n"
        "    re_path(r'^items/(?P<pk>[0-9]+)/$', views.item_detail),\n"
        "]\n"
    )
    path = _write(tmp_path, "urls.py", src)
    nodes, _ = py_ext.extract_file(path, "urls.py")
    ids = {n.id for n in nodes}
    assert "route:ANY:/users/" in ids
    assert any(i.startswith("route:ANY:/^items/") for i in ids)
    user_route = next(n for n in nodes if n.id == "route:ANY:/users/")
    assert user_route.handler == "views.user_list"


def test_decorator_without_args_skipped(tmp_path: Path):
    src = (
        "@staticmethod\n"
        "def something():\n"
        "    pass\n"
    )
    path = _write(tmp_path, "x.py", src)
    nodes, _ = py_ext.extract_file(path, "x.py")
    assert nodes == []


def test_syntax_error_returns_empty(tmp_path: Path):
    path = _write(tmp_path, "broken.py", "def :::\n")
    nodes, edges = py_ext.extract_file(path, "broken.py")
    assert nodes == [] and edges == []


def test_unreadable_file_returns_empty(tmp_path: Path):
    path = tmp_path / "missing.py"
    nodes, edges = py_ext.extract_file(path, "missing.py")
    assert nodes == [] and edges == []


# ---------------------------------------------------------------------------
# Orchestrator tests (extractors/__init__.py)
# ---------------------------------------------------------------------------


def test_orchestrator_extracts_python_and_html_and_js(tmp_path):
    from playwright_god import extractors as orch

    orch._reset_warnings()
    (tmp_path / "api.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n"
        "@app.get('/x')\ndef x(): return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "page.html").write_text("<a href='/dash'>d</a>\n", encoding="utf-8")
    (tmp_path / "App.tsx").write_text(
        'import {Routes, Route} from "react-router-dom";\n'
        'export default function App(){return <Route path="/login" />;}\n',
        encoding="utf-8",
    )
    g = orch.extract(tmp_path)
    ids = {n.id for n in g.nodes}
    assert "route:GET:/x" in ids
    assert "route:GET:/dash" in ids
    assert "route:GET:/login" in ids


def test_orchestrator_skips_excluded_dirs(tmp_path):
    from playwright_god import extractors as orch

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.tsx").write_text(
        'export default function X(){}\n', encoding="utf-8"
    )
    g = orch.extract(tmp_path)
    assert all("node_modules" not in n.id for n in g.nodes)


def test_orchestrator_warns_once_when_extras_missing(tmp_path, monkeypatch):
    from playwright_god import extractors as orch

    orch._reset_warnings()
    monkeypatch.setattr(orch._js_ts, "is_available", lambda: False)
    monkeypatch.setattr(orch._html, "is_available", lambda: False)
    (tmp_path / "App.tsx").write_text("export default function X(){}\n", encoding="utf-8")
    (tmp_path / "i.html").write_text("<a href='/x'>x</a>\n", encoding="utf-8")
    import warnings as _w
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        orch.extract(tmp_path)
    msgs = [str(w.message) for w in caught]
    assert any("js-extract" in m for m in msgs)
    assert any("html-extract" in m for m in msgs)
    # second call should not re-warn
    with _w.catch_warnings(record=True) as again:
        _w.simplefilter("always")
        orch.extract(tmp_path)
    assert all("install" not in str(w.message).lower() for w in again)


def test_relpath_handles_outside_root(tmp_path):
    from playwright_god.extractors import _relpath

    # Path on a different anchor cannot be made relative.
    out = _relpath(Path("/tmp/elsewhere"), tmp_path)
    assert out == "/tmp/elsewhere"


def test_extractor_capabilities_include_metadata():
    from playwright_god.extractors import extractor_capabilities

    caps = extractor_capabilities()
    assert any(cap["name"] == "python-web" for cap in caps)
    js_cap = next(cap for cap in caps if cap["name"] == "js-ts-ui")
    assert "typescript" in js_cap["languages"]
    assert "react" in js_cap["frameworks"]


# ---------------------------------------------------------------------------
# Edge cases for full coverage
# ---------------------------------------------------------------------------


def test_decorator_with_dynamic_path_skipped(tmp_path):
    src = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get(some_var)\n"
        "def x(): return 1\n"
    )
    path = _write(tmp_path, "a.py", src)
    nodes, _ = py_ext.extract_file(path, "a.py")
    assert all(n.kind != "route" for n in nodes)


def test_bare_name_decorator_skipped(tmp_path):
    src = "@cached\ndef x(): return 1\n"
    path = _write(tmp_path, "a.py", src)
    nodes, _ = py_ext.extract_file(path, "a.py")
    assert nodes == []


def test_urlpatterns_non_list_assignment_skipped(tmp_path):
    src = "urlpatterns = some_other()\n"
    path = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(path, "u.py")
    assert nodes == []


def test_urlpatterns_path_with_non_string_first_arg_skipped(tmp_path):
    src = (
        "from django.urls import path\n"
        "urlpatterns = [path(some_var, view)]\n"
    )
    path_file = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(path_file, "u.py")
    assert nodes == []


def test_path_callable_handler_stringified(tmp_path):
    src = (
        "from django.urls import path\n"
        "from . import views\n"
        "urlpatterns = [path('x/', views.IndexView.as_view())]\n"
    )
    p = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(p, "u.py")
    handler = next(n for n in nodes).handler
    # stringify_handler walks the Call -> Attribute chain.
    assert "as_view" in handler


def test_urlpatterns_non_call_entry_skipped(tmp_path):
    src = "urlpatterns = ['notacall']\n"
    p = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(p, "u.py")
    assert nodes == []


def test_methods_kwarg_with_non_string_elements_filtered(tmp_path):
    src = (
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.route('/x', methods=[some_var])\n"
        "def x(): return ''\n"
    )
    p = _write(tmp_path, "a.py", src)
    nodes, _ = py_ext.extract_file(p, "a.py")
    # No string method names -> defaults to GET
    assert any(n.id == "route:GET:/x" for n in nodes)


# ---------------------------------------------------------------------------
# Additional edge-case tests for full coverage (lines 71-72, 74, 107, 147-148, 150, 152, 176)
# ---------------------------------------------------------------------------


def test_decorator_with_name_form_get(tmp_path):
    """Test decorator where func is an ast.Name (lines 71-74)."""
    src = (
        "from fastapi import get\n"
        "@get('/direct')\n"
        "def direct_route(): return 1\n"
    )
    path = _write(tmp_path, "a.py", src)
    nodes, _ = py_ext.extract_file(path, "a.py")
    # 'get' is in _FASTAPI_METHODS, so it should produce a route
    assert any(n.id == "route:GET:/direct" for n in nodes)


def test_decorator_with_unknown_method_name(tmp_path):
    """Test decorator with method name not in _FASTAPI_METHODS (line 107 continue)."""
    src = (
        "from something import app\n"
        "@app.custom('/foo')\n"
        "def foo(): return 1\n"
    )
    path = _write(tmp_path, "a.py", src)
    nodes, _ = py_ext.extract_file(path, "a.py")
    # 'custom' is not in recognized methods, so no route produced
    assert nodes == []


def test_django_path_via_attribute_form(tmp_path):
    """Test Django path() called via Attribute (lines 147-148)."""
    src = (
        "from django import urls\n"
        "urlpatterns = [urls.path('admin/', admin_view)]\n"
    )
    path = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(path, "u.py")
    assert any(n.id == "route:ANY:/admin/" for n in nodes)


def test_django_path_wrong_name_skipped(tmp_path):
    """Test urlpatterns with a call to something other than path/re_path/url (line 150)."""
    src = (
        "from django.urls import include\n"
        "urlpatterns = [include('app.urls')]\n"
    )
    path = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(path, "u.py")
    # 'include' not in {path, re_path, url}
    assert nodes == []


def test_django_path_no_args(tmp_path):
    """Test path() with no arguments at all (line 152)."""
    src = (
        "from django.urls import path\n"
        "urlpatterns = [path()]\n"
    )
    path = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(path, "u.py")
    assert nodes == []


def test_stringify_handler_unknown_type_returns_empty(tmp_path):
    """Test _stringify_handler returns '' for unknown AST node types (line 176)."""
    src = (
        "from django.urls import path\n"
        "urlpatterns = [path('x/', 123)]\n"  # 123 is ast.Constant(int), not Name/Attr/Call
    )
    path = _write(tmp_path, "u.py", src)
    nodes, _ = py_ext.extract_file(path, "u.py")
    # Route created but handler is ""
    route = next((n for n in nodes if n.id == "route:ANY:/x/"), None)
    assert route is not None
    assert route.handler == ""


def test_decorator_call_func_is_call_returns_empty(tmp_path):
    """Test decorator where call.func is a Call node (line 74: method_name is None)."""
    # @something()('/path') - the outer call's func is itself a Call
    src = (
        "from factory import create_decorator\n"
        "@create_decorator()('/foo')\n"
        "def foo(): return 1\n"
    )
    path = _write(tmp_path, "a.py", src)
    nodes, _ = py_ext.extract_file(path, "a.py")
    # The inner call's func is a Call, not Name or Attribute, so method_name=None
    assert nodes == []


def test_decorator_without_path_skipped(tmp_path):
    src = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.middleware('http')\n"
        "def x(req, call_next): return call_next(req)\n"
    )
    p = _write(tmp_path, "a.py", src)
    nodes, _ = py_ext.extract_file(p, "a.py")
    # 'middleware' isn't in our recognised method set; skipped.
    assert all(n.kind != "route" for n in nodes)
