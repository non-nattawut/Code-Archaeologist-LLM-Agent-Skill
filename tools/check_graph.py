#!/usr/bin/env python3
"""check_graph.py -- does the graph deserve to be trusted?

The skill's promise is that an agent can read the graph instead of the source.
Every bug this project has recorded broke that promise *silently*: the build
exited 0 and the graph was quietly smaller or quietly wrong. This asserts the
invariants a correct graph must satisfy, on any built graph, so a wrong one
cannot pass as a small one.

    python tools/check_graph.py                   # both maps under data/
    python tools/check_graph.py --map flow        # one map
    python tools/check_graph.py --src ./src       # resolve node sources against these roots
    python tools/check_graph.py --self-test       # prove every check can fail

Two kinds of check:

  C..  structural invariants of the artifact: every edge lands on a node, ids are
       unique, a node's `source` range really contains its declaration, a call
       edge's target is really named inside its caller, `precision` is what the
       graph implies, the report's counts are the graph's counts, and every
       security finding lies inside the node it is attributed to.
  D..  derived features, tested metamorphically: the real graph is copied, a
       known defect is injected (a cycle, an orphan, a hub...), and the analysis
       must report it. A detector that returns nothing looks exactly like a clean
       codebase, so "it found zero cycles" is only evidence if it can find one.

`--self-test` is the rule the plan set for this phase -- *an assertion that
cannot fail is worse than none* -- written as code: it breaks the input for each
check on purpose (or swaps an analysis function for a broken one) and fails if
that check stays quiet.

Repo tool, not part of the installed skill. Roots default to the ones the last
build recorded, so run it from the directory the build was run from.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(REPO, ".agents", "skills", "code-archaeologist")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import paths  # noqa: E402,F401  (puts the category dirs and vendor/ on sys.path)
from paths import DATA_DIR  # noqa: E402

import analyze  # noqa: E402
import console  # noqa: E402
import context  # noqa: E402
import duplicates  # noqa: E402
import ids  # noqa: E402
import manifest  # noqa: E402
import scan_security  # noqa: E402
import taxonomy  # noqa: E402
import trace_path  # noqa: E402

MAPS = {"flow": os.path.join(DATA_DIR, "flow", "flow_graph.json"),
        "structure": os.path.join(DATA_DIR, "structure", "graph.json")}
EDGE_TYPES = {"flow": {"calls", "http"}, "structure": {"references"}}
VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
LANGS = set(taxonomy.LANG_BY_EXT.values())


class Ctx:
    """One map, its report, and the source files its nodes point into."""

    def __init__(self, kind: str, graph: dict, report: dict, files: dict, graph_path: str, roots):
        self.kind, self.graph, self.report, self.files = kind, graph, report or {}, files
        self.graph_path, self.roots = graph_path, roots
        self.nodes = graph.get("nodes", [])
        self.edges = graph.get("edges", [])
        self.by_id = {n["id"]: n for n in self.nodes}
        self._lines: dict[str, list[str] | None] = {}

    def lines(self, key: str):
        if key not in self._lines:
            full = self.files.get(key)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    self._lines[key] = fh.read().splitlines()
            except (OSError, TypeError):
                self._lines[key] = None
        return self._lines[key]

    def body(self, node: dict) -> str | None:
        """The node's source range as text, or None when it cannot be read."""
        path, line = split_source(node.get("source"))
        lines = self.lines(path)
        if lines is None or line is None:
            return None
        end = node.get("end") if isinstance(node.get("end"), int) else line
        return "\n".join(lines[line - 1:max(line, end)])

    def analysis_shapes(self):
        """The (nodes, edges) shapes analyze.py works on."""
        nodes = {n["id"]: dict(n) for n in self.nodes}
        edges = [(e["source"], e["target"], e.get("type", "")) for e in self.edges
                 if e.get("source") in nodes and e.get("target") in nodes]
        return nodes, edges


def split_source(src):
    """'path:line' -> (path, line); a bare path -> (path, None)."""
    path, _, line = (src or "").rpartition(":")
    if path and line.isdigit():
        return path, int(line)
    return src or "", None


