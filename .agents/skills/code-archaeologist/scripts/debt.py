#!/usr/bin/env python3
"""debt.py — what is rotting: markers left in the code, and code nothing calls.

Two cheap, deterministic signals joined into one list an agent can answer
"what should we clean up" from, without reading a single file:

  markers     TODO / FIXME / HACK / XXX / BUG / DEPRECATED found in comments,
              each attributed to the graph node that owns the line
  dead code   nodes with no callers that are not entry points, and the files
              where *every* node is dead (a stronger signal than one orphan)

    python debt.py --src ./src
    python debt.py --src ./src --graph <flow_graph.json> --out <file>.json

Heuristic by design: a marker is text in a comment, and "dead" means nothing in
*this graph* calls it — dynamic dispatch, reflection and test-only entry points
do not show up. These are review prompts, not proof.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "report", "debt.json")

sys.path.insert(0, SCRIPT_DIR)
import analyze          # noqa: E402  (one definition of "which nodes are orphans")
import console          # noqa: E402  (stdout must survive a non-UTF-8 console)
import scan_security    # noqa: E402  (source iteration + node attribution)

TAGS = ("TODO", "FIXME", "HACK", "XXX", "BUG", "DEPRECATED")
MARKER_RE = re.compile(r"\b(" + "|".join(TAGS) + r")\b[:\s-]*(.*)")
LEAD_RE = re.compile(r"^(" + "|".join(TAGS) + r")\b")
TEXT_CHARS = 120


def _comment_part(line: str) -> str:
    """The comment half of a line, or "" when the line has no comment.

    Keeps `todo_count = 3` and `"TODO in a string"` out of the inventory: a
    marker has to sit after `#`, `//`, `/*` or a `*` continuation — or open a
    line of its own, which is how they appear inside docstrings.
    """
    best = -1
    for token in ("#", "//", "/*"):
        i = line.find(token)
        if i != -1 and (best == -1 or i < best):
            best = i + len(token)
    if best != -1:
        return line[best:]
    stripped = line.lstrip()
    if stripped.startswith("*"):
        return stripped[1:]
    return stripped if LEAD_RE.match(stripped) else ""


def find_markers(roots, graph_path: str) -> list[dict]:
    index = scan_security.node_index(graph_path)
    found: list[dict] = []
    for full, key in scan_security.iter_source_files(roots):
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for no, raw in enumerate(lines, 1):
            m = MARKER_RE.search(_comment_part(raw))
            if not m:
                continue
            text = " ".join(m.group(2).split())
            if text.endswith("*/"):                 # /* BUG: off-by-one */
                text = text[:-2].rstrip()
            found.append({
                "tag": m.group(1).upper(),
                "text": text[:TEXT_CHARS],
                "file": key,
                "line": no,
                "node": scan_security.owner_of(index, key, no),
            })
    return sorted(found, key=lambda f: (f["file"], f["line"]))


def find_dead(graph_path: str) -> dict:
    """Orphan nodes, plus the files in which every node is an orphan."""
    try:
        nodes, edges = analyze.load(graph_path)
    except SystemExit:                  # no graph built yet: markers still work
        return {"nodes": [], "files": []}
    orphans = set(analyze.find_orphans(nodes, edges))

    by_file: dict[str, list[str]] = {}
    for nid, n in nodes.items():
        by_file.setdefault((n.get("source") or "").split(":")[0], []).append(nid)
    dead_files = sorted(f for f, ids in by_file.items()
                        if f and ids and all(i in orphans for i in ids))

    detail = [{"id": nid, "source": nodes[nid].get("source"),
               "layer": nodes[nid].get("layer"), "kind": nodes[nid].get("kind")}
              for nid in sorted(orphans)]
    return {"nodes": detail, "files": dead_files}


def build(roots, graph_path: str = DEFAULT_GRAPH, out_path: str | None = None) -> dict:
    roots = [roots] if isinstance(roots, str) else list(roots)
    markers = find_markers(roots, graph_path)
    dead = find_dead(graph_path)

    by_tag: dict[str, int] = {}
    for m in markers:
        by_tag[m["tag"]] = by_tag.get(m["tag"], 0) + 1

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roots": [os.path.abspath(r) for r in roots],
        "graph": os.path.relpath(graph_path, SKILL_ROOT).replace("\\", "/"),
        "summary": {
            "markers": len(markers),
            "by_tag": dict(sorted(by_tag.items(), key=lambda kv: (-kv[1], kv[0]))),
            "dead_nodes": len(dead["nodes"]),
            "dead_files": len(dead["files"]),
        },
        "markers": markers,
        "dead_nodes": dead["nodes"],
        "dead_files": dead["files"],
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inventory TODO-style markers and dead code.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph used to attribute and find dead code")
    parser.add_argument("--out", default=None, help=f"Write the payload here (e.g. {DEFAULT_OUT})")
    parser.add_argument("--top", type=int, default=10, help="Rows to print per section")
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
    tags = ", ".join(f"{k} {v}" for k, v in s["by_tag"].items()) or "none"
    print(f"Debt: {s['markers']} marker(s) ({tags}), {s['dead_nodes']} dead node(s), "
          f"{s['dead_files']} dead file(s)")
    for m in d["markers"][:args.top]:
        owner = f" [{m['node']}]" if m["node"] else ""
        print(f"  {m['tag']:<10} {m['file']}:{m['line']}{owner}  {m['text']}")
    for n in d["dead_nodes"][:args.top]:
        print(f"  dead       {n['id']}  {n['source']}")
    for f in d["dead_files"][:args.top]:
        print(f"  dead file  {f}")
    if args.out:
        print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
