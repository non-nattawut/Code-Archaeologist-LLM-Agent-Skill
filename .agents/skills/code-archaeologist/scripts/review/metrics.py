#!/usr/bin/env python3
"""metrics.py — how big and how tangled, per file and per node.

The size half of the review pass. Two measurements, joined by node id so they
line up with either graph:

  per file    total / code / comment / blank lines, and the language
  per node    LOC, cyclomatic complexity, max nesting depth, parameter count

A comment line is one that starts with `#` (or `//` `/*` `*`), so a Python
docstring counts as code, not comment.

Node entries are keyed exactly like the graphs key them (`name`, `Class.method`,
`Class`), so an agent can ask "how long is OrderService.place_order" without
opening a single source file — which is the whole point of computing this here.

    python metrics.py --src ./backend ./frontend
    python metrics.py --src ./src --graph <graph.json> --out <file> --top 10

Per-node metrics cover Python only: the JS/TS extractor does not record an end
line yet, so frontend files land in the file totals but not in `nodes`.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "report", "metrics.json")

import manifest  # noqa: E402
import console          # noqa: E402  (stdout must survive a non-UTF-8 console)
import scan_security    # noqa: E402  (iter_source_files: one definition of "a source file")
from taxonomy import lang_of  # noqa: E402  (one definition of "what language is this file")
import py_extract as px  # noqa: E402  (Python, via tree-sitter)

# Languages whose line comment is # rather than //.
HASH_COMMENT = {"py", "ruby", "elixir"}
HASH_PREFIXES = ("#",)
DEFAULT_COMMENTS = ("//", "/*", "*")

# Decision points: each is a place execution can go two ways, so each adds 1 to
# the McCabe count of the function containing it. tree-sitter spellings, chosen
# to name the same constructs `ast` did -- `for_statement` covers `async for`,
# which had its own class in `ast`, and `elif_clause` / `else_clause` are separate
# nodes here where `ast` nested another `If`.
DECISIONS = {"if_statement", "elif_clause", "for_statement", "while_statement",
             "except_clause", "with_statement", "assert_statement",
             "conditional_expression", "case_clause"}
# Statements that indent their body: the depth measurement follows these.
BLOCKS = {"if_statement", "for_statement", "while_statement", "with_statement",
          "try_statement", "match_statement", "function_definition", "class_definition"}
DEFS = ("function_definition",)


def line_metrics(full: str, lang: str) -> dict:
    """Total / code / comment / blank lines for one file."""
    prefixes = HASH_PREFIXES if lang in HASH_COMMENT else DEFAULT_COMMENTS
    total = comment = blank = 0
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                total += 1
                line = raw.strip()
                if not line:
                    blank += 1
                elif line.startswith(prefixes):
                    comment += 1
    except OSError:
        return {}
    return {"lines": total, "code": total - blank - comment, "comment": comment,
            "blank": blank, "lang": lang}


def complexity(node) -> int:
    """1 + every branch inside `node` (whole subtree, nested defs included).

    `ast` counted a chained `a and b and c` as two branches by reading `BoolOp`'s
    operand list; tree-sitter nests `boolean_operator`, so each nesting level is
    one node and counting the nodes gives the same total. A comprehension's `if`
    clauses are `if_clause` nodes rather than a list hanging off `comprehension`.
    """
    score = 1
    for child in px.walk(node):
        if child.type in DECISIONS:
            score += 1
        elif child.type == "boolean_operator":
            op = px.field(child, "operator")
            if op is not None and px.text(op) in ("and", "or"):
                score += 1
        elif child.type == "if_clause":
            score += 1
    return score


def depth(node, level: int = 0) -> int:
    """Deepest nesting of block statements below `node` (0 when the body is flat)."""
    deepest = level
    for child in node.named_children:
        step = level + 1 if child.type in BLOCKS else level
        deepest = max(deepest, depth(child, step))
    return deepest


def params(node) -> int:
    """Declared parameters, `self` included -- the count `ast` produced."""
    if node.type not in DEFS:
        return 0
    plist = px.params_of(node)
    if plist is None:
        return 0
    return len([c for c in plist.named_children if c.type != "comment"])


def _entry(node, key: str) -> dict:
    return {
        "loc": px.end_line(node) - px.line(node) + 1,
        "complexity": complexity(node),
        "depth": depth(node),
        "params": params(node),
        "file": key,
        "line": px.line(node),
        "lang": "py",
    }


def node_metrics(full: str, key: str) -> dict:
    """Metrics for the top-level defs and classes of one Python file.

    Only the levels the graphs model: module functions, classes, and their direct
    methods. A closure inside a function is measured as part of that function.
    """
    try:
        tree = px.parse(px.read_source(full))
    except OSError:
        return {}
    if tree is None:                        # no Python grammar: the build already said so
        return {}
    out: dict[str, dict] = {}
    for _decs, node in px.defs_in(tree.root_node, ("class_definition", "function_definition")):
        name = px.def_name(node)
        out[name] = _entry(node, key)
        if node.type == "class_definition":
            for _m_decs, member in px.defs_in(px.body_of(node)):
                out[f"{name}.{px.def_name(member)}"] = _entry(member, key)
    return out


def _graph_ids(graph_path: str) -> set[str]:
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except (FileNotFoundError, ValueError):
        return set()
    return {n["id"] for n in graph.get("nodes", []) if "id" in n}


def build(roots, graph_path: str | None = None, out_path: str | None = None, top: int = 10) -> dict:
    """The whole payload: file lines, node metrics, and the three rankings."""
    roots = [roots] if isinstance(roots, str) else list(roots)
    files: dict[str, dict] = {}
    nodes: dict[str, dict] = {}
    for full, key in scan_security.iter_source_files(roots):
        lang = lang_of(key)
        info = line_metrics(full, lang)
        if not info:
            continue
        files[key] = info
        if lang == "py":
            for node_id, entry in node_metrics(full, key).items():
                nodes.setdefault(node_id, entry)   # same id in two files: first wins

    langs: dict[str, dict] = {}
    for info in files.values():
        bucket = langs.setdefault(info["lang"], {"files": 0, "lines": 0})
        bucket["files"] += 1
        bucket["lines"] += info["lines"]

    totals = {"files": len(files)}
    for field in ("lines", "code", "comment", "blank"):
        totals[field] = sum(f[field] for f in files.values())
    totals["comment_ratio"] = round(totals["comment"] / totals["lines"], 3) if totals["lines"] else 0.0

    ids = _graph_ids(graph_path) if graph_path else set()
    for node_id, entry in nodes.items():
        entry["in_graph"] = node_id in ids

    # Rank only what this graph contains, so the flow report ranks methods and the
    # structure report ranks classes. With no graph to compare against, rank everything.
    ranked = {k: v for k, v in nodes.items() if v["in_graph"]} or nodes

    def rank(items, field):
        return sorted(items, key=lambda kv: (-kv[1][field], kv[0]))[:top]

    payload = {
        "roots": manifest.rel_roots(roots),
        "totals": totals,
        "languages": dict(sorted(langs.items(), key=lambda kv: (-kv[1]["lines"], kv[0]))),
        "files": dict(sorted(files.items())),
        "nodes": dict(sorted(nodes.items())),
        "top_loc": [{"id": k, "loc": v["loc"], "complexity": v["complexity"],
                     "file": v["file"], "line": v["line"]} for k, v in rank(ranked.items(), "loc")],
        "top_complexity": [{"id": k, "complexity": v["complexity"], "loc": v["loc"],
                            "file": v["file"], "line": v["line"]}
                           for k, v in rank(ranked.items(), "complexity")],
        "top_files": [{"file": k, "lines": v["lines"], "code": v["code"]}
                      for k, v in rank(files.items(), "lines")],
        "unmeasured_graph_ids": sorted(ids - set(nodes)),
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Line counts and complexity, per file and per node.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph used to flag which nodes are mapped")
    parser.add_argument("--out", default=None, help=f"Write the payload here (e.g. {DEFAULT_OUT})")
    parser.add_argument("--top", type=int, default=10, help="How many entries in each ranking")
    args = parser.parse_args(argv)
    console.safe_stdout()

    missing = [r for r in args.src if not os.path.isdir(r)]
    if missing:
        print(f"error: source root(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    m = build(args.src, args.graph, args.out, args.top)
    t = m["totals"]
    print(f"Metrics: {t['files']} file(s), {t['lines']} line(s) "
          f"({t['code']} code, {t['comment']} comment, {t['blank']} blank)")
    if m["languages"]:
        print("  languages: " + ", ".join(f"{k} {v['files']} file(s)/{v['lines']} line(s)"
                                          for k, v in m["languages"].items()))
    if m["top_loc"]:
        big = m["top_loc"][0]
        print(f"  largest: {big['id']} {big['loc']} line(s) ({big['file']}:{big['line']})")
    if m["top_complexity"]:
        cx = m["top_complexity"][0]
        print(f"  most complex: {cx['id']} cx {cx['complexity']} ({cx['file']}:{cx['line']})")
    if m["unmeasured_graph_ids"]:
        print(f"  {len(m['unmeasured_graph_ids'])} graph node(s) have no metrics "
              f"(non-Python, or outside --src)")
    if args.out:
        print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