def short(nid: str) -> str:
    return ids.bare(nid)       # an overload's id carries its parameter types; the source does not


def synthetic(nid: str) -> bool:
    """An inline route endpoint (`GET /go/healthz`) -- it has no name of its own."""
    return " " in nid


# --- C: structural invariants --------------------------------------------------

def c01_dangling(c):
    return [f"edge {e.get('source')} -> {e.get('target')}: endpoint is not a node"
            for e in c.edges if e.get("source") not in c.by_id or e.get("target") not in c.by_id]


def c02_duplicate_ids(c):
    seen, out = {}, []
    for n in c.nodes:
        if n["id"] in seen:
            out.append(f"{n['id']}: one id for two nodes ({seen[n['id']]} and {n.get('source')})"
                       " -- the last one wins silently")
        else:
            seen[n["id"]] = n.get("source")
    return out


def c03_edge_types(c):
    ok = EDGE_TYPES[c.kind]
    return [f"edge {e.get('source')} -> {e.get('target')}: type {e.get('type')!r} is not one of {sorted(ok)}"
            for e in c.edges if e.get("type") not in ok]


def c04_taxonomy(c):
    out = []
    for n in c.nodes:
        for field, allowed in (("layer", taxonomy.LAYERS), ("kind", taxonomy.KINDS), ("lang", LANGS)):
            if n.get(field) not in allowed:
                out.append(f"{n['id']}: {field} {n.get(field)!r} is not a value taxonomy.py knows")
    return out


def c05_source(c):
    out = []
    for n in c.nodes:
        path, line = split_source(n.get("source"))
        if c.kind == "flow" and (line is None or line < 1):
            out.append(f"{n['id']}: source {n.get('source')!r} carries no line number")
        if path not in c.files:
            out.append(f"{n['id']}: source file {path!r} is not a scanned source file")
    return out


def c06_end_range(c):
    # Both maps: structure classes and components carry a range since phase 6a. A
    # module group has no line, so the `line is None` skip below covers it.
    out = []
    for n in c.nodes:
        path, line = split_source(n.get("source"))
        lines, end = c.lines(path), n.get("end")
        if line is None or lines is None:
            continue                                     # C05 reports it
        if not isinstance(end, int) or end < line:
            out.append(f"{n['id']}: end {end!r} is before its start line {line}")
        elif end > len(lines):
            out.append(f"{n['id']}: end {end} is past the end of {path} ({len(lines)} lines)")
    return out


def c07_name_at_source(c):
    """A node's range must contain its own name -- else it points somewhere else.

    An off-by-one here mis-attributes every security finding, churn number and
    clone range that lands on the node, and nothing downstream would notice.
    """
    out = []
    for n in c.nodes:
        path, line = split_source(n.get("source"))
        lines = c.lines(path)
        if lines is None:
            continue
        if c.kind == "structure" and n.get("kind") == "module":
            continue                                     # a synthetic "<File>Module" entity
        if line is not None:
            # A shared name is file-qualified (`widgets.WidgetStore`); the file spells the
            # bare name, which is the id's last segment.
            body = c.body(n) or ""
            want = ([r["path"] for r in n.get("routes") or []] if synthetic(n["id"])
                    else [short(n["id"])])
            where = f"{path}:{line}-{n.get('end')}"
        elif c.kind == "flow":
            continue                                     # C05 reports a flow node with no line
        else:
            body, want, where = "\n".join(lines), [short(n["id"])], path
        if want and not any(w in body for w in want):
            out.append(f"{n['id']}: {want[0]!r} does not occur in {where} -- the range points elsewhere")
    return out


def c08_declaration_calls(c):
    return [f"{e['source']}: a declaration (signature, no body) has a call edge to {e['target']}"
            for e in c.edges if e.get("type") == "calls" and c.by_id.get(e.get("source"), {}).get("declaration")]


