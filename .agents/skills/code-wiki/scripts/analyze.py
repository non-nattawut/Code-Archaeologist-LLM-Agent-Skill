#!/usr/bin/env python3
"""analyze.py — deterministic architectural smell report over a graph.

Because the dependency graph is explicit, three high-value checks a reviewer
cares about are nearly free (no parsing, no tokens, stdlib only):

  cycles            circular dependencies (strongly-connected components > 1
                    node, plus self-loops) — the hardest coupling to untangle.
  orphans           nodes with no incoming edges that aren't entry points
                    (endpoints / controllers / route handlers) — likely dead code.
  layer_violations  edges that call "upward" against the standard layering
                    (controller -> service -> repository/client -> model), e.g. a
                    repository calling a controller — a backwards dependency.

Works on either graph (structure graph.json or flow_graph.json).

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "structure", "graph.json")

# Standard layering, shallow -> deep. A call from a deeper layer to a shallower
# one is a backwards dependency. Layers absent here (function/module/ui/...) are
# not ranked, so their edges are never flagged (avoids noise).
LAYER_RANK = {"controller": 0, "service": 1, "repository": 2, "client": 2, "model": 3}


def load(path: str) -> tuple[dict, list[tuple[str, str, str]]]:
    if not os.path.isfile(path):
        print(json.dumps({"error": f"graph not found at {path}"}, indent=2), file=sys.stderr)
        raise SystemExit(1)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    nodes = {n["id"]: n for n in data.get("nodes", [])}
    edges = [(e["source"], e["target"], e.get("type", "")) for e in data.get("edges", [])
             if e.get("source") in nodes and e.get("target") in nodes]
    return nodes, edges


def find_cycles(nodes: dict, edges: list[tuple[str, str, str]]) -> list[list[str]]:
    """Strongly-connected components with > 1 node (iterative Tarjan), plus self-loops."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for s, t, _ in edges:
        adj[s].append(t)

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = [0]
    sccs: list[list[str]] = []

    def strongconnect(root: str):
        # Explicit stack to avoid recursion limits on large graphs.
        work = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = counter[0]
                counter[0] += 1
                stack.append(v)
                on_stack.add(v)
            recursed = False
            for i in range(pi, len(adj[v])):
                w = adj[v][i]
                if w not in index:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                elif w in on_stack:
                    low[v] = min(low[v], index[w])
            if recursed:
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    sccs.append(sorted(comp))
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])

    for n in nodes:
        if n not in index:
            strongconnect(n)

    self_loops = sorted([s] for s, t, _ in edges if s == t)
    return sorted(sccs + self_loops)


def _is_dunder(name: str) -> bool:
    base = name.rsplit(".", 1)[-1]
    return base.startswith("__") and base.endswith("__")


def find_orphans(nodes: dict, edges: list[tuple[str, str, str]]) -> list[str]:
    """Nodes with no incoming edges that aren't legitimate entry points.
    Dunder methods (e.g. __init__) are excluded — they're called implicitly."""
    has_caller = {t for _, t, _ in edges}
    orphans = []
    for nid, n in nodes.items():
        if nid in has_caller or _is_dunder(nid):
            continue
        is_entry = (n.get("kind") == "endpoint" or n.get("layer") == "controller"
                    or bool(n.get("route")))
        if not is_entry:
            orphans.append(nid)
    return sorted(orphans)


def find_layer_violations(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Backwards (deep -> shallow) call edges. Cross-stack `http` edges are
    skipped — a frontend client calling a backend controller is the intended
    direction across the API boundary, not a violation."""
    violations = []
    for s, t, etype in edges:
        if etype == "http":
            continue
        sl, tl = nodes[s].get("layer"), nodes[t].get("layer")
        if sl in LAYER_RANK and tl in LAYER_RANK and LAYER_RANK[tl] < LAYER_RANK[sl]:
            violations.append({"source": s, "target": t, "from": sl, "to": tl})
    return sorted(violations, key=lambda v: (v["source"], v["target"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report architectural smells (cycles, orphans, layer violations).")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to graph.json / flow_graph.json")
    args = parser.parse_args(argv)

    nodes, edges = load(args.graph)
    cycles = find_cycles(nodes, edges)
    orphans = find_orphans(nodes, edges)
    violations = find_layer_violations(nodes, edges)
    print(json.dumps({
        "cycles": cycles,
        "orphans": orphans,
        "layer_violations": violations,
        "summary": {"cycles": len(cycles), "orphans": len(orphans),
                    "layer_violations": len(violations)},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
