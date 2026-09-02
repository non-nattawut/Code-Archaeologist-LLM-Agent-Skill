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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_FLOW_DIR = os.path.join(DATA_DIR, "flow")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow_graph.json")
# Persistent cache of AI-written summaries, keyed by node id -> {hash, summary}.
DESCRIPTIONS_PATH = os.path.join(DATA_DIR, "descriptions.json")
# Transient list of nodes that still need an AI summary (agent fills these in).
PENDING_PATH = os.path.join(DATA_DIR, "pending_descriptions.json")


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

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data"}

LAYER_RULES = [
    (re.compile(r"controller|handler|router|resource|endpoint", re.I), "controller"),
    (re.compile(r"service|usecase|manager", re.I), "service"),
    (re.compile(r"repository|repo|dao|store|mapper", re.I), "repository"),
    (re.compile(r"model|entity|schema|dto|record", re.I), "model"),
    (re.compile(r"config|settings", re.I), "config"),
    (re.compile(r"client|gateway|adapter", re.I), "client"),
]
ROUTE_DECORATOR_RE = re.compile(r"route|get|post|put|patch|delete|mapping|endpoint", re.I)


def infer_layer(name: str, decorators: list[str], bases: list[str]) -> str:
    haystack = " ".join([name] + decorators + bases)
    for pattern, layer in LAYER_RULES:
        if pattern.search(haystack):
            return layer
    return "unknown"


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