def c09_precision(c):
    if c.kind != "flow":
        return [f"{n['id']}: a structure node carries `precision`" for n in c.nodes if n.get("precision")]
    out, targets = [], {}
    for e in c.edges:
        targets.setdefault(e["source"], []).append(e["target"])
    for n in c.nodes:
        got = n.get("precision") or []
        unknown = [r for r in got if r not in taxonomy.PRECISION_REASONS]
        if unknown:
            out.append(f"{n['id']}: precision value(s) {unknown} are not in taxonomy.PRECISION_REASONS")
        want = taxonomy.precision_of(n, [c.by_id[t] for t in targets.get(n["id"], []) if t in c.by_id])
        if got != want:
            out.append(f"{n['id']}: precision {got} but its edges imply {want}")
    return out


def c10_signatures(c):
    out = []
    for n in c.nodes:
        sigs = n.get("signatures")
        if sigs is not None and (not isinstance(sigs, list) or len(sigs) < 2
                                 or not all(isinstance(s, str) and s for s in sigs)):
            out.append(f"{n['id']}: signatures {sigs!r} -- a fold records two or more signatures")
    return out


def c11_routes(c):
    out = []
    for n in c.nodes:
        for r in n.get("routes") or []:
            if r.get("method") not in VERBS:
                out.append(f"{n['id']}: route method {r.get('method')!r} is not an HTTP verb")
            if not str(r.get("path", "")).startswith("/"):
                out.append(f"{n['id']}: route path {r.get('path')!r} does not start with '/'")
        if n.get("routes") and n.get("kind") != "endpoint":
            out.append(f"{n['id']}: has routes but kind is {n.get('kind')!r}, not 'endpoint'")
    return out


def c12_http_edges(c):
    out = []
    for e in c.edges:
        if e.get("type") != "http":
            continue
        s, t = c.by_id.get(e.get("source"), {}), c.by_id.get(e.get("target"), {})
        if not s.get("http"):
            out.append(f"http edge {e.get('source')} -> {e.get('target')}: the caller makes no HTTP call")
        if not t.get("routes"):
            out.append(f"http edge {e.get('source')} -> {e.get('target')}: the target serves no route")
    return out


def c13_call_text(c):
    """Every call edge is real: the callee's name appears in the caller's range.

    This is the precision promise ("every edge shown is real"), and before this
    check nothing asserted it.
    """
    out = []
    for e in c.edges:
        if e.get("type") != "calls" or synthetic(e.get("target", "")):
            continue
        caller = c.by_id.get(e.get("source"))
        body = c.body(caller) if caller else None
        if body is not None and short(e["target"]) not in body:
            out.append(f"call edge {e['source']} -> {e['target']}: {short(e['target'])!r}"
                       f" is never named in {caller.get('source')}-{caller.get('end')}")
    return out


def c14_ext(c):
    if c.kind != "flow":
        return []
    return [f"{n['id']}: ext {n.get('ext')!r} is not a count" for n in c.nodes
            if not isinstance(n.get("ext"), int) or isinstance(n.get("ext"), bool) or n.get("ext") < 0]


def c15_report_counts(c):
    """The report was computed from this graph, so its counts must be this graph's."""
    summary = (c.report.get("analysis") or {}).get("summary") or {}
    if not summary:
        return []
    nodes, edges = c.analysis_shapes()
    actual = {
        "nodes": len(nodes), "edges": len(edges),
        "cycles": len(analyze.find_cycles(nodes, edges)),
        "orphans": len(analyze.find_orphans(nodes, edges)),
        "layer_violations": len(analyze.find_layer_violations(nodes, edges)),
        "hubs": len(analyze.find_hubs(nodes, edges)),
        "god_objects": len(analyze.find_god_objects(nodes, edges)),
    }
    return [f"report says {k} = {summary.get(k)}, the graph gives {v}"
            for k, v in actual.items() if k in summary and summary[k] != v]


