"""Python flow-graph extractor (FastAPI / Flask / Django).

Uses only the standard library :mod:`ast` module.  The goal is *recall over
precision*: we recognise common decorator shapes used by FastAPI, Flask, and
Django (the ``urlpatterns`` list with ``path()`` / ``re_path()`` calls).
Anything more exotic is left to manual ``Route`` declarations in
``playwright-god.toml``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..flow_graph import Edge, Evidence, Node, Route

# FastAPI: @app.get("/x") / @router.post("/x")
# Flask:   @app.route("/x", methods=["POST"])
# Django:  path("x/", view), re_path(r"^x/$", view)


_FASTAPI_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def extract_file(path: Path, rel: str) -> tuple[list[Node], list[Edge]]:
    """Return (nodes, edges) parsed from a single Python source file.

    Parser failures (syntax errors) yield empty lists; never raises.
    """

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [], []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return [], []

    nodes: list[Node] = []
    edges: list[Edge] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                routes = _routes_from_decorator(deco, node, rel)
                nodes.extend(routes)
        elif isinstance(node, ast.Assign) and _is_urlpatterns(node):
            nodes.extend(_routes_from_urlpatterns(node, rel))

    return nodes, edges


# ---------------------------------------------------------------------------
# Decorator-based extraction (FastAPI + Flask)
# ---------------------------------------------------------------------------


def _routes_from_decorator(
    deco: ast.expr,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    rel: str,
) -> list[Route]:
    call = deco if isinstance(deco, ast.Call) else None
    if call is None:
        return []
    func_attr = call.func
    method_name: str | None = None
    if isinstance(func_attr, ast.Attribute):
        method_name = func_attr.attr.lower()
    elif isinstance(func_attr, ast.Name):
        method_name = func_attr.id.lower()
    if method_name is None:
        return []

    path_value = _first_string_arg(call)
    if path_value is None:
        return []

    handler = func.name
    line = getattr(func, "lineno", 1)
    end_line = getattr(func, "end_lineno", line) or line
    evidence = (Evidence(file=rel, line_range=(line, end_line)),)

    if method_name in _FASTAPI_METHODS:
        return [Route(method=method_name.upper(), path=path_value,
                      handler=handler, evidence=evidence)]

    if method_name == "route":
        # Flask: @app.route("/x", methods=["POST"])
        methods = _methods_from_kwargs(call) or ("GET",)
        return [Route(method=m.upper(), path=path_value, handler=handler,
                      evidence=evidence) for m in methods]
    return []


def _first_string_arg(call: ast.Call) -> str | None:
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _methods_from_kwargs(call: ast.Call) -> list[str]:
    for kw in call.keywords:
        if kw.arg != "methods":
            continue
        if isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
            out: list[str] = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.append(elt.value)
            return out
    return []


# ---------------------------------------------------------------------------
# Django urlpatterns
# ---------------------------------------------------------------------------


def _is_urlpatterns(assign: ast.Assign) -> bool:
    for target in assign.targets:
        if isinstance(target, ast.Name) and target.id == "urlpatterns":
            return True
    return False


def _routes_from_urlpatterns(assign: ast.Assign, rel: str) -> list[Route]:
    if not isinstance(assign.value, (ast.List, ast.Tuple)):
        return []
    routes: list[Route] = []
    for elt in assign.value.elts:
        route = _route_from_path_call(elt, rel)
        if route is not None:
            routes.append(route)
    return routes


def _route_from_path_call(call_node: ast.expr, rel: str) -> Route | None:
    if not isinstance(call_node, ast.Call):
        return None
    func = call_node.func
    name: str | None = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name not in {"path", "re_path", "url"}:
        return None
    if not call_node.args:
        return None
    first = call_node.args[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None
    raw_path = first.value
    # Normalise to a leading slash so route IDs are consistent across frameworks.
    norm_path = raw_path if raw_path.startswith("/") else f"/{raw_path}"
    handler = _stringify_handler(call_node.args[1]) if len(call_node.args) > 1 else ""
    line = getattr(call_node, "lineno", 1)
    end_line = getattr(call_node, "end_lineno", line) or line
    evidence = (Evidence(file=rel, line_range=(line, end_line)),)
    # Django path()s are method-agnostic; record as ANY (the conventional
    # route ID for "all verbs match this URL").
    return Route(method="ANY", path=norm_path, handler=handler, evidence=evidence)


def _stringify_handler(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        prefix = _stringify_handler(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _stringify_handler(node.func)
    return ""


__all__ = ["extract_file"]
