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

from taxonomy import infer_layer, is_test_path, precision_of, ROUTE_DECORATOR_RE  # noqa: E402
import py_extract as px  # noqa: E402  (Python, via tree-sitter)
from js_ts_extract import find_js_files, extract_js_files, frontend_degraded   # noqa: E402
from ts_extract import find_lang_files, extract_lang_files  # noqa: E402  (Java/Go/C#, via tree-sitter)

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data"}


def iter_py_files(src: str):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def _base_nodes(cls):
    """Base-class expressions of a class definition (`ast`'s `cls.bases`)."""
    args = px.field(cls, "superclasses")
    if args is None:
        return []
    return [c for c in args.named_children if c.type != "keyword_argument"]


def _self_attr_types(cls) -> dict[str, str]:
    """Map self.<attr> -> ClassName using __init__ annotations/assignments and
    class-level annotated attributes."""
    types: dict[str, str] = {}
    body = px.body_of(cls)
    if body is None:
        return types

    # Class-level annotated attributes:  service: OrderService
    for targets, _value, annotation in px.assignments(body):
        if annotation is None:
            continue
        target = targets[0] if targets else None
        if target is not None and target.type == "identifier":
            t = px.annotation_type(annotation)
            if t:
                types[px.text(target)] = t

    init = next((m for _decs, m in px.defs_in(body) if px.def_name(m) == "__init__"), None)
    if init is None:
        return types

    param_types = px.param_annotations(init)

    for targets, value, annotation in px.assignments(init):
        for tgt in targets:
            attr = px.self_attr_name(tgt)
            if not attr:
                continue
            # self.attr: OrderService = ...
            if annotation is not None:
                t = px.annotation_type(annotation)
                if t:
                    types[attr] = t
                continue
            # self.attr = param  /  self.attr = SomeClass()
            if value is None:
                continue
            if value.type == "identifier" and param_types.get(px.text(value)):
                types[attr] = param_types[px.text(value)]
            elif value.type == "call":
                ctor = px.name_of(px.field(value, "function"))
                if ctor and ctor[:1].isupper():
                    types[attr] = ctor
    return types


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
        call = d.named_children[0] if d.named_children else None
        if call is None or call.type != "call":
            continue
        # @router.post(...) as well as a bare `@get(...)` imported from the framework.
        func = px.field(call, "function")
        if func is None:
            continue
        if func.type == "attribute":
            verb = px.text(px.field(func, "attribute")).lower()
        elif func.type == "identifier":
            verb = px.text(func).lower()
        else:
            continue
        args = px.call_args(call)
        path = px.string_value(args[0]) if args else ""
        if not path:
            continue
        if verb in HTTP_VERBS:
            routes.append({"method": verb.upper(), "path": path})
        elif verb in ("route", "add_url_rule"):
            methods = [m.upper() for m in px.sequence_strings(px.call_keywords(call).get("methods"))]
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
    # Deferred call sites, resolved in pass 2:  (caller_id, class_ctx, ctx, node)
    pending: list[tuple[str, str | None, dict, object]] = []

    for path, root in _iter_sources(roots):
        try:
            raw = px.read_source(path)
        except OSError as exc:
            print(f"  ! skipped {path}: {exc}", file=sys.stderr)
            continue
        tree = px.parse(raw)
        if tree is None:
            px.warn_missing()
            continue
        rel = _rel_source(path, root)
        root_node = tree.root_node

        for cls_decos_nodes, cls in px.defs_in(root_node, ("class_definition",)):
            cls_name = px.def_name(cls)
            cls_decos = [px.name_of(d.named_children[0]) if d.named_children else ""
                         for d in cls_decos_nodes]
            cls_bases = [px.name_of(b) for b in _base_nodes(cls)]
            layer = infer_layer(cls_name, cls_decos, cls_bases)
            attr_types = _self_attr_types(cls)
            class_methods.setdefault(cls_name, set())

            for m_decos, m in px.defs_in(px.body_of(cls)):
                m_name = px.def_name(m)
                node_id = f"{cls_name}.{m_name}"
                class_methods[cls_name].add(m_name)
                decos = [px.name_of(d.named_children[0]) if d.named_children else ""
                         for d in m_decos]
                routes = _route_of(m_decos)
                is_endpoint = bool(routes) or layer == "controller" or any(ROUTE_DECORATOR_RE.search(d) for d in decos)
                doc = px.docstring_of(m)
                code = px.text(m)
                # `ast` walked decorators as part of the function but reported the
                # source segment from `def` onward. Both are kept: `outer` for the
                # walk, `m` for the text, so `ext` counts and hashes both match.
                outer = m.parent if m_decos else m
                methods[node_id] = {
                    "id": node_id, "name": m_name, "cls": cls_name, "layer": layer,
                    "kind": "endpoint" if is_endpoint else "method",
                    "signature": px.signature(m),
                    "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                    "source": f"{rel}:{px.line(m)}", "end": px.end_line(m),
                    "calls": [], "callers": [],
                    "hash": _hash(code), "code": code, "routes": routes,
                }
                local_types = _local_types(outer, attr_types, decl=m)
                pending.append((node_id, cls_name, {"attr_types": attr_types, "local_types": local_types}, outer))

        for fn_decos, fn in px.defs_in(root_node):
            fn_name = px.def_name(fn)
            node_id = fn_name
            func_nodes[fn_name] = node_id
            doc = px.docstring_of(fn)
            code = px.text(fn)
            # Flask's normal shape is @app.route on a module-level def, not on a
            # class method -- so a whole framework was invisible until this loop
            # asked the same question the class loop already asked.
            routes = _route_of(fn_decos)
            outer = fn.parent if fn_decos else fn
            methods[node_id] = {
                "id": node_id, "name": fn_name, "cls": None,
                "layer": "controller" if routes else "function",
                "kind": "endpoint" if routes else "function", "signature": px.signature(fn),
                "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                "source": f"{rel}:{px.line(fn)}", "end": px.end_line(fn),
                "calls": [], "callers": [],
                "hash": _hash(code), "code": code, "routes": routes,
            }
            local_types = _local_types(outer, {}, decl=fn)
            pending.append((node_id, None, {"attr_types": {}, "local_types": local_types}, outer))

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

    # --- Java / Go / C#: same graph, same shape ---
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

    # `precision` needs the edges, so it is computed here rather than at extraction:
    # two of its three reasons are properties of what a node *calls*, not of the
    # node itself.
    for src_id, dst_id, _type in edges:
        methods[src_id]["calls"].append(dst_id)
        methods[dst_id]["callers"].append(src_id)
    for info in methods.values():
        info["calls"] = sorted(set(info["calls"]))
        info["callers"] = sorted(set(info["callers"]))
    for info in methods.values():
        reasons = precision_of(info, [methods[c] for c in info["calls"] if c in methods])
        if reasons:
            info["precision"] = reasons

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
        "source": f"{rel}:{data.get('line', 0)}", "end": data.get("endLine", 0),
        "calls": [], "callers": [],
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
    """A Java/Go/C# flow node. Same shape as `_js_node`.

    It used to carry `approx: True`, which was honest while these three were read
    textually and became arbitrary once every language moved to tree-sitter --
    Python and JS/TS resolve no more completely. The caveat is now stated once for
    every language (`taxonomy.PRECISION_CAVEAT`) and what survives per node is
    `precision`, a list of losses that can actually be named.
    """
    doc = (data.get("doc") or "").strip()
    calls = data.get("calls") or []
    content = json.dumps({"n": name, "c": sorted(f'{c["type"]}.{c["name"]}' for c in calls),
                          "d": doc}, sort_keys=True)
    params = data.get("params") or {}
    node = {
        "id": nid, "name": name, "cls": cls, "layer": layer, "kind": kind,
        "signature": f'{name}({", ".join(sorted(params))})',
        "doc": doc.splitlines()[0] if doc else "",
        "source": f'{rel}:{data.get("line", 0)}', "end": data.get("endLine", 0),
        "calls": [], "callers": [],
        "hash": _hash(content), "code": f"// {rel}\n{name}(...)", "lang": lang,
        "routes": _dedupe_routes(data.get("routes") or []),
    }
    if data.get("declaration"):
        # A signature with no body: it exists so calls through the declared type
        # resolve, but there is no code in it to measure, clone or call dead.
        node["declaration"] = True
    return node