def analyze(src: str):
    """Two-pass analysis: collect declarations, then resolve calls."""
    methods: dict[str, dict] = {}          # node_id -> info
    class_methods: dict[str, set[str]] = {}  # ClassName -> {method names}
    func_nodes: dict[str, str] = {}         # module function name -> node_id
    # Deferred call sites, resolved in pass 2:  (caller_id, class_ctx, fn_ast)
    pending: list[tuple[str, str | None, dict, ast.AST]] = []

    for path in iter_py_files(src):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src_text = fh.read()
            tree = ast.parse(src_text, filename=path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"  ! skipped {path}: {exc}", file=sys.stderr)
            continue
        rel = os.path.relpath(path, src).replace("\\", "/")

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
                is_endpoint = layer == "controller" or any(ROUTE_DECORATOR_RE.search(d) for d in decos)
                doc = ast.get_docstring(m) or ""
                code = ast.get_source_segment(src_text, m) or ""
                methods[node_id] = {
                    "id": node_id, "name": m.name, "cls": cls.name, "layer": layer,
                    "kind": "endpoint" if is_endpoint else "method",
                    "signature": _signature(m),
                    "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                    "source": f"{rel}:{m.lineno}", "calls": [], "callers": [],
                    "hash": _hash(code), "code": code,
                }
                local_types = _local_types(m, attr_types)
                pending.append((node_id, cls.name, {"attr_types": attr_types, "local_types": local_types}, m))

        for fn in [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            node_id = fn.name
            func_nodes[fn.name] = node_id
            doc = ast.get_docstring(fn) or ""
            code = ast.get_source_segment(src_text, fn) or ""
            methods[node_id] = {
                "id": node_id, "name": fn.name, "cls": None, "layer": "function",
                "kind": "function", "signature": _signature(fn),
                "doc": doc.strip().splitlines()[0] if doc.strip() else "",
                "source": f"{rel}:{fn.lineno}", "calls": [], "callers": [],
                "hash": _hash(code), "code": code,
            }
            local_types = _local_types(fn, {})
            pending.append((node_id, None, {"attr_types": {}, "local_types": local_types}, fn))

    # --- Pass 2: resolve call edges ---
    edges: set[tuple[str, str]] = set()
    for caller_id, cls_ctx, ctx, fn in pending:
        for target in _resolve_calls(fn, cls_ctx, ctx, methods, class_methods, func_nodes):
            if target != caller_id:
                edges.add((caller_id, target))

    for src_id, dst_id in edges:
        methods[src_id]["calls"].append(dst_id)
        methods[dst_id]["callers"].append(src_id)
    for info in methods.values():
        info["calls"] = sorted(set(info["calls"]))
        info["callers"] = sorted(set(info["callers"]))

    return methods, sorted(edges)


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


def _resolve_calls(fn, cls_ctx, ctx, methods, class_methods, func_nodes) -> set[str]:
    attr_types, local_types = ctx["attr_types"], ctx["local_types"]
    found: set[str] = set()

    def exists(cls_name, method):
        return cls_name in class_methods and method in class_methods[cls_name]

    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            method = func.attr
            base = func.value
            # self.attr.method()
            if _is_self_attr(base):
                cls_name = attr_types.get(base.attr)
                if cls_name and exists(cls_name, method):
                    found.add(f"{cls_name}.{method}")
            # self.method()
            elif isinstance(base, ast.Name) and base.id == "self" and cls_ctx:
                if exists(cls_ctx, method):
                    found.add(f"{cls_ctx}.{method}")
            # <var>.method()  where var is a typed param/local
            elif isinstance(base, ast.Name) and base.id in local_types:
                cls_name = local_types[base.id]
                if exists(cls_name, method):
                    found.add(f"{cls_name}.{method}")
        elif isinstance(func, ast.Name):
            # bare function call to a known module function
            if func.id in func_nodes:
                found.add(func_nodes[func.id])
    return found


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
        page = (
            f"---\n"
            f"entity: {info['id']}\n"
            f"kind: {info['kind']}\n"
            f"layer: {info['layer']}\n"
            f"class: {info['cls'] or ''}\n"
            f"source: {info['source']}\n"
            f"desc_source: {info.get('desc_source', 'auto')}\n"
            f"---\n"
            f"# {info['id']}\n\n"
            f"## What it does\n{info.get('summary', '')}\n\n"
            f"## Signature\n`{info['signature']}`\n\n"
            f"## Calls\n{calls_md}\n\n"
            f"## Called by\n{callers_md}\n"
        )
        with open(os.path.join(flow_dir, f"{_safe(info['id'])}.md"), "w", encoding="utf-8") as fh:
            fh.write(page)


def write_graph(methods: dict, edges, graph_path: str) -> None:
    nodes = [
        {"id": i["id"], "layer": i["layer"], "kind": i["kind"],
         "cls": i["cls"], "signature": i["signature"], "doc": i.get("summary", ""),
         "source": i["source"]}
        for i in sorted(methods.values(), key=lambda x: x["id"])
    ]
    graph = {"nodes": nodes,
             "edges": [{"source": s, "target": t, "type": "calls"} for s, t in edges]}
    os.makedirs(os.path.dirname(graph_path), exist_ok=True)
    with open(graph_path, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)
        fh.write("\n")


def build(src: str, flow_dir: str, graph_path: str) -> int:
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        print(f"error: --src '{src}' is not a directory", file=sys.stderr)
        return 2
    print(f"Analyzing call flow in {src} ...")
    methods, edges = analyze(src)
    if not methods:
        print("No Python methods/functions found.")
        return 0

    # Hybrid descriptions: docstring -> cached AI summary -> auto fallback.
    cache = _load_json(DESCRIPTIONS_PATH, {})
    pending = resolve_descriptions(methods, cache)
    # Prune cache entries for nodes that no longer exist (handles deletes).
    cache = {k: v for k, v in cache.items() if k in methods}
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
    print(f"Flow: {len(methods)} node(s), {len(edges)} call edge(s), {len(endpoints)} endpoint(s)")
    print(f"  descriptions: {from_doc} docstring, {from_ai} cached-AI, {len(pending)} pending")
    print(f"  graph -> {graph_path}")
    print(f"  notes -> {flow_dir}")
    if pending:
        print(f"  NOTE: {len(pending)} method(s) need an AI summary. Read {PENDING_PATH},")
        print("        write a one-line summary for each, then run apply_descriptions.py and rebuild.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a method-level call/request-flow graph.")
    parser.add_argument("--src", default="./src", help="Source directory to analyze (default: ./src)")
    parser.add_argument("--flow-dir", default=DEFAULT_FLOW_DIR, help="Output directory for method notes")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Output flow_graph.json path")
    args = parser.parse_args(argv)
    return build(args.src, args.flow_dir, args.graph)


if __name__ == "__main__":
    raise SystemExit(main())
