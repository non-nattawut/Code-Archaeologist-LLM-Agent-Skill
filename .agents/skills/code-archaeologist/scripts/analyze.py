#!/usr/bin/env python3
"""analyze.py — deterministic architectural smell report and health grade over a graph.

Because the dependency graph is explicit, the checks a reviewer cares about are
nearly free (no parsing, no tokens, stdlib only):

  cycles            circular dependencies (strongly-connected components > 1
                    node, plus self-loops) — the hardest coupling to untangle.
  orphans           nodes with no incoming edges that aren't entry points
                    (endpoints / controllers / route handlers) — likely dead code.
  layer_violations  edges that call "upward" against the standard layering
                    (controller -> service -> repository/client -> model), e.g. a
                    repository calling a controller — a backwards dependency.
  hubs              nodes whose total degree is very high — a change there ripples
                    everywhere (high coupling).
  god_objects       classes with too many methods, or entities referencing too many
                    others — the classic "does everything" anti-pattern.
  patterns          name-based recognition of singleton / factory / observer /
                    React-hook idioms, so the shape of the codebase is visible.
  health            a 0-100 score and A-F grade combining all of the above (plus
                    security findings when `--security` is given).

Works on either graph (structure graph.json or flow_graph.json).

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "structure", "graph.json")

sys.path.insert(0, SCRIPT_DIR)
import console      # noqa: E402  (stdout must survive a non-UTF-8 console)


# Standard layering, shallow -> deep. A call from a deeper layer to a shallower
# one is a backwards dependency. Layers absent here (function/module/ui/...) are
# not ranked, so their edges are never flagged (avoids noise).
LAYER_RANK = {"controller": 0, "service": 1, "repository": 2, "client": 2, "model": 3}

# Anti-pattern thresholds (tune here; they are deliberately conservative).
HUB_DEGREE = 10       # fan_in + fan_out at or above this = high coupling
GOD_METHODS = 12      # methods on one class (flow graph)
GOD_FANOUT = 8        # entities one entity references (structure graph)

# Name-based idiom recognition. Heuristic: it reports what the naming claims.
PATTERN_RULES = [
    ("singleton", re.compile(r"(get_?instance|shared_?instance|_instance$|singleton)", re.I)),
    ("factory", re.compile(r"(factory|^make_|^build_|\.make_|\.build_)", re.I)),
    ("observer", re.compile(r"(subscribe|unsubscribe|notify|emit|dispatch|add_?listener|publish)", re.I)),
    ("react_hook", re.compile(r"(^|\.)use[A-Z]")),
]

GRADES = [(90, "A"), (80, "B"), (70, "C"), (60, "D")]


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


def degrees(nodes: dict, edges: list[tuple[str, str, str]]) -> dict[str, dict]:
    deg = {nid: {"fan_in": 0, "fan_out": 0} for nid in nodes}
    for s, t, _ in edges:
        deg[s]["fan_out"] += 1
        deg[t]["fan_in"] += 1
    return deg


def find_hubs(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Highly coupled nodes — everything routes through them."""
    deg = degrees(nodes, edges)
    hubs = [{"node": nid, **d, "degree": d["fan_in"] + d["fan_out"]}
            for nid, d in deg.items() if d["fan_in"] + d["fan_out"] >= HUB_DEGREE]
    return sorted(hubs, key=lambda h: (-h["degree"], h["node"]))


