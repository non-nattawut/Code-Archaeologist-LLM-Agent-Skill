#!/usr/bin/env python3
"""metrics.py — how big and how tangled, per file and per node.

The size half of the review pass. Two measurements, joined by node id so they
line up with either graph:

  per file    total / code / comment / blank lines, and the language
  per node    LOC, cyclomatic complexity, max nesting depth, parameter count

A comment line is one that starts with `#` (or `//` `/*` `*`), so a Python
docstring counts as code, not comment.

Per-node figures are measured on the *graph's own nodes*, in every graphed
language: each node's `source` (`file:line`) and `end` pick its definition out of
the file's tree-sitter parse, and one table per grammar says which node types are
decisions, blocks and definitions. So the key is the graph id by construction --
an agent can ask "how long is OrderService.place_order" without opening a source
file, and a name two files define is measured under its file-qualified id.

Until phase 6a this measured Python only, walking each file's definitions and
keying them by *bare* name, first wins. Once shared names became file-qualified
(finding #5, phase 5a), such a node could never match its own figures, and every
Java / Go / C# / JS / TS node had none at all.

A node with no range -- a structure module group, a signature-only declaration,
a node outside `--src` -- has no body to measure and is listed in
`unmeasured_graph_ids` instead.

    python metrics.py --src ./backend ./frontend
    python metrics.py --src ./src --graph <graph.json> --out <file> --top 10

Zero external dependencies beyond the tree-sitter wheels. Python 3.10+.
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
import grammars         # noqa: E402  (one parser per language, the extractors' own)
import scan_security    # noqa: E402  (iter_source_files: one definition of "a source file")
from taxonomy import lang_of  # noqa: E402  (one definition of "what language is this file")
import py_extract as px  # noqa: E402  (tree helpers, and read_source's newline rule)

# Languages whose line comment is # rather than //.
HASH_COMMENT = {"py", "ruby", "elixir"}
HASH_PREFIXES = ("#",)
DEFAULT_COMMENTS = ("//", "/*", "*")

# Census language (taxonomy.lang_of) -> the grammar that parses it.
GRAMMAR = {"py": "python", "js": "javascript", "jsx": "javascript", "ts": "typescript",
           "tsx": "tsx", "java": "java", "go": "go", "csharp": "csharp"}

# Per grammar: `decisions` each add 1 to the McCabe count of the node containing
# them, `blocks` indent a body (depth follows them), and `defs` are what a graph
# node's range can point at. tree-sitter spellings, every one checked against the
# pinned grammar (`Language.id_for_node_kind`) when this table was written.
#
# Python's sets are exactly the ones `ast` counted before the port -- `for_statement`
# covers `async for`, and `elif_clause` / `else_clause` are separate nodes where
# `ast` nested another `If`. Change them and every Python number moves.
_JS_DECISIONS = {"if_statement", "for_statement", "for_in_statement", "while_statement",
                 "do_statement", "catch_clause", "ternary_expression", "switch_case"}
_JS_BLOCKS = {"if_statement", "for_statement", "for_in_statement", "while_statement",
              "do_statement", "try_statement", "switch_statement", "function_declaration",
              "function_expression", "arrow_function", "method_definition", "class_declaration"}
_JS_DEFS = {"function_declaration", "generator_function_declaration", "method_definition",
            "arrow_function", "function_expression", "class_declaration", "variable_declarator"}
TABLES = {
    "python": {
        "decisions": {"if_statement", "elif_clause", "for_statement", "while_statement",
                      "except_clause", "with_statement", "assert_statement",
                      "conditional_expression", "case_clause"},
        "blocks": {"if_statement", "for_statement", "while_statement", "with_statement",
                   "try_statement", "match_statement", "function_definition", "class_definition"},
        "defs": {"function_definition", "class_definition"},
    },
    "java": {
        "decisions": {"if_statement", "for_statement", "enhanced_for_statement", "while_statement",
                      "do_statement", "catch_clause", "ternary_expression", "switch_label"},
        "blocks": {"if_statement", "for_statement", "enhanced_for_statement", "while_statement",
                   "do_statement", "try_statement", "try_with_resources_statement",
                   "switch_expression", "lambda_expression"},
        "defs": {"method_declaration", "constructor_declaration", "class_declaration",
                 "interface_declaration", "enum_declaration", "record_declaration"},
    },
    "go": {
        "decisions": {"if_statement", "for_statement", "expression_case", "type_case",
                      "communication_case"},
        "blocks": {"if_statement", "for_statement", "expression_switch_statement",
                   "type_switch_statement", "select_statement", "func_literal"},
        "defs": {"function_declaration", "method_declaration", "type_spec", "func_literal"},
    },
    "csharp": {
        "decisions": {"if_statement", "for_statement", "foreach_statement", "while_statement",
                      "do_statement", "catch_clause", "conditional_expression", "switch_section",
                      "switch_expression_arm"},
        "blocks": {"if_statement", "for_statement", "foreach_statement", "while_statement",
                   "do_statement", "try_statement", "switch_statement", "lambda_expression",
                   "local_function_statement"},
        "defs": {"method_declaration", "constructor_declaration", "class_declaration",
                 "interface_declaration", "struct_declaration", "record_declaration",
                 "enum_declaration", "local_function_statement"},
    },
    "javascript": {"decisions": _JS_DECISIONS, "blocks": _JS_BLOCKS, "defs": _JS_DEFS},
    "typescript": {"decisions": _JS_DECISIONS, "blocks": _JS_BLOCKS,
                   "defs": _JS_DEFS | {"abstract_class_declaration"}},
    "tsx": {"decisions": _JS_DECISIONS, "blocks": _JS_BLOCKS,
            "defs": _JS_DEFS | {"abstract_class_declaration"}},
}

# Short-circuit operators: each is a branch. Python spells them in
# `boolean_operator`; every other grammar here in `binary_expression`.
BOOLEAN_OPS = {"and", "or", "&&", "||", "??"}
# A case label that is the fallback, not a branch of its own.
_FALLBACK_CASES = {"switch_label", "switch_section", "switch_expression_arm"}


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


def complexity(node, table: dict) -> int:
    """1 + every branch inside `node` (whole subtree, nested defs included).

    `ast` counted a chained `a and b and c` as two branches by reading `BoolOp`'s
    operand list; tree-sitter nests the operator node, so each nesting level is
    one node and counting the nodes gives the same total. A Python
    comprehension's `if` clauses are `if_clause` nodes. A `default:` / `_ =>` case
    is the fallback, not a branch, and does not count.
    """
    score = 1
    for child in px.walk(node):
        kind = child.type
        if kind in table["decisions"]:
            if kind in _FALLBACK_CASES and px.text(child).lstrip().startswith(("default", "_")):
                continue
            score += 1
        elif kind in ("boolean_operator", "binary_expression"):
            op = px.field(child, "operator")
            if op is not None and px.text(op) in BOOLEAN_OPS:
                score += 1
        elif kind == "if_clause":
            score += 1
    return score


def depth(node, blocks: set, level: int = 0) -> int:
    """Deepest nesting of block statements below `node` (0 when the body is flat)."""
    deepest = level
    for child in node.named_children:
        step = level + 1 if child.type in blocks else level
        deepest = max(deepest, depth(child, blocks, step))
    return deepest


def params(node, grammar: str) -> int:
    """Declared parameters. Python counts `self`, which is the count `ast` produced."""
    if grammar == "python":
        if node.type != "function_definition":
            return 0
        plist = px.params_of(node)
        if plist is None:
            return 0
        return len([c for c in plist.named_children if c.type != "comment"])
    if node.type == "variable_declarator":          # const f = (a, b) => ...
        node = px.field(node, "value") or node
    plist = px.field(node, "parameters")
    if plist is None:
        return 1 if px.field(node, "parameter") is not None else 0   # x => x
    # Go declares `a, b int` as one parameter with two names.
    return sum(max(1, len(c.children_by_field_name("name")))
               for c in plist.named_children if c.type != "comment")


def locate(root, line: int, end: int, defs: set):
    """The definition a graph range points at, or None.

    Among definition nodes ending on the range's last line, the one starting
    closest to its first line -- ties to the outermost. "Closest", not "equal":
    the extractors disagree about decorators (a TS method's range opens at its
    first decorator, a Java method's at its name), and both must land on the
    method rather than on the decorator or the body.
    """
    lo, hi = line - 1, end - 1
    best, best_key = None, None
    stack = [root]
    while stack:
        node = stack.pop()
        if node.end_point[0] < lo or node.start_point[0] > hi:
            continue
        if node.type in defs and node.end_point[0] == hi:
            key = (abs(node.start_point[0] - lo), node.start_byte - node.end_byte)
            if best_key is None or key < best_key:
                best, best_key = node, key
        stack.extend(node.children)
    return best


def _parse(full: str, grammar: str):
    parser = grammars.parser_for(grammar)
    if parser is None:                      # no grammar: the build already said so
        return None
    try:
        # read_source normalizes newlines exactly as the extractors do, so a CRLF
        # checkout puts every row where the graph says it is.
        return parser.parse(px.read_source(full)).root_node
    except OSError:
        return None


def node_metrics(nodes, paths: dict) -> dict:
    """{graph id: metrics} for every node whose range can be found in its file.

    `nodes` are graph nodes (id, source `file:line`, end); `paths` maps a source
    key to its file on disk, as `scan_security.iter_source_files` yields them.
    """
    trees: dict[str, object] = {}
    out: dict[str, dict] = {}
    for n in nodes:
        if n.get("declaration"):
            continue                        # a signature: no body, nothing to count
        key, _, start = (n.get("source") or "").rpartition(":")
        end = n.get("end")
        if not key or not start.isdigit() or not isinstance(end, int) or end < int(start):
            continue                        # no range: a module group, a stub
        grammar = GRAMMAR.get(lang_of(key))
        if grammar is None or key not in paths:
            continue
        if key not in trees:
            trees[key] = _parse(paths[key], grammar)
        if trees[key] is None:
            continue
        table = TABLES[grammar]
        found = locate(trees[key], int(start), end, table["defs"])
        if found is None:
            continue
        out[n["id"]] = {
            "loc": end - int(start) + 1,
            "complexity": complexity(found, table),
            "depth": depth(found, table["blocks"]),
            "params": params(found, grammar),
            "file": key,
            "line": int(start),
            "lang": lang_of(key),
        }
    return out


def _graph_nodes(graph_path: str) -> list[dict]:
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("nodes", [])
    except (FileNotFoundError, ValueError):
        return []


def build(roots, graph_path: str | None = None, out_path: str | None = None, top: int = 10) -> dict:
    """The whole payload: file lines, node metrics, and the three rankings."""
    roots = [roots] if isinstance(roots, str) else list(roots)
    files: dict[str, dict] = {}
    paths: dict[str, str] = {}
    for full, key in scan_security.iter_source_files(roots):
        lang = lang_of(key)
        info = line_metrics(full, lang)
        if not info:
            continue
        files[key] = info
        paths[key] = full

    graph = _graph_nodes(graph_path) if graph_path else []
    nodes = node_metrics(graph, paths)

    langs: dict[str, dict] = {}
    for info in files.values():
        bucket = langs.setdefault(info["lang"], {"files": 0, "lines": 0})
        bucket["files"] += 1
        bucket["lines"] += info["lines"]

    totals = {"files": len(files)}
    for field in ("lines", "code", "comment", "blank"):
        totals[field] = sum(f[field] for f in files.values())
    totals["comment_ratio"] = round(totals["comment"] / totals["lines"], 3) if totals["lines"] else 0.0

    def rank(items, field):
        return sorted(items, key=lambda kv: (-kv[1][field], kv[0]))[:top]

    payload = {
        "roots": manifest.rel_roots(roots),
        "totals": totals,
        "languages": dict(sorted(langs.items(), key=lambda kv: (-kv[1]["lines"], kv[0]))),
        "files": dict(sorted(files.items())),
        "nodes": dict(sorted(nodes.items())),
        "top_loc": [{"id": k, "loc": v["loc"], "complexity": v["complexity"],
                     "file": v["file"], "line": v["line"]} for k, v in rank(nodes.items(), "loc")],
        "top_complexity": [{"id": k, "complexity": v["complexity"], "loc": v["loc"],
                            "file": v["file"], "line": v["line"]}
                           for k, v in rank(nodes.items(), "complexity")],
        "top_files": [{"file": k, "lines": v["lines"], "code": v["code"]}
                      for k, v in rank(files.items(), "lines")],
        "unmeasured_graph_ids": sorted({n["id"] for n in graph if "id" in n} - set(nodes)),
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
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph whose nodes are measured")
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
              f"(no range to measure: module groups, declarations; or outside --src)")
    if args.out:
        print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