def c16_security_owner(c):
    """A finding is attributed to the node whose range contains its line, or to none."""
    findings = (c.report.get("security") or {}).get("findings") or []
    out = []
    for f in findings:
        nid, fpath, fline = f.get("node"), f.get("file"), f.get("line")
        if c.kind == "flow":
            containing = []
            for n in c.nodes:
                path, line = split_source(n.get("source"))
                end = n.get("end") if isinstance(n.get("end"), int) else line
                if path == fpath and line is not None and line <= fline <= end:
                    containing.append(n["id"])
            where = f"{fpath}:{fline}"
            if nid is None:
                if containing:
                    out.append(f"{where}: finding has no owner, but {containing[0]} contains that line")
            elif nid not in c.by_id:
                out.append(f"{where}: attributed to {nid}, which is not a node")
            elif nid not in containing:
                n = c.by_id[nid]
                real = f"; {containing[0]} does" if containing else "; no node does"
                out.append(f"{where}: attributed to {nid} ({n.get('source')}-{n.get('end')}),"
                           f" which does not contain the line{real}")
        elif nid is not None:
            n = c.by_id.get(nid)
            if n is None or split_source(n.get("source"))[0] != fpath:
                out.append(f"{fpath}:{fline}: attributed to {nid}, which is not in that file")
    return out


def c17_note_names(c):
    """Every node's note file is distinct on a case-insensitive filesystem.

    Notes are written to `<id>.md` (unsafe characters as `_`). On Windows and macOS
    two ids differing only in case are ONE file, so the second note silently
    overwrites the first -- the vault has a page fewer than the graph has nodes.
    """
    seen, out = {}, []
    for n in c.nodes:
        key = re.sub(r"[^A-Za-z0-9_.-]", "_", n["id"]).lower()
        if key in seen:
            out.append(f"{n['id']} and {seen[key]}: one note file on a case-insensitive filesystem"
                       " -- one note overwrites the other")
        else:
            seen[key] = n["id"]
    return out


def c18_ambiguous(c):
    """A call dropped as ambiguous was ambiguous between real overloads.

    `ambiguous` names the overload set a call could not pick from; it must name two or
    more nodes of this graph, or the drop -- and the `overloads` marker -- is invented.
    """
    if c.kind != "flow":
        return []
    out = []
    for n in c.nodes:
        for base in n.get("ambiguous") or []:
            cls, _, name = base.rpartition(".")
            members = [m for m in c.nodes if m["id"].endswith(")") and short(m["id"]) == name
                       and (m.get("cls") or "") == cls]
            if len(members) < 2:
                out.append(f"{n['id']}: ambiguous {base!r} is not an overload set in this graph")
    return out


STRUCTURAL = [c01_dangling, c02_duplicate_ids, c03_edge_types, c04_taxonomy, c05_source,
              c06_end_range, c07_name_at_source, c08_declaration_calls, c09_precision,
              c10_signatures, c11_routes, c12_http_edges, c13_call_text, c14_ext,
              c15_report_counts, c16_security_owner, c17_note_names, c18_ambiguous]


# --- D: derived features, tested by injecting a known defect -------------------

def _app_pair(nodes: dict):
    ids = sorted(i for i, n in nodes.items() if n.get("layer") != "test")
    return ids[0], ids[1]


def d01_cycles(c):
    nodes, edges = c.analysis_shapes()
    if len(nodes) < 2:
        return []
    a, b = _app_pair(nodes)
    out = []
    found = analyze.find_cycles(nodes, edges + [(a, b, "calls"), (b, a, "calls")])
    if not any(a in comp and b in comp for comp in found):
        out.append(f"an injected 2-cycle {a} <-> {b} was not reported")
    if [a] not in analyze.find_cycles(nodes, edges + [(a, a, "calls")]):
        out.append(f"an injected self-loop on {a} was not reported")
    return out


def d02_orphans(c):
    # Probe ids are deliberately not dunder-shaped: find_orphans exempts dunders
    # (`__init__` is called implicitly), and a first draft named its probe
    # `__orphan__` -- which made "an uncalled function is reported" vacuous.
    nodes, edges = c.analysis_shapes()
    probe = dict(nodes)
    probe["probe_orphan"] = {"id": "probe_orphan", "kind": "function", "layer": "function"}
    probe["probe_declaration"] = {"id": "probe_declaration", "kind": "method", "layer": "service", "declaration": True}
    probe["probe_test"] = {"id": "probe_test", "kind": "function", "layer": "test"}
    found = set(analyze.find_orphans(probe, edges))
    out = []
    if "probe_orphan" not in found:
        out.append("an injected uncalled function was not reported as an orphan")
    if "probe_declaration" in found:
        out.append("an uncalled declaration was reported as dead code -- it has no body to delete")
    if "probe_test" in found:
        out.append("an uncalled test was reported as dead code -- a runner calls it")
    return out


