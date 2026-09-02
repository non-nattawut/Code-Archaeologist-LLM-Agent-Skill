#!/usr/bin/env python3
"""trace_path.py — Deterministic graph tracer (pure stdlib, no networkx).

Reads data/graph.json and answers two kinds of questions, emitting machine-
readable JSON node lists so the agent knows exactly which vault notes to read:

  Mode 1 (flow):    --from A --to B    shortest path A -> B  (--all for all paths)
  Mode 2 (impact):  --impact-of X      all upstream/transitive callers of X

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "graph.json")


def load_graph(path: str):
    if not os.path.isfile(path):
        _fail(f"graph not found at {path}; run build_graph.py first")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    nodes = {n["id"] for n in data.get("nodes", [])}
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    radj: dict[str, list[str]] = {n: [] for n in nodes}
    for e in data.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s in nodes and t in nodes:
            adj.setdefault(s, []).append(t)
            radj.setdefault(t, []).append(s)
    return nodes, adj, radj


def _emit(obj: dict, code: int = 0) -> int:
    print(json.dumps(obj, indent=2))
    return code


def _fail(msg: str) -> None:
    print(json.dumps({"error": msg}, indent=2), file=sys.stderr)
    raise SystemExit(1)


def bfs_shortest(adj: dict[str, list[str]], start: str, goal: str) -> list[str] | None:
    if start == goal:
        return [start]
    prev: dict[str, str] = {start: start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in prev:
                prev[nxt] = cur
                if nxt == goal:
                    return _reconstruct(prev, start, goal)
                q.append(nxt)
    return None


def _reconstruct(prev: dict[str, str], start: str, goal: str) -> list[str]:
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return list(reversed(path))


def all_simple_paths(adj, start, goal, max_paths=50, max_depth=25):
    """Bounded DFS enumeration of simple paths (guards against huge graphs)."""
    results: list[list[str]] = []

    def dfs(node, path, visited):
        if len(results) >= max_paths or len(path) > max_depth:
            return
        if node == goal:
            results.append(list(path))
            return
        for nxt in adj.get(node, []):
            if nxt not in visited:
                visited.add(nxt)
                path.append(nxt)
                dfs(nxt, path, visited)
                path.pop()
                visited.remove(nxt)

    dfs(start, [start], {start})
    return results


def impact_of(radj: dict[str, list[str]], target: str) -> list[str]:
    """Reverse-BFS: all transitive upstream callers of `target`."""
    seen: set[str] = set()
    q = deque([target])
    while q:
        cur = q.popleft()
        for caller in radj.get(cur, []):
            if caller not in seen:
                seen.add(caller)
                q.append(caller)
    return sorted(seen)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Trace flow paths or blast-radius impact in graph.json.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to graph.json")
    parser.add_argument("--from", dest="src", help="Source node (flow mode)")
    parser.add_argument("--to", dest="dst", help="Target node (flow mode)")
    parser.add_argument("--all", action="store_true", help="List all simple paths, not just shortest")
    parser.add_argument("--impact-of", dest="impact", help="List all upstream callers of this node")
    args = parser.parse_args(argv)

    nodes, adj, radj = load_graph(args.graph)
    if not nodes:
        _fail("graph is empty; run build_wiki.py then build_graph.py")

    if args.impact:
        if args.impact not in nodes:
            _fail(f"unknown node '{args.impact}'")
        impacted = impact_of(radj, args.impact)
        return _emit({
            "mode": "impact",
            "target": args.impact,
            "impacted": impacted,
            "count": len(impacted),
        })

    if args.src and args.dst:
        for label, node in (("--from", args.src), ("--to", args.dst)):
            if node not in nodes:
                _fail(f"unknown node for {label}: '{node}'")
        if args.all:
            paths = all_simple_paths(adj, args.src, args.dst)
            return _emit({
                "mode": "flow-all",
                "from": args.src,
                "to": args.dst,
                "paths": paths,
                "count": len(paths),
                "found": bool(paths),
            })
        path = bfs_shortest(adj, args.src, args.dst)
        return _emit({
            "mode": "flow",
            "from": args.src,
            "to": args.dst,
            "path": path or [],
            "found": path is not None,
        }, code=0 if path else 0)

    _fail("provide either --from A --to B, or --impact-of X")


if __name__ == "__main__":
    raise SystemExit(main())
