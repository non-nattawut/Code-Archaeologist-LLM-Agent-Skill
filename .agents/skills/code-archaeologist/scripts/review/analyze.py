#!/usr/bin/env python3
"""analyze.py — deterministic architectural smell report and health grade over a graph.

Because the dependency graph is explicit, the checks a reviewer cares about are
nearly free (no parsing, no tokens, stdlib only):

  cycles            circular dependencies (strongly-connected components > 1
                    node, plus self-loops) — the hardest coupling to untangle.
  orphans           nodes with no incoming edges that aren't entry points
                    (endpoints / controllers / route handlers / React components)
                    — likely dead code.
  layer_violations  edges that call "upward" against the standard layering
                    (controller -> service -> repository/client -> model), e.g. a
                    repository calling a controller — a backwards dependency.
  hubs              nodes depended on by many *and* depending on many — changes arrive
                    from every direction and spread to every caller (high coupling).
  shared_helpers    used by many, depending on nearly nothing. Normal, and reported
                    rather than graded — see `health`.
  coordinators      calling many, called by almost nothing. Worth watching, also not graded.
  wrong_way_deps    a stable node calling an unstable one — a dependency pointing the
                    wrong way, which layer ranks only catch when both ends are ranked.
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_GRAPH = os.path.join(DATA_DIR, "structure", "graph.json")

import console      # noqa: E402  (stdout must survive a non-UTF-8 console)
from taxonomy import CLASS_KINDS, INHERITANCE_LINKS, call_direction  # noqa: E402  (which way an inheritance link is walked)


# Standard layering, shallow -> deep. A call from a deeper layer to a shallower
# one is a backwards dependency. Layers absent here (function/module/ui/...) are
# not ranked, so their edges are never flagged (avoids noise).
LAYER_RANK = {"controller": 0, "service": 1, "repository": 2, "client": 2, "model": 3}

# Anti-pattern thresholds (tune here; they are deliberately conservative).
GOD_METHODS = 12      # methods on one class (flow graph)
GOD_FANOUT = 8        # entities one entity references (structure graph)

# Coupling is a direction, not a count. Robert Martin's instability
#     I = fan_out / (fan_in + fan_out)      0 = stable, 1 = unstable
# separates three shapes that a total-degree count folds into one, only one of which
# is a problem. `GlobalResponse.success` with 40 callers and no callees scored exactly
# as badly as a method that is called from everywhere *and* calls everything.
HELPER_FAN_IN = 10            # used by many...
HELPER_INSTABILITY = 0.1      # ...and depending on nearly nothing: a shared helper.
HUB_FAN_IN = 5                # depended on by many *and*
HUB_FAN_OUT = 5               # depending on many: the shape that actually hurts.
COORD_FAN_OUT = 10            # calls many...
COORD_FAN_IN = 2              # ...and almost nothing calls it: a coordinator.
# A stable node depending on an unstable one is a dependency pointing the wrong way:
# the thing everything relies on is built on the thing that keeps changing.
WRONG_WAY_CALLER_I = 0.3      # the caller is stable...
WRONG_WAY_CALLEE_I = 0.7      # ...the callee is not, and
WRONG_WAY_FAN_IN = 5          # enough depends on the caller for it to matter.

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
    for s, t, kind in edges:
        if kind not in INHERITANCE_LINKS:    # a decorator delegating to its own interface is not a cycle
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
    Dunder methods (e.g. __init__) are excluded — they're called implicitly, and so
    is test code — a runner calls it, so nothing in the graph ever will."""
    # An implementation is reached through the declaration its `implements` link names.
    has_caller = {call_direction(s, t, kind)[1] for s, t, kind in edges}
    # ...and the base end is *named* by the class that inherits it: `class Audited extends
    # Auditable` is a reference to Auditable written in Audited's own source, which an IDE
    # counts as a usage. The flip above only ever marks the child, so a base class with
    # twelve subclasses and no other mention was reported dead (r74). Not `overrides`:
    # replacing a method does not reference the base method's body (`find_overridden` is
    # where that case is reported).
    has_caller |= {t for s, t, kind in edges if kind in ("implements", "extends")}
    # A call that could not pick an overload (`this::values`, `values(x)` with x untyped)
    # still calls one of them: `ambiguous` names the set, and none of it is dead.
    maybe_called = {base.rpartition(".")[::2] for n in nodes.values() for base in n.get("ambiguous") or []}
    orphans = []
    for nid, n in nodes.items():
        if nid in has_caller or _is_dunder(nid):
            continue
        if nid.endswith(")") and ((n.get("cls") or ""), nid[:nid.index("(")].rpartition(".")[2]) in maybe_called:
            continue
        # A React component is mounted by the framework and a route handler is
        # called by the server: in both cases the caller is outside the graph, so
        # having no incoming edge says nothing about whether the code is used.
        # A body-less declaration is excluded for a different reason -- it holds
        # no code at all, so "dead code" is the wrong question to ask of it.
        # `entry` names a framework caller the graph cannot see (`@Scheduled`,
        # `override`, `next:page`) -- the same reason as a route, stated per node.
        # `overridden` is listed on its own (find_overridden): its body never runs, but
        # deleting it changes what a new subclass inherits, which dead code never does.
        is_entry = (n.get("kind") in ("endpoint", "component") or bool(n.get("routes"))
                    or n.get("layer") in ("controller", "test")
                    or bool(n.get("declaration")) or bool(n.get("entry")) or bool(n.get("overridden")))
        if not is_entry:
            orphans.append(nid)
    return sorted(orphans)