def _analyze_lang(roots: list[str]):
    """Java/Go/C# nodes and call edges.

    Two passes for the same reason the Python analyzer needs two: a call can only
    be resolved once every class and its method names are known. `ts_extract`
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
                    node = _lang_node(nid, m["name"], cls["name"],
                                      "controller" if routed else layer,
                                      "endpoint" if routed else "method",
                                      m, rel, lang)
                    prev = methods.get(nid)
                    if prev is not None:
                        # Overloads share one node id -- the id scheme carries no
                        # arity. Keep one node, but record every signature that
                        # folded into it rather than silently showing the last.
                        node["signatures"] = ((prev.get("signatures") or [prev["signature"]])
                                              + [node["signature"]])
                    methods[nid] = node
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


def _local_types(fn, seed: dict[str, str], decl=None) -> dict[str, str]:
    """Local variable -> ClassName from param annotations and `x = SomeClass()`.

    `fn` is the node to walk and `decl` the definition whose parameters to read.
    They differ for a decorated function: `ast` folded decorators into the node it
    walked, so the walk has to start at the wrapper to count the same call sites,
    while the parameters only exist on the definition inside it.
    """
    types = dict(seed)
    types.update({k: v for k, v in px.param_annotations(decl if decl is not None else fn).items() if v})
    for targets, value, _annotation in px.assignments(fn):
        if value is None or value.type != "call":
            continue
        ctor = px.name_of(px.field(value, "function"))
        if ctor and ctor[:1].isupper():
            for tgt in targets:
                if tgt.type == "identifier":
                    types[px.text(tgt)] = ctor
    return types


def _resolve_calls(fn, cls_ctx, ctx, methods, class_methods, func_nodes) -> tuple[set[str], int]:
    """Returns (in-graph call targets, number of call sites that stayed external)."""
    attr_types, local_types = ctx["attr_types"], ctx["local_types"]
    found: set[str] = set()
    sites = 0

    def exists(cls_name, method):
        return cls_name in class_methods and method in class_methods[cls_name]

    for node in px.calls_in(fn):
        target = None
        func = px.field(node, "function")
        if func is None:
            continue
        if func.type == "attribute":
            method = px.text(px.field(func, "attribute"))
            base = px.field(func, "object")
            base_name = px.text(base) if base is not None and base.type == "identifier" else ""
            # self.attr.method()
            if px.is_self_attr(base):
                cls_name = attr_types.get(px.self_attr_name(base))
                if cls_name and exists(cls_name, method):
                    target = f"{cls_name}.{method}"
            # self.method()
            elif base_name == "self" and cls_ctx:
                if exists(cls_ctx, method):
                    target = f"{cls_ctx}.{method}"
            # <var>.method()  where var is a typed param/local
            elif base_name in local_types:
                cls_name = local_types[base_name]
                if exists(cls_name, method):
                    target = f"{cls_name}.{method}"
        elif func.type == "identifier":
            # bare function call to a known module function
            if px.text(func) in func_nodes:
                target = func_nodes[px.text(func)]
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
        prec = info.get("precision") or []
        prec_md = f"precision: {', '.join(prec)}\n" if prec else ""
        decl_md = "declaration: true\n" if info.get("declaration") else ""
        # An overload pair shares one id, so the note lists what folded into it --
        # otherwise the single signature shown looks like the only one there is.
        sigs = info.get("signatures") or []
        sig_md = "\n".join(f"`{s}`" for s in sigs) if sigs else f"`{info['signature']}`"
        page = (
            f"---\n"
            f"entity: {info['id']}\n"
            f"kind: {info['kind']}\n"
            f"layer: {info['layer']}\n"
            f"class: {info['cls'] or ''}\n"
            f"source: {info['source']}\n"
            f"lang: {info.get('lang', 'py')}\n"
            f"{prec_md}"
            f"{decl_md}"
            f"desc_source: {info.get('desc_source', 'auto')}\n"
            f"---\n"
            f"# {info['id']}\n\n"
            f"## What it does\n{info.get('summary', '')}\n\n"
            f"## Signature\n{sig_md}\n\n"
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
                "source": i["source"], "end": i.get("end", 0),
                "lang": i.get("lang", "py"),
                "ext": i.get("ext", 0)}  # call sites that leave the graph (libs/stdlib)
        if i.get("http"):
            node["http"] = i["http"]
        if i.get("routes"):
            node["routes"] = i["routes"]
        if i.get("precision"):
            # Named precision losses. Absent means nothing *nameable* was lost --
            # never that the edges are complete, which PRECISION_CAVEAT says.
            node["precision"] = i["precision"]
        if i.get("declaration"):
            node["declaration"] = True   # signature only; no body to measure or run
        if i.get("signatures"):
            node["signatures"] = i["signatures"]   # overloads folded into one id
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
