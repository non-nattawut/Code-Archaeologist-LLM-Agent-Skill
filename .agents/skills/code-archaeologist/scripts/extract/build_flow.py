#!/usr/bin/env python3
"""build_flow.py — Method-level call / request-flow analyzer.

Where build_wiki.py maps *structure* (which classes reference which), this maps
*behavior*: it resolves method-to-method calls into a call graph so you can trace
an actual request flow, e.g.

    OrderController.create_order -> OrderService.place_order -> OrderRepository.save

Each node is a method/function and carries a description of what it does, its
signature, and its callers/callees. Controller methods are marked as `endpoint`
roots so request flows have a clear entry point.

Outputs (deterministic, zero dependencies, Python 3.10+):
  data/flow_graph.json   nodes (methods) + edges (calls)
  data/flow/<Node>.md    one note per method/function, with [[wikilinks]]

Call resolution is heuristic (no type inference engine):
  - self.<attr>.m()  -> attr type from __init__ annotations / assignments
  - <param>.m()      -> param type from the method's own annotations
  - <local>.m()      -> local assigned via `x = SomeClass()`
  - self.m() / m()   -> same class / known module function
Unresolved (external/stdlib) calls are dropped to keep the graph readable.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_FLOW_DIR = os.path.join(DATA_DIR, "flow", "notes")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
# Persistent cache of AI-written summaries, keyed by node id -> {hash, summary}.
DESCRIPTIONS_PATH = os.path.join(CACHE_DIR, "descriptions.json")
# Transient list of nodes that still need an AI summary (agent fills these in).
PENDING_PATH = os.path.join(CACHE_DIR, "pending_descriptions.json")


def _hash(code: str) -> str:
    return hashlib.sha1((code or "").encode("utf-8")).hexdigest()[:12]


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return default


def _save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")

from taxonomy import infer_layer, is_test_path, ROUTE_DECORATOR_RE  # noqa: E402
from js_bridge import find_js_files, extract_js_files, frontend_degraded   # noqa: E402
from lang_extract import find_lang_files, extract_lang_files  # noqa: E402  (Java/Go/C#, approximate)

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data"}


def iter_py_files(src: str):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def _name_of(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    return ""


def _annotation_type(ann) -> str:
    """Return a bare class name from a type annotation, if simple."""
    if ann is None:
        return ""
    if isinstance(ann, ast.Name):
        return ann.id
    if isinstance(ann, ast.Attribute):
        return ann.attr
    if isinstance(ann, ast.Subscript):  # e.g. Optional[Foo], List[Foo]
        return _annotation_type(ann.slice)
    return ""


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        return f"{fn.name}({ast.unparse(fn.args)})"
    except Exception:
        return f"{fn.name}(...)"


def _self_attr_types(cls: ast.ClassDef) -> dict[str, str]:
    """Map self.<attr> -> ClassName using __init__ annotations/assignments and
    class-level annotated attributes."""
    types: dict[str, str] = {}

    # Class-level annotated attributes:  service: OrderService
    for item in cls.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            t = _annotation_type(item.annotation)
            if t:
                types[item.target.id] = t

    init = next((n for n in cls.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__init__"), None)
    if not init:
        return types

    param_types = {a.arg: _annotation_type(a.annotation) for a in init.args.args if a.annotation}

    for node in ast.walk(init):
        # self.attr: OrderService = ...
        if isinstance(node, ast.AnnAssign) and _is_self_attr(node.target):
            t = _annotation_type(node.annotation)
            if t:
                types[node.target.attr] = t
        # self.attr = param  /  self.attr = SomeClass()
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if _is_self_attr(tgt):
                    attr = tgt.attr
                    val = node.value
                    if isinstance(val, ast.Name) and val.id in param_types and param_types[val.id]:
                        types[attr] = param_types[val.id]
                    elif isinstance(val, ast.Call):
                        ctor = _name_of(val.func)
                        if ctor and ctor[:1].isupper():
                            types[attr] = ctor
    return types


def _is_self_attr(node) -> bool:
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self"


HTTP_VERBS = {"get", "post", "put", "patch", "delete"}


def _route_of(decorators: list) -> list[dict]:
    """Every {method, path} a set of decorators declares.

    A list, not a single route, because one handler routinely serves several: Flask
    writes `@app.route("/orders", methods=["GET", "POST"])`, and stacking two
    decorators on one function is normal in every framework here. Returning only
    the first match silently dropped the rest, so a POST to a handler that also
    accepts GET never linked to its frontend caller.
    """
    routes: list[dict] = []
    for d in decorators:
        if not isinstance(d, ast.Call):
            continue
        # @router.post(...) as well as a bare `@get(...)` imported from the framework.
        if isinstance(d.func, ast.Attribute):
            verb = d.func.attr.lower()
        elif isinstance(d.func, ast.Name):
            verb = d.func.id.lower()
        else:
            continue
        path = None
        if d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str):
            path = d.args[0].value
        if not path:
            continue
        if verb in HTTP_VERBS:
            routes.append({"method": verb.upper(), "path": path})
        elif verb in ("route", "add_url_rule"):
            methods = []
            for kw in d.keywords:
                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    methods = [str(e.value).upper() for e in kw.value.elts
                               if isinstance(e, ast.Constant)]
            for method in (methods or ["GET"]):
                routes.append({"method": method, "path": path})
    return _dedupe_routes(routes)


def _dedupe_routes(routes: list[dict]) -> list[dict]:
    """Unique routes in a fixed order (constraint 2: same source, same bytes)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for r in sorted(routes, key=lambda r: (r["path"], r["method"])):
        key = (r["method"], r["path"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _norm_path(path: str) -> str:
    """Normalize a URL/route path so every framework's param syntax compares equal.

    Handles `:id` (Express/Nest), `{id}` (FastAPI), `<id>` and `<int:id>` (Flask),
    and Nest's optional `:id?`. A query string is not part of the route.
    """
    path = path.split("?", 1)[0]        # a query string is not part of the route
    segs = []
    for seg in path.strip("/").split("/"):
        if not seg:
            continue
        if seg.startswith(":") or (seg.startswith("{") and seg.endswith("}")) \
                or (seg.startswith("<") and seg.endswith(">")) or seg.startswith("*"):
            segs.append("*")
        else:
            segs.append(seg)
    return "/" + "/".join(segs)


def _api_edges(methods: dict) -> set[tuple[str, str]]:
    """Link frontend HTTP calls to backend route handlers (method + path match).

    Exact `(METHOD, path)` first. Failing that, one documented fallback: a route
    whose path is a *suffix* of the call's, and only when exactly one route
    matches. That is what makes a mount prefix work -- a frontend `/api/orders`
    reaching a handler registered as `/orders` under an `/api` mount -- without
    guessing when two routes could both be meant.
    """
    routes: dict[tuple[str, str], list[str]] = {}
    for nid, info in methods.items():
        for r in info.get("routes") or []:
            routes.setdefault((r["method"].upper(), _norm_path(r["path"])), []).append(nid)

    edges: set[tuple[str, str]] = set()
    for nid, info in methods.items():
        for h in info.get("http") or []:
            method, url = h["method"].upper(), _norm_path(h["url"])
            owners = _owners(routes, method, url) or _suffix_match(routes, method, url)
            if owners and len(owners) == 1 and owners[0] != nid:
                edges.add((nid, owners[0]))
    return edges


def _owners(routes: dict, method: str, path: str) -> list[str]:
    """Handlers registered for `path`, counting the ones registered for every verb.

    A framework can register a path without naming a verb -- Go's
    `mux.HandleFunc("/orders", h)` serves all of them -- which `_route_of` records
    as the verb `ANY`. Such a route really does answer this call, so it is a match,
    not a near miss.
    """
    return (routes.get((method, path)) or []) + (routes.get(("ANY", path)) or [])


def _suffix_match(routes: dict, method: str, url: str) -> list[str] | None:
    """Routes whose path is a trailing run of *whole segments* of `url`, same verb.

    Segment-aligned on purpose: `/api/orders` matches a route `/orders`, but
    `/myorders` must not.
    """
    parts = url.strip("/").split("/")
    candidates = {"/" + "/".join(parts[i:]) for i in range(1, len(parts))}
    hits: list[str] = []
    for suffix in candidates:
        hits.extend(_owners(routes, method, suffix))
    return sorted(set(hits)) or None


def _rel_source(path: str, root: str) -> str:
    """Path relative to its root, prefixed with the root's name so monorepo
    areas (backend/… vs frontend/…) are distinguishable in the graph."""
    rel = os.path.relpath(path, root).replace("\\", "/")
    return f"{os.path.basename(os.path.normpath(root))}/{rel}"


def _iter_sources(roots: list[str]):
    for root in roots:
        for path in iter_py_files(root):
            yield path, root


def analyze(roots: list[str]):
    """Two-pass analysis across one or more source roots (Python + JS/TS)."""
    methods: dict[str, dict] = {}          # node_id -> info
    class_methods: dict[str, set[str]] = {}  # ClassName -> {method names}
    func_nodes: dict[str, str] = {}         # module function name -> node_id
    # Deferred call sites, resolved in pass 2:  (caller_id, class_ctx, fn_ast)
    pending: list[tuple[str, str | None, dict, ast.AST]] = []

    for path, root in _iter_sources(roots):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src_text = fh.read()
            tree = ast.parse(src_text, filename=path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"  ! skipped {path}: {exc}", file=sys.stderr)
            continue
        rel = _rel_source(path, root)

        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            cls_decos = [_name_of(d) for d in cls.decorator_list]
            cls_bases = [_name_of(b) for b in cls.bases]
            layer = infer_layer(cls.name, cls_decos, cls_bases)
            attr_types = _self_attr_types(cls)
            class_methods.setdefault(cls.name, set())

            for m in [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                node_id = f"{cls.name}.{m.name}"
                class_methods[cls.name].add(m.name)
                decos = [_name_of(d) for d in m.decorator_list]
                routes = _route_of(m.decorator_list)
                is_endpoint = bool(routes) or layer == "controller" or any(ROUTE_DECORATOR_RE.search(d) for d in decos)
                doc = ast.get_docstring(m) or ""
                code = ast.get_source_segment(src_text, m) or ""
                methods[node_id] = {
                    "id": node_id, "name": m.name, "cls": cls.name, "layer": layer,
                    "kind": "endpoint" if is_endpoint else "method",
                    "signature": _signature(m),
                    "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                    "source": f"{rel}:{m.lineno}", "calls": [], "callers": [],
                    "hash": _hash(code), "code": code, "routes": routes,
                }
                local_types = _local_types(m, attr_types)
                pending.append((node_id, cls.name, {"attr_types": attr_types, "local_types": local_types}, m))

        for fn in [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            node_id = fn.name
            func_nodes[fn.name] = node_id
            doc = ast.get_docstring(fn) or ""
            code = ast.get_source_segment(src_text, fn) or ""
            # Flask's normal shape is @app.route on a module-level def, not on a
            # class method -- so a whole framework was invisible until this loop
            # asked the same question the class loop already asked.
            routes = _route_of(fn.decorator_list)
            methods[node_id] = {
                "id": node_id, "name": fn.name, "cls": None,
                "layer": "controller" if routes else "function",
                "kind": "endpoint" if routes else "function", "signature": _signature(fn),
                "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                "source": f"{rel}:{fn.lineno}", "calls": [], "callers": [],
                "hash": _hash(code), "code": code, "routes": routes,
            }
            local_types = _local_types(fn, {})
            pending.append((node_id, None, {"attr_types": {}, "local_types": local_types}, fn))

    # --- Pass 2: resolve Python call edges ---  (edges carry a type)
    edges: set[tuple[str, str, str]] = set()
    for caller_id, cls_ctx, ctx, fn in pending:
        targets, external = _resolve_calls(fn, cls_ctx, ctx, methods, class_methods, func_nodes)
        methods[caller_id]["ext"] = external
        for target in targets:
            if target != caller_id:
                edges.add((caller_id, target, "calls"))

    # --- Frontend (JS/TS): merge nodes + call edges into the same graph ---
    js_methods, js_edges = _analyze_js(roots)
    methods.update(js_methods)
    for s, t in js_edges:
        if s in methods and t in methods and s != t:
            edges.add((s, t, "calls"))

    # --- Java / Go / C#: the approximate tier, same graph, marked as approximate ---
    lang_methods, lang_edges = _analyze_lang(roots)
    methods.update(lang_methods)
    for s, t in lang_edges:
        if s in methods and t in methods and s != t:
            edges.add((s, t, "calls"))

    # Test code gets its own layer, in one pass so both extractors agree. It is not
    # application code, and analyze.py must not count it as dead: a runner calls it.
    for info in methods.values():
        if is_test_path(info.get("source") or ""):
            info["layer"] = "test"

    # --- Cross-stack: link frontend HTTP calls to backend route handlers ---
    for s, t in _api_edges(methods):
        edges.add((s, t, "http"))

    for src_id, dst_id, _type in edges:
        methods[src_id]["calls"].append(dst_id)
        methods[dst_id]["callers"].append(src_id)
    for info in methods.values():
        info["calls"] = sorted(set(info["calls"]))
        info["callers"] = sorted(set(info["callers"]))

    return methods, sorted(edges)


def _js_node(nid: str, name: str, cls, layer: str, kind: str, data: dict, rel: str) -> dict:
    doc = (data.get("doc") or "").strip()
    http = data.get("http", [])
    calls = data.get("calls", [])
    content = json.dumps({"n": name, "c": sorted(calls), "h": http, "d": doc}, sort_keys=True)
    code = (f"// {rel}\n{name}(...) calls {', '.join(calls) or 'nothing'}"
            + (f"; http {http}" if http else ""))
    return {
        "id": nid, "name": name, "cls": cls, "layer": layer, "kind": kind,
        "signature": f"{name}()",
        "doc": doc.splitlines()[0] if doc else "",
        "source": f"{rel}:{data.get('line', 0)}", "calls": [], "callers": [],
        "hash": _hash(content), "code": code, "http": http, "lang": "js",
        "routes": _dedupe_routes(data.get("routes") or []),
    }


def _attach_routes(routes: list[dict], methods: dict, raw_calls: list, make_node) -> None:
    """Router registrations -> the handler's node, or an endpoint node of their own.

    Express (`router.post("/x", h)`) and Go (`mux.HandleFunc("POST /x", h)`) register
    routes the same way and so are read the same way: a named handler attaches its
    route to that function's own node; an inline literal has no node to attach to,
    so the registration itself becomes the endpoint ("POST /orders").
    """
    for r in routes:
        handler = r.get("handler")
        route = {"method": r["method"], "path": r["path"]}
        if handler and handler in methods:
            methods[handler]["routes"] = _dedupe_routes(methods[handler]["routes"] + [route])
            methods[handler]["kind"] = "endpoint"
            methods[handler]["layer"] = "controller"
        elif not handler:
            nid = f'{r["method"]} {r["path"]}'
            node = make_node(nid, dict(r, routes=[route]))
            node["signature"] = nid    # the route is the signature; `nid()` reads as nonsense
            methods[nid] = node
            raw_calls.append((nid, r.get("calls", [])))


def _analyze_js(roots: list[str]):
    """Extract JS/TS functions/methods as flow nodes and resolve their calls."""
    methods: dict[str, dict] = {}
    func_nodes: set[str] = set()
    raw_calls: list[tuple[str, list[str]]] = []

    for root in roots:
        for res in extract_js_files(find_js_files(root)):
            rel = _rel_source(res["file"], root)
            stem = os.path.splitext(os.path.basename(res["file"]))[0]
            for fn in res.get("functions", []):
                nid = fn["name"]
                # A function that returns JSX is a React component in both maps --
                # one meaning, one kind, whichever map you are reading.
                component = bool(fn.get("jsx"))
                methods[nid] = _js_node(nid, fn["name"], None,
                                        "ui" if component else infer_layer(f'{fn["name"]} {stem}'),
                                        "component" if component else "function", fn, rel)
                func_nodes.add(nid)
                raw_calls.append((nid, fn.get("calls", [])))
            for cls in res.get("classes", []):
                # Nest hands us real decorator names (@Controller, @Injectable), which
                # is better evidence of a layer than the class name and file stem that
                # were all a JS class used to offer.
                layer = infer_layer(f'{cls["name"]} {stem}', cls.get("decorators", []))
                for m in cls.get("methods", []):
                    nid = f'{cls["name"]}.{m["name"]}'
                    routed = bool(m.get("routes"))
                    methods[nid] = _js_node(nid, m["name"], cls["name"],
                                            "controller" if routed else layer,
                                            "endpoint" if routed else "method", m, rel)
                    raw_calls.append((nid, m.get("calls", [])))

            _attach_routes(res.get("routes", []), methods, raw_calls,
                           lambda nid, data: _js_node(nid, nid, None, "controller",
                                                      "endpoint", data, rel))

    edges: set[tuple[str, str]] = set()
    for owner, calls in raw_calls:
        methods[owner]["ext"] = sum(1 for name in calls if name not in func_nodes)
        for name in calls:
            if name in func_nodes and name != owner:
                edges.add((owner, name))
    return methods, edges


def _lang_node(nid: str, name: str, cls, layer: str, kind: str, data: dict,
               rel: str, lang: str) -> dict:
    """A flow node from the approximate tier. Same shape as `_js_node`, plus `approx`."""
    doc = (data.get("doc") or "").strip()
    calls = data.get("calls") or []
    content = json.dumps({"n": name, "c": sorted(f'{c["type"]}.{c["name"]}' for c in calls),
                          "d": doc}, sort_keys=True)
    params = data.get("params") or {}
    return {
        "id": nid, "name": name, "cls": cls, "layer": layer, "kind": kind,
        "signature": f'{name}({", ".join(sorted(params))})',
        "doc": doc.splitlines()[0] if doc else "",
        "source": f'{rel}:{data.get("line", 0)}', "calls": [], "callers": [],
        "hash": _hash(content), "code": f"// {rel}\n{name}(...)", "lang": lang,
        "routes": _dedupe_routes(data.get("routes") or []), "approx": True,
    }


def _analyze_lang(roots: list[str]):
    """Java/Go/C# nodes and call edges — the approximate tier.

    Two passes for the same reason the Python analyzer needs two: a call can only
    be resolved once every class and its method names are known. `lang_extract`
    has already turned each receiver into a declared type; this decides whether
    that type is actually in the graph, and drops the call when it is not.
    """
    methods: dict[str, dict] = {}
    class_methods: dict[str, set[str]] = {}
    func_nodes: dict[str, str] = {}
    raw_calls: list[tuple[str, list[dict]]] = []

    for root in roots:
        for res in extract_lang_files(find_lang_files(root)):
            rel = _rel_source(res["file"], root)
            stem = os.path.splitext(os.path.basename(res["file"]))[0]
            lang = res["lang"]

            for cls in res.get("classes", []):
                layer = infer_layer(f'{cls["name"]} {stem}', cls.get("decorators", []),
                                    cls.get("bases", []))
                class_methods.setdefault(cls["name"], set())
                for m in cls.get("methods", []):
                    nid = f'{cls["name"]}.{m["name"]}'
                    class_methods[cls["name"]].add(m["name"])
                    routed = bool(m.get("routes"))
                    methods[nid] = _lang_node(nid, m["name"], cls["name"],
                                              "controller" if routed else layer,
                                              "endpoint" if routed else "method",
                                              m, rel, lang)
                    raw_calls.append((nid, m.get("calls", [])))

            for fn in res.get("functions", []):
                nid = fn["name"]
                func_nodes[fn["name"]] = nid
                methods[nid] = _lang_node(nid, fn["name"], None,
                                          infer_layer(f'{fn["name"]} {stem}'),
                                          "function", fn, rel, lang)
                raw_calls.append((nid, fn.get("calls", [])))

            _attach_routes(res.get("routes", []), methods, raw_calls,
                           lambda nid, data, rel=rel, lang=lang:
                               _lang_node(nid, nid, None, "controller", "endpoint",
                                          data, rel, lang))

    edges: set[tuple[str, str]] = set()
    for owner, calls in raw_calls:
        external = 0
        cls_ctx = methods[owner]["cls"]
        for call in calls:
            name, declared = call["name"], call["type"]
            if declared == "?":                  # receiver could not be typed
                target = None
            elif declared:
                target = f"{declared}.{name}" if name in class_methods.get(declared, ()) else None
            elif cls_ctx and name in class_methods.get(cls_ctx, ()):
                target = f"{cls_ctx}.{name}"     # bare call: same class first,
            else:
                target = func_nodes.get(name)    # then a module function
            if target and target in methods:
                if target != owner:
                    edges.add((owner, target))
            else:
                external += 1
        methods[owner]["ext"] = external
    return methods, edges


def _local_types(fn, seed: dict[str, str]) -> dict[str, str]:
    """Local variable -> ClassName from param annotations and `x = SomeClass()`."""
    types = dict(seed)
    for a in getattr(fn.args, "args", []):
        t = _annotation_type(a.annotation)
        if t:
            types[a.arg] = t
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            ctor = _name_of(node.value.func)
            if ctor and ctor[:1].isupper():
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        types[tgt.id] = ctor
    return types


def _resolve_calls(fn, cls_ctx, ctx, methods, class_methods, func_nodes) -> tuple[set[str], int]:
    """Returns (in-graph call targets, number of call sites that stayed external)."""
    attr_types, local_types = ctx["attr_types"], ctx["local_types"]
    found: set[str] = set()
    sites = 0

    def exists(cls_name, method):
        return cls_name in class_methods and method in class_methods[cls_name]

    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        target = None
        func = node.func
        if isinstance(func, ast.Attribute):
            method = func.attr
            base = func.value
            # self.attr.method()
            if _is_self_attr(base):
                cls_name = attr_types.get(base.attr)
                if cls_name and exists(cls_name, method):
                    target = f"{cls_name}.{method}"
            # self.method()
            elif isinstance(base, ast.Name) and base.id == "self" and cls_ctx:
                if exists(cls_ctx, method):
                    target = f"{cls_ctx}.{method}"
            # <var>.method()  where var is a typed param/local
            elif isinstance(base, ast.Name) and base.id in local_types:
                cls_name = local_types[base.id]
                if exists(cls_name, method):
                    target = f"{cls_name}.{method}"
        elif isinstance(func, ast.Name):
            # bare function call to a known module function
            if func.id in func_nodes:
                target = func_nodes[func.id]
        if target:
            found.add(target)
        else:
            sites += 1  # library / stdlib / unresolved: kept as a count, not an edge
    return found, sites


def _auto_summary(info: dict) -> str:
    """Deterministic fallback used until an AI summary is available."""
    if info["calls"]:
        return "Delegates to " + ", ".join(f"[[{c}]]" for c in info["calls"]) + "."
    return "_No description available._"


def resolve_descriptions(methods: dict, cache: dict) -> dict:
    """Hybrid description resolution, cheapest source first:
      1. docstring (free, authoritative)
      2. cached AI summary whose hash still matches the current source (free)
      3. deterministic auto-summary  + flag the node as needing an AI summary
    Sets info['summary'] and info['desc_source'] in place; returns the pending map.
    """
    pending: dict[str, dict] = {}
    for node_id, info in methods.items():
        if info["doc"]:
            info["summary"], info["desc_source"] = info["doc"], "docstring"
        elif node_id in cache and cache[node_id].get("hash") == info["hash"]:
            info["summary"], info["desc_source"] = cache[node_id]["summary"], "ai"
            cache[node_id]["file"] = info["source"].split(":")[0]   # scopes future pruning
        else:
            info["summary"], info["desc_source"] = _auto_summary(info), "auto"
            pending[node_id] = {
                "hash": info["hash"], "signature": info["signature"],
                "source": info["source"], "code": info["code"],
            }
    return pending


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def write_vault(methods: dict, flow_dir: str) -> None:
    os.makedirs(flow_dir, exist_ok=True)
    for fn in os.listdir(flow_dir):
        if fn.endswith(".md"):
            os.remove(os.path.join(flow_dir, fn))

    for info in methods.values():
        calls_md = "\n".join(f"- [[{c}]]" for c in info["calls"]) or "_None._"
        callers_md = "\n".join(f"- [[{c}]]" for c in info["callers"]) or "_None (entry point)._"
        http = info.get("http") or []
        http_md = "".join(f"\n## HTTP calls\n" + "\n".join(f"- `{h['method']} {h['url']}`" for h in http) + "\n"
                          if http else "")
        approx_md = "approx: true\n" if info.get("approx") else ""
        page = (
            f"---\n"
            f"entity: {info['id']}\n"
            f"kind: {info['kind']}\n"
            f"layer: {info['layer']}\n"
            f"class: {info['cls'] or ''}\n"
            f"source: {info['source']}\n"
            f"lang: {info.get('lang', 'py')}\n"
            f"{approx_md}"
            f"desc_source: {info.get('desc_source', 'auto')}\n"
            f"---\n"
            f"# {info['id']}\n\n"
            f"## What it does\n{info.get('summary', '')}\n\n"
            f"## Signature\n`{info['signature']}`\n\n"
            f"## Calls\n{calls_md}\n\n"
            f"## Called by\n{callers_md}\n"
            f"{http_md}"
        )
        with open(os.path.join(flow_dir, f"{_safe(info['id'])}.md"), "w", encoding="utf-8") as fh:
            fh.write(page)


def write_graph(methods: dict, edges, graph_path: str) -> None:
    nodes = []
    for i in sorted(methods.values(), key=lambda x: x["id"]):
        node = {"id": i["id"], "layer": i["layer"], "kind": i["kind"],
                "cls": i["cls"], "signature": i["signature"], "doc": i.get("summary", ""),
                "source": i["source"], "lang": i.get("lang", "py"),
                "ext": i.get("ext", 0)}  # call sites that leave the graph (libs/stdlib)
        if i.get("http"):
            node["http"] = i["http"]
        if i.get("routes"):
            node["routes"] = i["routes"]
        if i.get("approx"):
            node["approx"] = True     # read textually, not parsed -- see lang_extract.py
        nodes.append(node)
    graph = {"nodes": nodes,
             "edges": [{"source": s, "target": t, "type": ty} for s, t, ty in edges]}
    os.makedirs(os.path.dirname(graph_path), exist_ok=True)
    with open(graph_path, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)
        fh.write("\n")


def build(src, flow_dir: str, graph_path: str) -> int:
    roots = [os.path.abspath(s) for s in ([src] if isinstance(src, str) else src)]
    missing = [r for r in roots if not os.path.isdir(r)]
    if missing:
        print(f"error: source root(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    print(f"Analyzing call flow in {', '.join(roots)} ...")
    methods, edges = analyze(roots)
    if not methods:
        print("No methods/functions found.")
        return 0

    # Hybrid descriptions: docstring -> cached AI summary -> auto fallback.
    cache = _load_json(DESCRIPTIONS_PATH, {})
    pending = resolve_descriptions(methods, cache)
    # Prune cache entries for nodes that no longer exist (handles deletes) -- but
    # only the ones this build could actually have seen. The cache belongs to the
    # skill install, not to a project, so a build of another codebase (or one that
    # skipped the frontend) must not throw away summaries for files it never read.
    if frontend_degraded():
        print("  ! description cache left intact: this build skipped the frontend")
    else:
        seen_files = {(m.get("source") or "").split(":")[0] for m in methods.values()}
        cache = {k: v for k, v in cache.items()
                 if k in methods or v.get("file") not in seen_files}
    _save_json(DESCRIPTIONS_PATH, cache)
    if pending:
        _save_json(PENDING_PATH, pending)
    elif os.path.exists(PENDING_PATH):
        os.remove(PENDING_PATH)

    write_vault(methods, flow_dir)
    write_graph(methods, edges, graph_path)

    endpoints = [m for m in methods.values() if m["kind"] == "endpoint"]
    from_doc = sum(1 for m in methods.values() if m["desc_source"] == "docstring")
    from_ai = sum(1 for m in methods.values() if m["desc_source"] == "ai")
    scope = " (BACKEND ONLY - frontend skipped)" if frontend_degraded() else ""
    print(f"Flow: {len(methods)} node(s), {len(edges)} call edge(s), {len(endpoints)} endpoint(s){scope}")
    print(f"  descriptions: {from_doc} docstring, {from_ai} cached-AI, {len(pending)} pending")
    print(f"  graph -> {graph_path}")
    print(f"  notes -> {flow_dir}")
    if frontend_degraded():
        print("  WARNING: this graph is incomplete -- JS/TS files were not parsed, so frontend")
        print("           nodes and cross-stack edges are missing. Do not commit it as the")
        print("           project's map; install the parser and rebuild (see the warning above).")
    if pending:
        print(f"  NOTE: {len(pending)} method(s) need an AI summary. Read {PENDING_PATH},")
        print("        write a one-line summary for each, then run apply_descriptions.py and rebuild.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a method-level call/request-flow graph.")
    parser.add_argument("--src", nargs="+", default=["./src"],
                        help="One or more source roots (e.g. --src ./backend ./frontend)")
    parser.add_argument("--flow-dir", default=DEFAULT_FLOW_DIR, help="Output directory for method notes")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Output flow_graph.json path")
    args = parser.parse_args(argv)
    return build(args.src, args.flow_dir, args.graph)


if __name__ == "__main__":
    raise SystemExit(main())