def find_overridden(nodes: dict, edges: list[tuple[str, str, str]]) -> list[str]:
    """Methods with a body that nothing calls and every subclass replaces: the body never
    runs today. Not graded -- it is a design question (is the default still wanted?), not rot."""
    has_caller = {call_direction(s, t, kind)[1] for s, t, kind in edges}
    return sorted(nid for nid, n in nodes.items() if n.get("overridden") and nid not in has_caller)


def find_layer_violations(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Backwards (deep -> shallow) call edges. Cross-stack `http` edges are
    skipped — a frontend client calling a backend controller is the intended
    direction across the API boundary, not a violation. Nor is an `implements` link:
    it is not a call in either direction."""
    violations = []
    for s, t, etype in edges:
        if etype == "http" or etype in INHERITANCE_LINKS:
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


def app_edges(nodes: dict, edges: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Edges between application nodes only.

    A test calls production code, which is coverage, not coupling: counting those
    calls would make every well-tested function look like a hub. A `renders` edge is
    the component tree, followed by traces but not counted as call coupling either, and
    an `implements` link says which class a method belongs to, not who calls whom.
    """
    return [e for e in edges
            if nodes[e[0]].get("layer") != "test" and nodes[e[1]].get("layer") != "test"
            and e[2] not in ("renders", "passes") and e[2] not in INHERITANCE_LINKS]


def instability(fan_in: int, fan_out: int) -> float:
    """Robert Martin's I = fan_out / (fan_in + fan_out). 0 = stable (everything depends
    on it, it depends on nothing), 1 = unstable (it depends on everything, nothing on it).
    A node with no edges at all has no direction to measure, and is 0.0 by convention."""
    total = fan_in + fan_out
    return round(fan_out / total, 3) if total else 0.0


def coupling(nodes: dict, edges: list[tuple[str, str, str]]) -> dict[str, dict]:
    """Per-node fan-in / fan-out / instability, over application edges only."""
    return {nid: {**d, "degree": d["fan_in"] + d["fan_out"],
                  "instability": instability(d["fan_in"], d["fan_out"])}
            for nid, d in degrees(nodes, app_edges(nodes, edges)).items()}


def _by_degree(found: list[dict]) -> list[dict]:
    return sorted(found, key=lambda x: (-x["degree"], x["node"]))


def find_hubs(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Nodes many things depend on that *also* depend on many things.

    Both directions at once is the shape that hurts: changes arrive from every caller
    and spread to every callee. A node with only one of the two is a shared helper or a
    coordinator — reported below, not deducted for. Counting total degree alone folded all
    three together, so a codebase with a well-used `GlobalResponse.success` scored as badly
    as one that is genuinely tangled."""
    return _by_degree([{"node": nid, **d} for nid, d in coupling(nodes, edges).items()
                       if d["fan_in"] >= HUB_FAN_IN and d["fan_out"] >= HUB_FAN_OUT])


def find_shared_helpers(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Used by many, depending on nearly nothing — `DateUtil.now`, `errorAlert`.

    This is what a shared helper is supposed to look like, so it is reported to be
    visible (a change there still reaches everyone) and never graded."""
    return _by_degree([{"node": nid, **d} for nid, d in coupling(nodes, edges).items()
                       if d["fan_in"] >= HELPER_FAN_IN and d["instability"] <= HELPER_INSTABILITY])


def find_coordinators(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Calls a great many things, and almost nothing calls it — a registration method,
    a top-level panel. Worth watching (it can grow into a god method) but low risk while
    nothing depends on it, and `god_objects` already penalises the class-level version,
    so this is reported without a deduction rather than counted twice."""
    return _by_degree([{"node": nid, **d} for nid, d in coupling(nodes, edges).items()
                       if d["fan_out"] >= COORD_FAN_OUT and d["fan_in"] <= COORD_FAN_IN])


def find_wrong_way_deps(nodes: dict, edges: list[tuple[str, str, str]]) -> list[dict]:
    """Calls from a stable node into an unstable one — a dependency pointing the wrong way.

    A helper that much of the codebase depends on should depend on little itself; when it
    reaches into something that depends on everything, every change to the unstable end
    travels out through the stable one's callers. Layer violations catch the same mistake
    only where both ends carry a ranked layer; this catches it from the shape alone."""
    coup = coupling(nodes, edges)
    found = [{"source": s, "target": t,
              "source_instability": coup[s]["instability"],
              "target_instability": coup[t]["instability"],
              "source_fan_in": coup[s]["fan_in"]}
             for s, t, kind in app_edges(nodes, edges)
             if s != t and coup[s]["fan_in"] >= WRONG_WAY_FAN_IN
             and coup[s]["instability"] < WRONG_WAY_CALLER_I
             and coup[t]["instability"] > WRONG_WAY_CALLEE_I]
    seen, unique = set(), []
    for v in found:                     # one edge may be written twice (two call sites)
        if (v["source"], v["target"]) not in seen:
            seen.add((v["source"], v["target"]))
            unique.append(v)
    return sorted(unique, key=lambda v: (v["source"], v["target"]))


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

    deg = degrees(nodes, app_edges(nodes, edges))
    for nid, n in nodes.items():
        if n.get("kind") in CLASS_KINDS and deg[nid]["fan_out"] >= GOD_FANOUT:
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
           hubs: list, god_objects: list, security: dict | None = None,
           wrong_way: list | None = None) -> dict:
    """0-100 score and A-F grade. Every deduction is capped so one bad category
    can't sink the grade on its own; `security` is `{"high": n, "medium": n, "low": n}`.

    Shared helpers and coordinators are reported but never deducted for: both are
    normal shapes, and grading them made a codebase score worse for having a well-used
    utility. Only `hubs` (coupled in both directions) and `wrong_way` count."""
    sec = security or {}
    dead_pct = round(100 * len(orphans) / node_count, 1) if node_count else 0.0
    deductions = {
        "dead_code": min(20, round(dead_pct * 0.5)),
        "cycles": min(24, 8 * len(cycles)),
        "layer_violations": min(16, 4 * len(violations)),
        "high_coupling": min(12, 3 * len(hubs)),
        "wrong_way_deps": min(8, 2 * len(wrong_way or [])),
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
    overridden = find_overridden(nodes, edges)
    violations = find_layer_violations(nodes, edges)
    hubs = find_hubs(nodes, edges)
    helpers = find_shared_helpers(nodes, edges)
    coordinators = find_coordinators(nodes, edges)
    wrong_way = find_wrong_way_deps(nodes, edges)
    gods = find_god_objects(nodes, edges)
    patterns = detect_patterns(nodes)
    return {
        "cycles": cycles,
        "orphans": orphans,
        "overridden": overridden,
        "layer_violations": violations,
        "hubs": hubs,
        "shared_helpers": helpers,
        "coordinators": coordinators,
        "wrong_way_deps": wrong_way,
        "god_objects": gods,
        "patterns": patterns,
        "health": health(len(nodes), cycles, orphans, violations, hubs, gods, security, wrong_way),
        "summary": {"nodes": len(nodes), "edges": len(edges), "cycles": len(cycles),
                    "orphans": len(orphans), "overridden": len(overridden),
                    "layer_violations": len(violations),
                    "hubs": len(hubs), "shared_helpers": len(helpers),
                    "coordinators": len(coordinators), "wrong_way_deps": len(wrong_way),
                    "god_objects": len(gods)},
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
    out += [f"  hub       {x['node']} in {x['fan_in']} / out {x['fan_out']} I={x['instability']}"
            for x in d["hubs"]]
    out += [f"  wrong-way {v['source']} -> {v['target']} "
            f"(I {v['source_instability']} -> {v['target_instability']})"
            for v in d.get("wrong_way_deps", [])]
    out += [f"  god       {g['name']} {g['reason']} {g['count']}" for g in d["god_objects"]]
    out += [f"  orphan    {n}" for n in d["orphans"]]
    out += [f"  helper    {x['node']} in {x['fan_in']} / out {x['fan_out']} (not graded)"
            for x in d.get("shared_helpers", [])]
    out += [f"  coord     {x['node']} in {x['fan_in']} / out {x['fan_out']} (not graded)"
            for x in d.get("coordinators", [])]
    out += [f"  overridden {n}" for n in d.get("overridden", [])]
    out += [f"  idiom     {k}: " + ", ".join(v) for k, v in d["patterns"].items()]
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
