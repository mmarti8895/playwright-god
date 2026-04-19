"""Unit tests for the JS/TS flow-graph extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from playwright_god.extractors import js_ts as js_ext

pytestmark = pytest.mark.skipif(
    not js_ext.is_available(), reason="tree-sitter not installed"
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_react_router_v6_route(tmp_path: Path):
    src = (
        'import {Routes, Route} from "react-router-dom";\n'
        'import Login from "./Login";\n'
        "function App() {\n"
        '  return <Routes><Route path="/login" element={<Login />} /></Routes>;\n'
        "}\n"
    )
    p = _write(tmp_path, "src/App.tsx", src)
    nodes, edges = js_ext.extract_file(p, "src/App.tsx")
    ids = {n.id for n in nodes}
    assert "route:GET:/login" in ids


def test_nextjs_pages_router(tmp_path: Path):
    p = _write(tmp_path, "pages/users/[id].tsx", "export default function U(){return null}\n")
    nodes, edges = js_ext.extract_file(p, "pages/users/[id].tsx")
    ids = {n.id for n in nodes}
    assert "route:GET:/users/{id}" in ids
    assert "view:pages/users/[id].tsx#default" in ids
    assert any(e.kind == "renders" for e in edges)


def test_nextjs_pages_index_root(tmp_path: Path):
    p = _write(tmp_path, "pages/index.tsx", "export default function H(){return null}\n")
    nodes, _ = js_ext.extract_file(p, "pages/index.tsx")
    assert any(n.id == "route:GET:/" for n in nodes)


def test_nextjs_app_router(tmp_path: Path):
    p = _write(tmp_path, "app/dashboard/page.tsx", "export default function D(){return null}\n")
    nodes, _ = js_ext.extract_file(p, "app/dashboard/page.tsx")
    ids = {n.id for n in nodes}
    assert "route:GET:/dashboard" in ids


def test_nextjs_catchall_segment(tmp_path: Path):
    p = _write(tmp_path, "pages/blog/[...slug].tsx", "export default function B(){return null}\n")
    nodes, _ = js_ext.extract_file(p, "pages/blog/[...slug].tsx")
    assert any(n.id == "route:GET:/blog/{slug*}" for n in nodes)


def test_nextjs_private_files_skipped(tmp_path: Path):
    p = _write(tmp_path, "pages/_app.tsx", "export default function A(){return null}\n")
    nodes, _ = js_ext.extract_file(p, "pages/_app.tsx")
    assert not any(n.kind == "route" for n in nodes)


def test_vue_router_object_routes(tmp_path: Path):
    src = (
        '<script>\n'
        'import { createRouter } from "vue-router";\n'
        'const routes = [\n'
        '  { path: "/profile", component: Profile },\n'
        '  { path: "/about", component: About },\n'
        '];\n'
        'export default createRouter({ routes });\n'
        '</script>\n'
    )
    p = _write(tmp_path, "src/router.vue", src)
    nodes, _ = js_ext.extract_file(p, "src/router.vue")
    ids = {n.id for n in nodes}
    assert "route:GET:/profile" in ids
    assert "route:GET:/about" in ids


def test_default_export_view(tmp_path: Path):
    src = "export default function Login() { return null; }\n"
    p = _write(tmp_path, "src/Login.tsx", src)
    nodes, _ = js_ext.extract_file(p, "src/Login.tsx")
    assert any(n.id == "view:src/Login.tsx#default" for n in nodes)


def test_unreadable_file_returns_empty(tmp_path: Path):
    p = tmp_path / "missing.tsx"
    nodes, edges = js_ext.extract_file(p, "missing.tsx")
    assert nodes == [] and edges == []


def test_vue_without_script_block_returns_empty(tmp_path: Path):
    p = _write(tmp_path, "x.vue", "<template><div/></template>\n")
    nodes, edges = js_ext.extract_file(p, "x.vue")
    assert nodes == [] and edges == []


# ---------------------------------------------------------------------------
# Edge cases for full coverage
# ---------------------------------------------------------------------------


def test_nextjs_pages_non_route_file_extension(tmp_path):
    """Test pages/ file with non-matching extension (line 100)."""
    p = _write(tmp_path, "pages/styles.css", "body{}\n")
    nodes, _ = js_ext.extract_file(p, "pages/styles.css")
    assert nodes == [] or all(n.kind != "route" for n in nodes)


def test_nextjs_pages_json_extension_skipped(tmp_path):
    """Test pages/ file with .json extension triggers line 100 branch."""
    p = _write(tmp_path, "pages/data.json", '{"x":1}\n')
    nodes, _ = js_ext.extract_file(p, "pages/data.json")
    # JSON files won't be parsed anyway, but relpath triggers fs-routing check
    assert all(n.kind != "route" for n in nodes)


def test_nextjs_pages_root_with_no_subpath(tmp_path):
    # Edge case: "pages" with no following segment doesn't match.
    p = _write(tmp_path, "src/pages_helper.ts", "export const x = 1;\n")
    nodes, _ = js_ext.extract_file(p, "src/pages_helper.ts")
    assert all(n.kind != "route" for n in nodes)


def test_nextjs_app_router_root_page(tmp_path):
    p = _write(tmp_path, "app/page.tsx", "export default function H(){return null}\n")
    nodes, _ = js_ext.extract_file(p, "app/page.tsx")
    assert any(n.id == "route:GET:/" for n in nodes)


def test_react_route_without_path_attr_skipped(tmp_path):
    src = (
        'import {Routes, Route} from "react-router-dom";\n'
        "function App() { return <Route element={<X />} />; }\n"
    )
    p = _write(tmp_path, "src/App.tsx", src)
    nodes, _ = js_ext.extract_file(p, "src/App.tsx")
    assert all(n.kind != "route" for n in nodes)