def d03_hubs(c):
    nodes, edges = c.analysis_shapes()
    out = []
    for layer, expect in (("service", True), ("test", False)):
        probe, extra = dict(nodes), []
        probe["probe_hub"] = {"id": "probe_hub", "kind": "method", "layer": "service"}
        for i in range(analyze.HUB_DEGREE):
            nid = f"probe_caller{i}"
            probe[nid] = {"id": nid, "kind": "method", "layer": layer}
            extra.append((nid, "probe_hub", "calls"))
        is_hub = any(h["node"] == "probe_hub" for h in analyze.find_hubs(probe, edges + extra))
        if is_hub != expect:
            out.append(f"{analyze.HUB_DEGREE} callers from layer {layer!r}: hub reported = {is_hub},"
                       f" expected {expect}" + ("" if expect else " (test calls are coverage, not coupling)"))
    return out


def d04_god_objects(c):
    nodes, edges = c.analysis_shapes()
    probe = dict(nodes)
    for i in range(analyze.GOD_METHODS):
        probe[f"ProbeGod.m{i}"] = {"id": f"ProbeGod.m{i}", "kind": "method", "layer": "service", "cls": "ProbeGod"}
    if not any(g["name"] == "ProbeGod" for g in analyze.find_god_objects(probe, edges)):
        return [f"a class with {analyze.GOD_METHODS} methods was not reported as a god object"]
    return []


def d05_layer_violations(c):
    nodes, edges = c.analysis_shapes()
    probe = dict(nodes)
    probe["probe_repo"] = {"id": "probe_repo", "kind": "method", "layer": "repository"}
    probe["probe_ctrl"] = {"id": "probe_ctrl", "kind": "method", "layer": "controller"}
    out = []
    if not any(v["source"] == "probe_repo" for v in
               analyze.find_layer_violations(probe, edges + [("probe_repo", "probe_ctrl", "calls")])):
        out.append("a repository -> controller call was not reported as a layer violation")
    if any(v["source"] == "probe_repo" for v in
           analyze.find_layer_violations(probe, edges + [("probe_repo", "probe_ctrl", "http")])):
        out.append("an http edge was reported as a layer violation -- crossing the API is intended")
    return out


def d06_health(c):
    nodes, edges = c.analysis_shapes()
    args = [len(nodes), analyze.find_cycles(nodes, edges), analyze.find_orphans(nodes, edges),
            analyze.find_layer_violations(nodes, edges), analyze.find_hubs(nodes, edges),
            analyze.find_god_objects(nodes, edges)]
    base = analyze.health(*args)["score"]
    out = []
    with_cycle = list(args)
    with_cycle[1] = args[1] + [["probe_a", "probe_b"]]
    if len(args[1]) < 3 and analyze.health(*with_cycle)["score"] >= base:
        out.append("adding a cycle did not lower the health score")
    if analyze.health(*args, security={"high": 1})["score"] >= base:
        out.append("a high-severity security finding did not lower the health score")
    return out


def _reverse_reach(radj, target):
    seen, stack = set(), [target]
    while stack:
        for caller in radj.get(stack.pop(), []):
            if caller not in seen:
                seen.add(caller)
                stack.append(caller)
    return sorted(seen)


