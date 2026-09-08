#!/usr/bin/env python3
"""search.py — find nodes without grepping source.

Grep answers "which lines contain this string". This answers "which nodes are
these", which is the question you actually have: it filters the graph by name,
description, file, layer, kind, language or connectivity and prints the ids you
can hand to `trace_path.py`, `context.py` or a note read.

    python search.py --name "payment|charge"          # name matches a regex
    python search.py --doc "order"                    # description matches a regex
    python search.py --layer repository --kind method
    python search.py --file order_repository.py
    python search.py --calls OrderRepository.save     # nodes that call it
    python search.py --called-by OrderService.place_order
    python search.py --orphans                        # no callers at all

Filters combine with AND. With none, it lists the whole map (up to `--limit`).
`--graph` selects the map (default: flow). `--format json` for tooling.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")

import console     # noqa: E402  (stdout must survive a non-UTF-8 console)

DOC_CHARS = 90


def _rx(pattern: str | None):
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.I)
    except re.error as exc:
        raise SystemExit(f"error: bad regex {pattern!r}: {exc}")


def search(graph_path: str, **f) -> list[dict]:
    """Every node matching all given filters, sorted by id."""
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except (OSError, ValueError):
        raise SystemExit(f"error: graph not found or unreadable at {graph_path} - build a map first")

    nodes = graph.get("nodes", [])
    calls: dict[str, set[str]] = {}
    callers: dict[str, set[str]] = {}
    for e in graph.get("edges", []):
        s, t = e.get("source"), e.get("target")
        calls.setdefault(s, set()).add(t)
        callers.setdefault(t, set()).add(s)

    name, doc = _rx(f.get("name")), _rx(f.get("doc"))
    hits = []
    for n in nodes:
        nid = n.get("id", "")
        if name and not name.search(nid):
            continue
        if doc and not doc.search(n.get("doc", "") or ""):
            continue
        if f.get("layer") and n.get("layer") != f["layer"]:
            continue
        if f.get("kind") and n.get("kind") != f["kind"]:
            continue
        if f.get("lang") and n.get("lang") != f["lang"]:
            continue
        if f.get("file") and f["file"].replace("\\", "/") not in (n.get("source") or ""):
            continue
        if f.get("calls") and f["calls"] not in calls.get(nid, ()):
            continue
        if f.get("called_by") and f["called_by"] not in callers.get(nid, ()):
            continue
        if f.get("orphans") and callers.get(nid):
            continue
        hits.append({
            "id": nid,
            "kind": n.get("kind"),
            "layer": n.get("layer"),
            "lang": n.get("lang"),
            "source": n.get("source"),
            "doc": " ".join((n.get("doc") or "").split()),
            "fan_in": len(callers.get(nid, ())),
            "fan_out": len(calls.get(nid, ())),
        })
    return sorted(hits, key=lambda h: h["id"])


def to_text(hits: list[dict], total: int) -> str:
    if not hits:
        return "no match"
    width = max(len(h["id"]) for h in hits)
    lines = []
    for h in hits:
        doc = h["doc"]
        if len(doc) > DOC_CHARS:
            doc = doc[:DOC_CHARS - 3].rstrip() + "..."
        lines.append(f"{h['id']:<{width}}  {h['kind']}/{h['layer']}  {h['source']}"
                     + (f"  {doc}" if doc else ""))
    if total > len(hits):
        lines.append(f"... {total - len(hits)} more (raise --limit)")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Find graph nodes by name, description or connectivity.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to the graph (default: the flow map)")
    parser.add_argument("--name", help="Regex matched against the node id")
    parser.add_argument("--doc", help="Regex matched against the node description")
    parser.add_argument("--layer", help="Exact layer (see templates/TAXONOMY.md)")
    parser.add_argument("--kind", help="Exact kind (see templates/TAXONOMY.md)")
    parser.add_argument("--lang", help="Exact language, e.g. py or ts")
    parser.add_argument("--file", help="Substring of the source path")
    parser.add_argument("--calls", help="Only nodes that call this node id")
    parser.add_argument("--called-by", dest="called_by", help="Only nodes called by this node id")
    parser.add_argument("--orphans", action="store_true", help="Only nodes nothing calls")
    parser.add_argument("--limit", type=int, default=40, help="Maximum rows to print")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(argv)
    console.safe_stdout()

    hits = search(args.graph, name=args.name, doc=args.doc, layer=args.layer, kind=args.kind,
                  lang=args.lang, file=args.file, calls=args.calls, called_by=args.called_by,
                  orphans=args.orphans)
    shown = hits[:args.limit]
    if args.format == "json":
        print(json.dumps({"count": len(hits), "shown": len(shown), "nodes": shown}, indent=2))
    else:
        print(to_text(shown, len(hits)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
