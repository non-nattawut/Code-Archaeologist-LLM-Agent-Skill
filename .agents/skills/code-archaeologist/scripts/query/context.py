#!/usr/bin/env python3
"""context.py — everything about a node, in one call.

The normal way to answer "what is this and what touches it" costs a trace plus
one file read per node on the path. This assembles the same answer from the
artifacts already on disk and returns it as one budgeted block:

  the node          kind, layer, source, size, complexity, churn, route
  what it does      the resolved description (docstring / cached AI / fallback)
  what it calls     immediate callees, each with its own one-line description
  what calls it     immediate callers, same
  what is risky     the scan findings attributed to it
  what covers it    the tests that call it (real call edges, not name matching)

    python context.py --node OrderService.place_order
    python context.py --node A B C --depth 2 --max-chars 8000
    python context.py --diff                    # every node the current diff touches
    python context.py --node X --format json

`--max-chars` is a hard budget: neighbor lists shrink until the pack fits, and
the pack says so when it trimmed. Reads the graph and, when present, the report
artifacts (metrics/security/insights) — never source.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR, SKILL_ROOT  # noqa: E402  (also puts sibling script dirs on sys.path)
REPORT_DIR = os.path.join(DATA_DIR, "report")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")

import console         # noqa: E402  (stdout must survive a non-UTF-8 console)
import trace_path      # noqa: E402  (one definition of "which nodes did this diff touch")

DOC_CHARS = 200
NEIGHBOR_CAPS = (12, 6, 3, 1)      # tried in order until the pack fits the budget


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _map_of(graph_path: str) -> str:
    return "flow" if os.path.basename(graph_path) == "flow_graph.json" else "structure"


def _side_data(graph_path: str) -> dict:
    """metrics / security / insights for this map, if the review pass has run."""
    out_dir = os.path.join(REPORT_DIR, _map_of(graph_path))
    metrics = _load(os.path.join(out_dir, "metrics.json")) or {}
    security = _load(os.path.join(out_dir, "security.json")) or {}
    insights = _load(os.path.join(out_dir, "insights.json")) or {}
    risks: dict[str, list[dict]] = {}
    for f in security.get("findings", []):
        if f.get("node"):
            risks.setdefault(f["node"], []).append(f)
    return {"metrics": metrics.get("nodes", {}), "risks": risks, "churn": insights.get("nodes", {})}


def _trim(text: str) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= DOC_CHARS else line[:DOC_CHARS - 3].rstrip() + "..."


def _neighbors(ids: list[str], nodes: dict, cap: int) -> list[dict]:
    shown = sorted(ids)[:cap]
    return [{"id": i, "doc": _trim(nodes.get(i, {}).get("doc", ""))} for i in shown]


def build(graph_path: str, node_ids: list[str], depth: int = 1, cap: int = NEIGHBOR_CAPS[0]) -> dict:
    graph = _load(graph_path)
    if graph is None:
        raise SystemExit(f"error: graph not found at {graph_path} - build a map first")
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    out: dict[str, list[str]] = {}
    inc: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s in nodes and t in nodes:
            out.setdefault(s, []).append(t)
            inc.setdefault(t, []).append(s)
    side = _side_data(graph_path)

    def walk(start: str, adj: dict) -> list[str]:
        """Node ids within `depth` hops of start, excluding start itself."""
        seen, frontier = {start}, [start]
        for _ in range(max(depth, 1)):
            nxt = [n for f in frontier for n in adj.get(f, []) if n not in seen]
            seen.update(nxt)
            frontier = nxt
        return [n for n in seen if n != start]

    packs = []
    for nid in node_ids:
        node = nodes.get(nid)
        if node is None:
            packs.append({"id": nid, "found": False})
            continue
        callees, callers = walk(nid, out), walk(nid, inc)
        # A test that calls this node covers it -- real call edges, not name matching.
        covered_by = sorted(i for i in inc.get(nid, []) if nodes[i].get("layer") == "test")
        callers = [i for i in callers if i not in set(covered_by)]
        packs.append({
            "id": nid,
            "found": True,
            "kind": node.get("kind"),
            "layer": node.get("layer"),
            "lang": node.get("lang"),
            "source": node.get("source"),
            "signature": node.get("signature"),
            "route": node.get("route"),
            "http": node.get("http"),
            "ext_calls": node.get("ext"),
            "doc": _trim(node.get("doc", "")),
            "metrics": side["metrics"].get(nid, {}),
            "churn": side["churn"].get(nid, {}),
            "risks": side["risks"].get(nid, []),
            "calls": _neighbors(callees, nodes, cap),
            "called_by": _neighbors(callers, nodes, cap),
            "calls_total": len(callees),
            "called_by_total": len(callers),
            "covered_by": covered_by,
        })
    return {"graph": os.path.relpath(graph_path, SKILL_ROOT).replace("\\", "/"),
            "map": _map_of(graph_path), "depth": depth, "nodes": packs}


def to_markdown(pack: dict) -> str:
    lines: list[str] = []
    for n in pack["nodes"]:
        if not n["found"]:
            lines += [f"# {n['id']}", "", f"_Not in the {pack['map']} map._", ""]
            continue
        facts = [x for x in (n.get("kind"), n.get("layer"), n.get("lang"), n.get("source")) if x]
        m, c = n.get("metrics") or {}, n.get("churn") or {}
        if m:
            facts.append(f"{m.get('loc')} LOC, cx {m.get('complexity')}, depth {m.get('depth')}")
        if c:
            facts.append(f"{c.get('commits')} commit(s)" + (f", {c['owner']}" if c.get("owner") else ""))
        lines += [f"# {n['id']}", "", " | ".join(str(f) for f in facts), ""]
        if n.get("signature"):
            lines += [f"`{n['signature']}`", ""]
        lines += [n["doc"] or "_No description._", ""]
        if n.get("route"):
            r = n["route"]
            lines += [f"**Route:** `{r.get('method', '')} {r.get('path', '')}`", ""]
        for label, key, total in (("Calls", "calls", "calls_total"),
                                  ("Called by", "called_by", "called_by_total")):
            rows = n[key]
            more = n[total] - len(rows)
            lines.append(f"## {label} ({n[total]})" if n[total] else f"## {label}")
            lines.append("")
            lines += [f"- `{r['id']}` - {r['doc'] or 'no description'}" for r in rows] or ["_None._"]
            if more > 0:
                lines.append(f"- _...{more} more_")
            lines.append("")
        if n.get("covered_by"):
            lines += [f"## Covered by ({len(n['covered_by'])} test(s))", ""]
            lines += [f"- `{t}`" for t in n["covered_by"]]
            lines.append("")
        if n["risks"]:
            lines += ["## Risks", ""]
            lines += [f"- **{r['severity']}** `{r['rule']}` {r['file']}:{r['line']}" for r in n["risks"]]
            lines.append("")
        if n.get("http"):
            lines += ["## HTTP calls", ""]
            lines += [f"- `{h['method']} {h['url']}`" for h in n["http"]]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render(graph_path: str, node_ids: list[str], depth: int, max_chars: int, as_json: bool) -> str:
    """Build the pack at the largest neighbor cap that fits the budget."""
    for cap in NEIGHBOR_CAPS:
        pack = build(graph_path, node_ids, depth, cap)
        text = json.dumps(pack, indent=2) if as_json else to_markdown(pack)
        if len(text) <= max_chars or cap == NEIGHBOR_CAPS[-1]:
            if len(text) > max_chars:      # cut on a line boundary, not mid-word
                cut = text[:max_chars]
                text = cut[:cut.rfind("\n") + 1 or max_chars] + f"\n_[trimmed to {max_chars} chars]_\n"
            return text
    return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One budgeted context pack for one or more nodes.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to the graph (default: the flow map)")
    parser.add_argument("--node", nargs="+", default=None, help="Node id(s) to pack")
    parser.add_argument("--diff", action="store_true", help="Pack every node the current git diff touches")
    parser.add_argument("--base", help="Diff against this git ref (with --diff)")
    parser.add_argument("--staged", action="store_true", help="Use staged changes (with --diff)")
    parser.add_argument("--depth", type=int, default=1, help="How many hops of neighbors to include")
    parser.add_argument("--max-chars", type=int, default=6000, help="Hard budget for the output")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="Output format")
    args = parser.parse_args(argv)
    console.safe_stdout()

    ids = list(args.node or [])
    if args.diff:
        _, _, _, sources = trace_path.load_graph(args.graph)
        files = trace_path._changed_files(args.base, args.staged)
        ids += [i for i in trace_path._nodes_for_files(sources, files) if i not in ids]
        if not ids:
            print("No graph node matches the current diff.", file=sys.stderr)
            return 0
    if not ids:
        parser.error("give --node <id> [...] or --diff")

    print(render(args.graph, ids, args.depth, args.max_chars, args.format == "json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