def d07_paths(c):
    """Blast radius and shortest paths, recomputed independently for every node."""
    _nodes, adj, radj, _src = trace_path.load_graph(c.graph_path)
    out = []
    for t in sorted(adj):
        if trace_path.impact_of(radj, t) != _reverse_reach(radj, t):
            out.append(f"blast radius of {t} disagrees with an independent reverse walk")
    for a in sorted(adj)[:200]:
        dist, frontier = {a: 0}, [a]
        while frontier:
            nxt = []
            for u in frontier:
                for v in adj.get(u, []):
                    if v not in dist:
                        dist[v] = dist[u] + 1
                        nxt.append(v)
            frontier = nxt
        for b in sorted(adj):
            p = trace_path.bfs_shortest(adj, a, b)
            if b not in dist:
                if p is not None:
                    out.append(f"path {a} -> {b} returned, but {b} is unreachable")
            elif p is None or len(p) - 1 != dist[b]:
                out.append(f"path {a} -> {b}: got {p}, but the shortest has {dist[b]} hop(s)")
            elif any(y not in adj.get(x, []) for x, y in zip(p, p[1:])):
                out.append(f"path {a} -> {b} uses a step that is not an edge: {p}")
    return out[:20]


def d08_duplicates_skip_declarations(c):
    if c.kind != "flow" or not c.roots:
        return []
    decls = {n["id"] for n in c.nodes if n.get("declaration")}
    shaped = {b["node"]["id"] for b in duplicates.node_bodies(c.roots, c.graph_path)}
    return [f"{d}: a declaration was given a token shape -- it has no body to compare" for d in decls & shaped]


def d09_context_budget(c):
    out = []
    for nid in sorted(c.by_id)[:15]:
        for budget in (80, 200, 600):
            for as_json in (False, True):
                text = context.render(c.graph_path, [nid], 1, budget, as_json)
                if len(text) > budget:
                    out.append(f"context pack for {nid} at --max-chars {budget}"
                               f"{' (json)' if as_json else ''} is {len(text)} chars")
    return out[:10]


DERIVED = [d01_cycles, d02_orphans, d03_hubs, d04_god_objects, d05_layer_violations, d06_health,
           d07_paths, d08_duplicates_skip_declarations, d09_context_budget]


# --- running ---------------------------------------------------------------------

def load_ctx(kind: str, graph_path: str | None = None, roots=None) -> Ctx:
    graph_path = graph_path or MAPS[kind]
    with open(graph_path, "r", encoding="utf-8") as fh:
        graph = json.load(fh)
    report = {}
    # The report beside *this* graph (<data>/<map>/<graph> -> <data>/report/<map>/), not
    # always the repo's: with --graph pointing into another install, c15/c16 compared a
    # real repository's graph against the sample's report.
    data_dir = os.path.dirname(os.path.dirname(os.path.abspath(graph_path)))
    rep_path = os.path.join(data_dir, "report", kind, "architecture_report.json")
    if os.path.exists(rep_path):
        with open(rep_path, "r", encoding="utf-8") as fh:
            report = json.load(fh)
    roots = roots or manifest.recorded_roots()
    files = {key: full for full, key in scan_security.iter_source_files(roots)} if roots else {}
    return Ctx(kind, graph, report, files, graph_path, roots)


def run(c: Ctx, checks) -> dict[str, list[str]]:
    return {fn.__name__: fn(c) for fn in checks}


def rebuild(c: Ctx, graph=None, report=None) -> Ctx:
    return Ctx(c.kind, graph if graph is not None else c.graph,
               report if report is not None else c.report, c.files, c.graph_path, c.roots)


# --- self-test: every check must be shown to fail --------------------------------

def _node(g, pred):
    return next(n for n in g["nodes"] if pred(n))


