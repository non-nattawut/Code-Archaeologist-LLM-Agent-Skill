#!/usr/bin/env python3
"""duplicates.py — copy-pasted functions, found even when the names were changed.

Clone detection by normalized token hash. Every node's body is reduced to the
shape of its code — identifiers become `ID`, literals become `LIT`, comments and
whitespace go away, keywords and operators stay — and bodies that reduce to the
same shape are the same code:

    def total(items):          def sum_all(rows):
        n = 0                      total = 0
        for i in items:            for r in rows:
            n += i.price               total += r.cost
        return n                   return total

Both normalize to `def ID ( ID ) : ID = LIT for ID in ID : ID += ID . ID return ID`,
so a rename cannot hide the copy. Changing an operator or adding a branch does
change the shape, and the two stop clustering — which is the point: this finds
copies, not merely similar-looking code.

    python duplicates.py --src ./src
    python duplicates.py --src ./src --graph <flow_graph.json> --out <file>.json

Ranges come from the graph (`source` + `end`), so this reads each file once and
never re-parses. Nodes without a usable range are skipped — a synthetic route
node has no body to compare.

Heuristic by design: a clone here is a token-shape match, not proof of a bad
abstraction. Two validators that legitimately look alike will cluster, and a
copy someone has since edited will not. It is a review prompt, not a verdict.

It errs toward missing a copy rather than inventing one. A docstring counts as a
token, so documenting one copy and not the other hides the pair — deliberate:
every rule for stripping leading docs was fragile enough to risk clustering
functions that merely start alike, and a false positive here costs more than a
miss.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR, SKILL_ROOT  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "report", "duplicates.json")

import manifest         # noqa: E402  (portable roots in the payload)
import console          # noqa: E402  (stdout must survive a non-UTF-8 console)
import scan_security    # noqa: E402  (one definition of "which files are source")

# Below this a match is noise: getters, one-line delegates and `return None`
# bodies are identical everywhere and say nothing about copy-paste.
MIN_TOKENS = 30

# Keywords kept verbatim so structure survives normalization. One union across
# the languages the graphs cover: a word only has to normalize *consistently*,
# and treating a stray `func` in Python as a keyword costs nothing.
KEYWORDS = frozenset("""
and as assert async await break case catch class const continue def default defer del
do elif else except extends finally for from func function go goto if implements import
in interface is lambda let map new nil none not or pass private protected public raise
range return select static struct switch this throw throws try type var void while with yield
bool byte char double float int long string true false null undefined self super
""".split())

TOKEN_RE = re.compile(r"""
      (?P<ws>\s+)
    | (?P<lcomment>\#[^\n]*|//[^\n]*)
    | (?P<bcomment>/\*.*?\*/)
    | (?P<tstring>'''.*?'''|\"\"\".*?\"\"\")
    | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)
    | (?P<number>\d+\.?\d*(?:[eE][+-]?\d+)?)
    | (?P<name>[A-Za-z_$][A-Za-z_$0-9]*)
    | (?P<op>[^\s\w])
""", re.VERBOSE | re.DOTALL)


def normalize(text: str) -> list[str]:
    """Source text -> the token shape of its code.

    Comments and whitespace are dropped, every literal becomes `LIT`, every
    non-keyword word becomes `ID`, and operators and punctuation are kept as
    they are. What survives is control flow and structure.
    """
    out: list[str] = []
    for m in TOKEN_RE.finditer(text):
        kind = m.lastgroup
        if kind in ("ws", "lcomment", "bcomment"):
            continue
        if kind in ("tstring", "string", "number"):
            out.append("LIT")
        elif kind == "name":
            word = m.group()
            out.append(word if word in KEYWORDS else "ID")
        else:
            out.append(m.group())
    return out


def node_bodies(roots, graph_path: str) -> list[dict]:
    """Every graph node paired with the token shape of its source range."""
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            nodes = json.load(fh).get("nodes", [])
    except (OSError, ValueError):
        return []

    # key ("<root>/<rel>") -> absolute path, from the one definition of "source file"
    paths = {key: full for full, key in scan_security.iter_source_files(roots)}
    cache: dict[str, list[str]] = {}
    out = []
    for n in nodes:
        if n.get("declaration"):
            continue                       # a signature with no body has no shape
        src = n.get("source") or ""
        key, _, start = src.partition(":")
        end = n.get("end") or 0
        if not key or not start.isdigit() or not end:
            continue                       # synthetic node: no body to compare
        start = int(start)
        if end < start or key not in paths:
            continue
        if key not in cache:
            try:
                with open(paths[key], "r", encoding="utf-8", errors="replace") as fh:
                    cache[key] = fh.readlines()
            except OSError:
                cache[key] = []
        lines = cache[key]
        body = "".join(lines[start - 1:end])
        if not body.strip():
            continue
        out.append({"node": n, "tokens": normalize(body), "loc": end - start + 1})
    return out


def find_clusters(bodies: list[dict], min_tokens: int = MIN_TOKENS) -> list[dict]:
    """Group bodies by the hash of their token shape; >= 2 is a clone cluster."""
    groups: dict[str, list[dict]] = {}
    for b in bodies:
        if len(b["tokens"]) < min_tokens:
            continue
        digest = hashlib.sha1(" ".join(b["tokens"]).encode("utf-8")).hexdigest()[:12]
        groups.setdefault(digest, []).append(b)

    clusters = []
    for digest, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda b: b["node"]["id"])
        clusters.append({
            "hash": digest,
            "tokens": len(members[0]["tokens"]),
            "loc": max(b["loc"] for b in members),
            "nodes": [{"id": b["node"]["id"], "source": b["node"].get("source"),
                       "layer": b["node"].get("layer"), "kind": b["node"].get("kind")}
                      for b in members],
        })
    # Biggest first: the longest copied body is the one worth extracting.
    return sorted(clusters, key=lambda c: (-c["tokens"], -len(c["nodes"]), c["hash"]))


def build(roots, graph_path: str = DEFAULT_GRAPH, out_path: str | None = None) -> dict:
    roots = [roots] if isinstance(roots, str) else list(roots)
    clusters = find_clusters(node_bodies(roots, graph_path))

    payload = {
        "roots": manifest.rel_roots(roots),
        "graph": os.path.relpath(graph_path, SKILL_ROOT).replace("\\", "/"),
        "summary": {
            "clusters": len(clusters),
            "nodes_involved": sum(len(c["nodes"]) for c in clusters),
            # What deleting the copies would save: every member past the first.
            "duplicated_loc": sum(c["loc"] * (len(c["nodes"]) - 1) for c in clusters),
        },
        "clusters": clusters,
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Find copy-pasted functions by normalized token hash.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph whose nodes supply the source ranges")
    parser.add_argument("--out", default=None, help=f"Write the payload here (e.g. {DEFAULT_OUT})")
    parser.add_argument("--top", type=int, default=10, help="Clusters to print")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(argv)
    console.safe_stdout()

    missing = [r for r in args.src if not os.path.isdir(r)]
    if missing:
        print(f"error: source root(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    d = build(args.src, args.graph, args.out)
    if args.format == "json":
        print(json.dumps(d, indent=2))
        return 0

    s = d["summary"]
    print(f"Duplicates: {s['clusters']} cluster(s), {s['nodes_involved']} node(s), "
          f"{s['duplicated_loc']} duplicated line(s)")
    for c in d["clusters"][:args.top]:
        print(f"  {c['tokens']:>4} tokens x{len(c['nodes'])}  {', '.join(n['id'] for n in c['nodes'])}")
        for n in c["nodes"]:
            print(f"       {n['source']}")
    if args.out:
        print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