def find_god_objects(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Classes with too many methods (flow graph) or too many references (structure graph)."""
    found = []
    methods: dict[str, int] = {}
    for n in nodes.values():
        if n.get("cls"):
            methods[n["cls"]] = methods.get(n["cls"], 0) + 1
    for cls, count in methods.items():
        if count >= GOD_METHODS:
            found.append({"name": cls, "reason": "methods", "count": count})

    deg = degrees(nodes, edges)
    for nid, n in nodes.items():
        if n.get("kind") == "class" and deg[nid]["fan_out"] >= GOD_FANOUT:
            found.append({"name": nid, "reason": "references", "count": deg[nid]["fan_out"]})
    return sorted(found, key=lambda g: (-g["count"], g["name"]))


def detect_patterns(nodes: dict) -> dict[str, list[str]]:
    """Group node ids by the design idiom their name advertises."""
    found: dict[str, list[str]] = {}
    for nid, n in nodes.items():
        for name, pattern in PATTERN_RULES:
            if name == "react_hook" and n.get("lang") not in ("js", None):
                continue
            if pattern.search(nid):
                found.setdefault(name, []).append(nid)
    return {k: sorted(v) for k, v in sorted(found.items())}


def health(node_count: int, cycles: list, orphans: list, violations: list,
           hubs: list, god_objects: list, security: dict | None = None) -> dict:
    """0-100 score and A-F grade. Every deduction is capped so one bad category
    can't sink the grade on its own; `security` is `{"high": n, "medium": n, "low": n}`."""
    sec = security or {}
    dead_pct = round(100 * len(orphans) / node_count, 1) if node_count else 0.0
    deductions = {
        "dead_code": min(20, round(dead_pct * 0.5)),
        "cycles": min(24, 8 * len(cycles)),
        "layer_violations": min(16, 4 * len(violations)),
        "high_coupling": min(12, 3 * len(hubs)),
        "god_objects": min(12, 3 * len(god_objects)),
        "security": min(30, 10 * sec.get("high", 0) + 4 * sec.get("medium", 0) + sec.get("low", 0)),
    }
    score = max(0, 100 - sum(deductions.values()))
    grade = next((g for cutoff, g in GRADES if score >= cutoff), "F")
    return {"score": score, "grade": grade, "dead_code_pct": dead_pct, "deductions": deductions}


def report(graph_path: str, security: dict | None = None) -> dict:
    nodes, edges = load(graph_path)
    cycles = find_cycles(nodes, edges)
    orphans = find_orphans(nodes, edges)
    violations = find_layer_violations(nodes, edges)
    hubs = find_hubs(nodes, edges)
    gods = find_god_objects(nodes, edges)
    patterns = detect_patterns(nodes)
    return {
        "cycles": cycles,
        "orphans": orphans,
        "layer_violations": violations,
        "hubs": hubs,
        "god_objects": gods,
        "patterns": patterns,
        "health": health(len(nodes), cycles, orphans, violations, hubs, gods, security),
        "summary": {"nodes": len(nodes), "edges": len(edges), "cycles": len(cycles),
                    "orphans": len(orphans), "layer_violations": len(violations),
                    "hubs": len(hubs), "god_objects": len(gods)},
    }


def to_text(d: dict) -> str:
    """The findings without the JSON envelope: grade, counts, then each list."""
    h, s = d["health"], d["summary"]
    out = [f"grade {h['grade']} ({h['score']}/100) - {s['nodes']} node(s), {s['edges']} edge(s)",
           f"cycles {s['cycles']}, orphans {s['orphans']}, layer violations {s['layer_violations']}, "
           f"hubs {s['hubs']}, god objects {s['god_objects']}"]
    out += [f"  deduction {k.replace('_', ' ')} -{v}" for k, v in h["deductions"].items() if v]
    out += ["  cycle     " + " > ".join(c) for c in d["cycles"]]
    out += [f"  violation {v['source']} -> {v['target']} ({v['from']} -> {v['to']})"
            for v in d["layer_violations"]]
    out += [f"  hub       {x['node']} in {x['fan_in']} / out {x['fan_out']}" for x in d["hubs"]]
    out += [f"  god       {g['name']} {g['reason']} {g['count']}" for g in d["god_objects"]]
    out += [f"  idiom     {k}: " + ", ".join(v) for k, v in d["patterns"].items()]
    out += [f"  orphan    {n}" for n in d["orphans"]]
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report architectural smells, anti-patterns and a health grade.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to graph.json / flow_graph.json")
    parser.add_argument("--security", default=None,
                        help="security.json from scan_security.py; folds findings into the grade")
    parser.add_argument("--format", choices=["text", "json"], default="json",
                        help="json (default, full detail) or text (grade + counts + the lists)")
    args = parser.parse_args(argv)
    console.safe_stdout()

    counts = None
    if args.security:
        with open(args.security, "r", encoding="utf-8") as fh:
            counts = json.load(fh).get("summary", {}).get("by_severity")
    data = report(args.graph, counts)
    print(to_text(data) if args.format == "text" else json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