def _mutations():
    """(check, map, what, mutate(graph, report)) -- each must make its check fire."""
    def first_named(g):
        return _node(g, lambda n: not synthetic(n["id"]) and n.get("kind") != "module")

    def off_range(g, r):
        n = _node(g, lambda n: n.get("end") and not synthetic(n["id"]) and split_source(n["source"])[1] > 3)
        path, _ = split_source(n["source"])
        n["source"], n["end"] = f"{path}:1", 1
    return [
        ("c01_dangling", "flow", "an edge to a node that does not exist",
         lambda g, r: g["edges"].append({"source": g["nodes"][0]["id"], "target": "__nope__", "type": "calls"})),
        ("c02_duplicate_ids", "flow", "a node duplicated",
         lambda g, r: g["nodes"].append(dict(g["nodes"][0]))),
        ("c03_edge_types", "structure", "an edge type the map does not use",
         lambda g, r: g["edges"][0].__setitem__("type", "bogus")),
        ("c04_taxonomy", "flow", "a layer taxonomy.py does not define",
         lambda g, r: g["nodes"][0].__setitem__("layer", "bogus")),
        ("c05_source", "structure", "a source file that was never scanned",
         lambda g, r: g["nodes"][0].__setitem__("source", "nowhere/missing.py")),
        ("c06_end_range", "flow", "an end line past the end of the file",
         lambda g, r: g["nodes"][0].__setitem__("end", 10 ** 6)),
        ("c07_name_at_source", "flow", "a range moved to line 1 of its file", off_range),
        ("c07_name_at_source", "structure", "an entity in a file that does not declare it",
         lambda g, r: first_named(g).__setitem__("id", "NoSuchEntityAnywhere")),
        ("c08_declaration_calls", "flow", "a call edge out of a declaration",
         lambda g, r: g["edges"].append({"source": _node(g, lambda n: n.get("declaration"))["id"],
                                         "target": g["nodes"][0]["id"], "type": "calls"})),
        ("c09_precision", "flow", "a named precision loss removed from its node",
         lambda g, r: _node(g, lambda n: n.get("precision")).pop("precision")),
        ("c10_signatures", "flow", "a 'fold' of one signature",
         lambda g, r: g["nodes"][0].__setitem__("signatures", ["only(one)"])),
        ("c11_routes", "flow", "a route path without a leading slash",
         lambda g, r: _node(g, lambda n: n.get("routes"))["routes"][0].__setitem__("path", "no-slash")),
        ("c12_http_edges", "flow", "an http edge into a node that serves no route",
         lambda g, r: g["edges"].append({"source": _node(g, lambda n: n.get("http"))["id"],
                                         "target": _node(g, lambda n: not n.get("routes"))["id"],
                                         "type": "http"})),
        ("c13_call_text", "flow", "a call edge to a callee never named in the caller",
         lambda g, r: g["edges"].append({"source": "EventStore.List", "target": "InvoiceStore.Put",
                                         "type": "calls"})),
        ("c14_ext", "flow", "a negative ext",
         lambda g, r: g["nodes"][0].__setitem__("ext", -1)),
        ("c15_report_counts", "flow", "a report whose node count is one off",
         lambda g, r: r["analysis"]["summary"].__setitem__("nodes", r["analysis"]["summary"]["nodes"] + 1)),
        ("c16_security_owner", "flow", "a finding moved outside its owner's range",
         lambda g, r: r["security"]["findings"][0].__setitem__("line", 10 ** 6)),
        ("c17_note_names", "flow", "two ids that differ only in case",
         lambda g, r: g["nodes"].append(dict(g["nodes"][0], id=g["nodes"][0]["id"].swapcase()))),
        ("c18_ambiguous", "flow", "a call dropped as ambiguous between overloads that do not exist",
         lambda g, r: g["nodes"][0].__setitem__("ambiguous", ["Nowhere.nothing"])),
    ]


def _sabotage():
    """(check, map, what, attribute path, broken replacement) for the derived checks.

    A check with two assertions gets two sabotages, one aimed at each. A single
    sabotage only proves the check *as a whole* can fail, and the first draft of
    d02 showed why that is not enough: its "an orphan is reported" assertion was
    vacuous (the probe had a dunder name, which find_orphans exempts), yet the
    self-test passed, because the one sabotage tripped the *other* assertion.
    """
    return [
        ("d01_cycles", "flow", "find_cycles that never finds one", (analyze, "find_cycles"), lambda n, e: []),
        ("d02_orphans", "flow", "find_orphans that finds nothing",
         (analyze, "find_orphans"), lambda n, e: []),
        ("d02_orphans", "flow", "find_orphans that calls everything dead",
         (analyze, "find_orphans"), lambda n, e: sorted(n)),
        ("d03_hubs", "flow", "find_hubs that finds none", (analyze, "find_hubs"), lambda n, e: []),
        ("d03_hubs", "flow", "app_edges that keeps test edges", (analyze, "app_edges"), lambda n, e: e),
        ("d04_god_objects", "flow", "find_god_objects that finds none",
         (analyze, "find_god_objects"), lambda n, e: []),
        ("d05_layer_violations", "flow", "find_layer_violations that finds none",
         (analyze, "find_layer_violations"), lambda n, e: []),
        ("d05_layer_violations", "flow", "find_layer_violations that flags http edges too",
         (analyze, "find_layer_violations"),
         lambda n, e: [{"source": s, "target": t} for s, t, _ in e]),
        ("d06_health", "flow", "a health score that ignores its inputs",
         (analyze, "health"), lambda *a, **k: {"score": 100, "grade": "A"}),
        ("d07_paths", "flow", "an impact_of that returns nothing", (trace_path, "impact_of"), lambda r, t: []),
        ("d08_duplicates_skip_declarations", "flow", "node_bodies that shapes declarations too",
         (duplicates, "node_bodies"),
         lambda roots, gp: [{"node": n, "tokens": ["ID"], "loc": 1}
                            for n in json.load(open(gp, encoding="utf-8"))["nodes"]]),
        ("d09_context_budget", "flow", "a render that ignores the budget",
         (context, "render"), lambda *a, **k: "x" * 10_000),
    ]


def self_test() -> int:
    ctxs = {k: load_ctx(k) for k in MAPS}
    base = {k: run(c, STRUCTURAL + DERIVED) for k, c in ctxs.items()}
    failures = 0
    print("C checks -- break the input, the check must fire:")
    for check, kind, what, mutate in _mutations():
        c = ctxs[kind]
        g, r = copy.deepcopy(c.graph), copy.deepcopy(c.report)
        mutate(g, r)
        fn = next(f for f in STRUCTURAL if f.__name__ == check)
        new = [x for x in fn(rebuild(c, g, r)) if x not in base[kind][check]]
        failures += not new
        print(f"  {'PASS' if new else 'FAIL'}  {check:<22} {kind:<9} {what}")
    print("D checks -- break the analysis, the check must fire:")
    for check, kind, what, (mod, attr), broken in _sabotage():
        original = getattr(mod, attr)
        setattr(mod, attr, broken)
        try:
            fn = next(f for f in DERIVED if f.__name__ == check)
            new = [x for x in fn(ctxs[kind]) if x not in base[kind][check]]
        finally:
            setattr(mod, attr, original)
        failures += not new
        print(f"  {'PASS' if new else 'FAIL'}  {check:<34} {what}")
    total = len(_mutations()) + len(_sabotage())
    print(f"{total - failures}/{total} checks shown to fail on a broken input")
    return 1 if failures else 0


def main(argv=None) -> int:
    console.safe_stdout()
    ap = argparse.ArgumentParser(description="Assert the invariants a correct graph must satisfy.")
    ap.add_argument("--map", choices=["flow", "structure", "both"], default="both")
    ap.add_argument("--graph", help="Path to a graph (with --map flow or structure)")
    ap.add_argument("--src", nargs="+", help="Source roots (default: the ones the last build recorded)")
    ap.add_argument("--self-test", action="store_true", help="Prove every check can fail")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()

    kinds = list(MAPS) if args.map == "both" else [args.map]
    total = 0
    for kind in kinds:
        c = load_ctx(kind, args.graph if args.map != "both" else None, args.src)
        results = run(c, STRUCTURAL + DERIVED)
        bad = {k: v for k, v in results.items() if v}
        n = sum(len(v) for v in bad.values())
        total += n
        print(f"{kind}: {len(c.nodes)} node(s), {len(c.edges)} edge(s), "
              f"{len(STRUCTURAL) + len(DERIVED)} checks -- {'OK' if not n else f'{n} finding(s)'}")
        for check, items in bad.items():
            for item in items:
                print(f"  {check}: {item}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
