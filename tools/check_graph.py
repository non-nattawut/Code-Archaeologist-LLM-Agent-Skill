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
EDGE_TYPES = {"flow": {"calls", "http", "renders", "passes", "implements", "overrides"},
              "structure": {"references", "implements", "extends"}}
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
            if (short(n["id"]) == os.path.splitext(os.path.basename(path))[0]
                    and body.lstrip().startswith("export default")):
                continue                                 # `export default function () {}` is named by its file
            where = f"{path}:{line}-{n.get('end')}"
        elif c.kind == "flow":
            continue                                     # C05 reports a flow node with no line
        else:
            body, want, where = "\n".join(lines), [short(n["id"])], path
        if want and not any(w in body for w in want):
            out.append(f"{n['id']}: {want[0]!r} does not occur in {where} -- the range points elsewhere")
    return out


def c08_declaration_calls(c):
    """A declaration has no body, so it calls nothing -- except the Java a MapStruct
    `@Mapping(expression = "java(...)")` on it spells, which the generated mapper runs."""
    out = []
    for e in c.edges:
        caller = c.by_id.get(e.get("source"), {})
        if e.get("type") != "calls" or not caller.get("declaration"):
            continue
        if re.search(rf'java\([^"]*\b{re.escape(short(e["target"]))}\b', c.body(caller) or ""):
            continue
        out.append(f"{e['source']}: a declaration (signature, no body) has a call edge to {e['target']}")
    return out


def c09_precision(c):
    if c.kind != "flow":
        return [f"{n['id']}: a structure node carries `precision`" for n in c.nodes if n.get("precision")]
    out, targets = [], {}
    for e in c.edges:
        if e.get("type") in ("calls", "http"):      # what build_flow counts as a node's calls
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
        callee = c.by_id.get(e["target"]) or {}
        if short(e["target"]) == "constructor" and callee.get("cls"):
            # `new ApiError(...)` runs `ApiError.constructor`: the source spells the class.
            if body is not None and not re.search(rf"\bnew\s+{re.escape(callee['cls'])}\b", body):
                out.append(f"call edge {e['source']} -> {e['target']}: `new {callee['cls']}` is never"
                           f" written in {caller.get('source')}-{caller.get('end')}")
            continue
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
        "overridden": len(analyze.find_overridden(nodes, edges)),
        "layer_violations": len(analyze.find_layer_violations(nodes, edges)),
        "hubs": len(analyze.find_hubs(nodes, edges)),
        "shared_helpers": len(analyze.find_shared_helpers(nodes, edges)),
        "coordinators": len(analyze.find_coordinators(nodes, edges)),
        "wrong_way_deps": len(analyze.find_wrong_way_deps(nodes, edges)),
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


def c19_unresolved(c):
    """`unresolved` names calls this graph could have resolved, and stays within `ext`.

    It is the honest half of a dropped call: a name the graph defines somewhere, that
    a call site named and the resolver could not place. So every entry must be a real
    node's bare name -- otherwise it is inventing a target -- and there cannot be more
    of them than there were dropped call sites in the first place.
    """
    if c.kind != "flow":
        return []
    known = {short(n["id"]) for n in c.nodes}
    out = []
    for n in c.nodes:
        names = n.get("unresolved") or []
        unknown = [x for x in names if x not in known]
        if unknown:
            out.append(f"{n['id']}: unresolved names nothing this graph defines: {unknown}")
        if len(names) > n.get("ext", 0):
            out.append(f"{n['id']}: {len(names)} unresolved name(s) but only {n.get('ext', 0)}"
                       " dropped call site(s)")
        if sorted(set(names)) != list(names):
            out.append(f"{n['id']}: unresolved is not sorted and unique: {names}")
        extra = [x for x in (n.get("untyped") or []) if x not in names]
        if extra:
            out.append(f"{n['id']}: untyped names {extra} are not among its unresolved names")
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


def c20_render_text(c):
    """Every render edge is real: the caller's range holds `<Name` for what it renders."""
    out = []
    for e in c.edges:
        if e.get("type") != "renders":
            continue
        caller = c.by_id.get(e.get("source"))
        body = c.body(caller) if caller else None
        if body is not None and f"<{short(e['target'])}" not in body:
            out.append(f"renders edge {e['source']} -> {e['target']}: `<{short(e['target'])}` is never"
                       f" written in {caller.get('source')}-{caller.get('end')}")
    return out


def c23_passes_text(c):
    """Every passes link is real: the caller's range names the function it hands over."""
    out = []
    for e in c.edges:
        if e.get("type") != "passes":
            continue
        caller = c.by_id.get(e.get("source"))
        body = c.body(caller) if caller else None
        name = short(e["target"])
        if body is not None and not re.search(rf"(?<![\w$.]){re.escape(name)}(?![\w$])", body):
            out.append(f"passes edge {e['source']} -> {e['target']}: {name!r} is never named in"
                       f" {caller.get('source')}-{caller.get('end')}")
    return out


def c21_implements(c):
    """Every implements link joins one method name on two classes, and the target's class is
    named in the source class's file -- or, within three hops, in the file of a class named
    there (an abstract class in between). Word-level: it can pass a wrong link between classes
    that happen to mention each other; it cannot pass one between classes that never do.
    In the structure map a link is a stated base, so its name must be written in the class."""
    if c.kind != "flow":
        out = []
        for e in c.edges:
            if e.get("type") not in taxonomy.INHERITANCE_LINKS:
                continue
            s, t = c.by_id.get(e.get("source")), c.by_id.get(e.get("target"))
            body = c.body(s) if s is not None else None
            base = e["target"].split(".")[-1]
            if body is not None and not re.search(rf"\b{re.escape(base)}\b", body):
                out.append(f"{e['type']} link {e['source']} -> {e['target']}: {base} is never named in"
                           f" {s.get('source')}-{s.get('end')}")
            if s is not None and t is not None:
                # A class filling in an interface implements it; anything else extends.
                want = ("implements" if t.get("kind") == "interface" and s.get("kind") != "interface"
                        else "extends")
                if e["type"] != want:
                    out.append(f"{e['type']} link {s['id']} ({s.get('kind')}) -> {t['id']} ({t.get('kind')}):"
                               f" should be {want}")
        return out
    files_of: dict[str, set[str]] = {}
    for n in c.nodes:
        if n.get("cls"):
            files_of.setdefault(n["cls"], set()).add(split_source(n.get("source"))[0])
    mentions: dict[str, set[str] | None] = {}

    def named_in(cls):
        if cls not in mentions:
            texts = [c.lines(f) for f in sorted(files_of.get(cls, ()))]
            if not texts or any(t is None for t in texts):
                mentions[cls] = None
            else:
                words = set(re.findall(r"\w+", "\n".join("\n".join(t) for t in texts)))
                mentions[cls] = (words & set(files_of)) - {cls}
        return mentions[cls]

    out = []
    for e in c.edges:
        if e.get("type") not in taxonomy.INHERITANCE_LINKS:
            continue
        s, t = c.by_id.get(e.get("source")), c.by_id.get(e.get("target"))
        if s is None or t is None:
            continue                                  # c01 reports it
        # Filling in a declaration implements it; replacing a body overrides it. A Python
        # `@abstractmethod` has a body, so a py implements link may point at one.
        if e["type"] == "overrides" and t.get("declaration"):
            out.append(f"overrides link {s['id']} -> {t['id']}: the target is a declaration -- implements")
        elif e["type"] == "implements" and not t.get("declaration") and t.get("lang") != "py":
            out.append(f"implements link {s['id']} -> {t['id']}: the target has a body -- overrides")
        elif e["type"] == "extends":
            out.append(f"extends link {s['id']} -> {t['id']}: a flow map joins methods, never classes")
        if short(s["id"]) != short(t["id"]) or not s.get("cls") or s.get("cls") == t.get("cls"):
            out.append(f"implements link {s['id']} -> {t['id']}: not one method name on two classes")
            continue
        seen, frontier, unreadable = {s["cls"]}, [s["cls"]], False
        for _ in range(3):
            nxt = []
            for cls in frontier:
                names = named_in(cls)
                if names is None:
                    unreadable = True
                    continue
                nxt += sorted(x for x in names if x not in seen)
                seen.update(names)
            frontier = nxt
        if t["cls"] not in seen and not unreadable:
            out.append(f"implements link {s['id']} -> {t['id']}: {t['cls']} is never named by"
                       f" {s['cls']} or by a class it names")
    return out


def c22_overridden(c):
    """`overridden` means every subclass replaces the body, so at least one `overrides` link
    must point at the node, and a declaration has no body to replace."""
    overridden_into = {e["target"] for e in c.edges if e.get("type") == "overrides"}
    return [f"{n['id']}: marked overridden, but " + ("it is a declaration" if n.get("declaration")
                                                      else "no overrides link points at it")
            for n in c.nodes if n.get("overridden")
            and (n.get("declaration") or n["id"] not in overridden_into)]

SITE_WINDOW = 5
ARM_RE = re.compile(r"(\d+):(\d+)/(\d+)")     # a call written across lines (`api\n  .get()`) names its callee a few lines on


def c24_call_sites(c):
    """Every call site is where the link says: its `line` lies in the caller's range and the
    callee is named there or just after, `loop` / `cond` appear only as `true`, and no link
    that is not a call carries a site. `arms` is a list of `"<line>:<col>/<arm>"`, only on a
    `cond` link -- one side of an either/or never has to run -- each branch starting inside the
    caller and no later than the call, outermost first, none named twice."""
    out = []
    for e in c.edges:
        keys = {k for k in ("line", "loop", "cond", "arms") if k in e}
        if not keys:
            continue
        where = f"{e.get('type')} edge {e.get('source')} -> {e.get('target')}"
        if e.get("type") != "calls":
            out.append(f"{where}: carries a call site ({sorted(keys)}) but is not a call")
            continue
        for flag in ("loop", "cond"):
            if flag in e and e[flag] is not True:
                out.append(f"{where}: {flag} is {e[flag]!r}; a false flag is left out, never written")
        if "line" not in e:
            out.append(f"{where}: {sorted(keys)} without a line")
            continue
        caller = c.by_id.get(e.get("source")) or {}
        path, start = split_source(caller.get("source"))
        end, line, lines = caller.get("end"), e["line"], c.lines(path)
        if not isinstance(line, int):
            out.append(f"{where}: line {line!r} is not a line number")
            continue
        if start is None or not isinstance(end, int):
            continue                     # C05 / C06 report a caller with no range
        if not start <= line <= end:
            out.append(f"{where}: line {line} is outside its caller {caller.get('source')}-{end}")
            continue
        if "arms" in e:
            arms = e["arms"]
            parsed = [ARM_RE.fullmatch(a) if isinstance(a, str) else None for a in arms] \
                if isinstance(arms, list) and arms else [None]
            if not all(parsed):
                out.append(f"{where}: arms {arms!r} is not a list of \"<line>:<col>/<arm>\"")
            elif e.get("cond") is not True:
                out.append(f"{where}: arms {arms} on a link that is not cond")
            else:
                starts = [(int(m.group(1)), int(m.group(2))) for m in parsed]
                if any(not start <= ln <= line for ln, _ in starts):
                    out.append(f"{where}: a branch in {arms} does not start between {start} and {line}")
                elif starts != sorted(starts) or len({s for s in starts}) != len(starts):
                    out.append(f"{where}: arms {arms} are not outermost first, each branch once")
        if lines is None or synthetic(e.get("target", "")):
            continue
        name = short(e["target"])
        near = "\n".join(lines[line - 1:min(end, line + SITE_WINDOW)])
        if name == "constructor":
            continue                     # `new X()` spells the class; c13 checks that
        if name not in near:
            out.append(f"{where}: {name!r} is not written at {path}:{line}")
    return out


STRUCTURAL = [c01_dangling, c02_duplicate_ids, c03_edge_types, c04_taxonomy, c05_source,
              c06_end_range, c07_name_at_source, c08_declaration_calls, c09_precision,
              c10_signatures, c11_routes, c12_http_edges, c13_call_text, c14_ext,
              c15_report_counts, c16_security_owner, c17_note_names, c18_ambiguous,
              c19_unresolved, c20_render_text, c21_implements, c22_overridden, c23_passes_text,
              c24_call_sites]


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
    probe["probe_impl"] = {"id": "probe_impl", "kind": "method", "layer": "service"}
    found = set(analyze.find_orphans(probe, edges + [("probe_impl", "probe_declaration", "implements")]))
    out = []
    if "probe_impl" in found:
        out.append("an implementation was reported as dead code -- its implements link reaches it")
    if "probe_orphan" not in found:
        out.append("an injected uncalled function was not reported as an orphan")
    if "probe_declaration" in found:
        out.append("an uncalled declaration was reported as dead code -- it has no body to delete")
    if "probe_test" in found:
        out.append("an uncalled test was reported as dead code -- a runner calls it")
    return out


def _coupling_probe(nodes, fan_in, fan_out, caller_layer="service"):
    """A node with `fan_in` callers and `fan_out` callees grafted onto the real graph."""
    probe, extra = dict(nodes), []
    probe["probe_hub"] = {"id": "probe_hub", "kind": "method", "layer": "service"}
    for i in range(fan_in):
        nid = f"probe_caller{i}"
        probe[nid] = {"id": nid, "kind": "method", "layer": caller_layer}
        extra.append((nid, "probe_hub", "calls"))
    for i in range(fan_out):
        nid = f"probe_callee{i}"
        probe[nid] = {"id": nid, "kind": "method", "layer": "service"}
        extra.append(("probe_hub", nid, "calls"))
    return probe, extra


def d03_hubs(c):
    """Coupling is a direction, not a count: only a node high in *both* directions is a
    graded hub. A shared helper (many callers, no callees) and a coordinator (many callees,
    no callers) are normal shapes, reported in their own lists and never deducted for."""
    nodes, edges = c.analysis_shapes()
    out = []
    cases = [
        # fan_in, fan_out, finder,              should report, why
        (analyze.HUB_FAN_IN, analyze.HUB_FAN_OUT, analyze.find_hubs, True,
         "coupled in both directions"),
        (analyze.HELPER_FAN_IN, 0, analyze.find_hubs, False,
         "a shared helper is not a hub -- nothing depends on what it depends on"),
        (analyze.HELPER_FAN_IN, 0, analyze.find_shared_helpers, True, "a shared helper"),
        (0, analyze.COORD_FAN_OUT, analyze.find_hubs, False,
         "a coordinator is not a hub -- nothing depends on it"),
        (0, analyze.COORD_FAN_OUT, analyze.find_coordinators, True, "a coordinator"),
    ]
    for fan_in, fan_out, finder, expect, why in cases:
        probe, extra = _coupling_probe(nodes, fan_in, fan_out)
        got = any(x["node"] == "probe_hub" for x in finder(probe, edges + extra))
        if got != expect:
            out.append(f"in {fan_in} / out {fan_out}: {finder.__name__} reported = {got},"
                       f" expected {expect} ({why})")
    # A test calling production code is coverage, not coupling.
    probe, extra = _coupling_probe(nodes, analyze.HUB_FAN_IN, analyze.HUB_FAN_OUT, "test")
    if any(h["node"] == "probe_hub" for h in analyze.find_hubs(probe, edges + extra)):
        out.append("callers from layer 'test' made a hub -- test calls are coverage, not coupling")
    return out


def d10_wrong_way(c):
    """A stable node calling an unstable one is a dependency pointing the wrong way; the
    same call in the other direction is how a dependency is supposed to point."""
    nodes, edges = c.analysis_shapes()
    probe, extra = dict(nodes), []
    # probe_stable: many callers, one callee -> low instability.
    # probe_unstable: no callers, many callees -> instability 1.0.
    probe["probe_stable"] = {"id": "probe_stable", "kind": "method", "layer": "service"}
    probe["probe_unstable"] = {"id": "probe_unstable", "kind": "method", "layer": "service"}
    for i in range(analyze.WRONG_WAY_FAN_IN):
        nid = f"probe_user{i}"
        probe[nid] = {"id": nid, "kind": "method", "layer": "service"}
        extra.append((nid, "probe_stable", "calls"))
    for i in range(5):
        nid = f"probe_leaf{i}"
        probe[nid] = {"id": nid, "kind": "method", "layer": "service"}
        extra.append(("probe_unstable", nid, "calls"))

    out = []
    bad = analyze.find_wrong_way_deps(probe, edges + extra + [("probe_stable", "probe_unstable", "calls")])
    if not any(v["source"] == "probe_stable" for v in bad):
        out.append("a stable node calling an unstable one was not reported as wrong-way")
    good = analyze.find_wrong_way_deps(probe, edges + extra + [("probe_unstable", "probe_stable", "calls")])
    if any(v["target"] == "probe_stable" and v["source"] == "probe_unstable" for v in good):
        out.append("an unstable node calling a stable one was reported -- that is the right direction")
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
           d07_paths, d08_duplicates_skip_declarations, d09_context_budget, d10_wrong_way]


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
        ("c19_unresolved", "flow", "an unresolved name no node in the graph has",
         lambda g, r: g["nodes"][0].__setitem__("unresolved", ["nothing_is_called_this"])),
        ("c19_unresolved", "flow", "more unresolved names than dropped call sites",
         lambda g, r: (g["nodes"][0].__setitem__("unresolved", [short(g["nodes"][1]["id"])]),
                       g["nodes"][0].__setitem__("ext", 0))),
        ("c20_render_text", "flow", "a renders edge from code that renders no such tag",
         lambda g, r: g["edges"].append({"source": "EventStore.List", "target": "OrderCard",
                                         "type": "renders"})),
        ("c24_call_sites", "flow", "a call site moved outside its caller",
         lambda g, r: next(e for e in g["edges"] if e.get("line")).__setitem__("line", 10 ** 6)),
        ("c24_call_sites", "flow", "a call site moved to a line in its caller that does not name the callee",
         lambda g, r: next(e for e in g["edges"] if e["source"] == "OrderWorkflow.place"
                           and e["target"] == "PricingRule.price").__setitem__("line", 22)),
        ("c24_call_sites", "flow", "a false loop flag written instead of left out",
         lambda g, r: next(e for e in g["edges"] if e.get("line")).__setitem__("loop", False)),
        ("c24_call_sites", "flow", "arms on a link that is not cond",
         lambda g, r: next(e for e in g["edges"] if e.get("arms")).pop("cond")),
        ("c24_call_sites", "flow", "an arm that names no branch position",
         lambda g, r: next(e for e in g["edges"] if e.get("arms")).__setitem__("arms", ["19/0"])),
        ("c24_call_sites", "flow", "an arm whose branch starts before its caller",
         lambda g, r: next(e for e in g["edges"] if e.get("arms")).__setitem__("arms", ["1:1/0"])),
        ("c24_call_sites", "flow", "a call site on a link that is not a call",
         lambda g, r: next(e for e in g["edges"] if e["type"] == "http").__setitem__("line", 1)),
        ("c23_passes_text", "flow", "a passes edge from code that never names the function",
         lambda g, r: g["edges"].append({"source": "EventStore.List", "target": "OrderCard",
                                         "type": "passes"})),
        ("c21_implements", "flow", "an implements link between two different method names",
         lambda g, r: g["edges"].append({"source": "OrderWorkflow.place", "target": "PricingRule.price",
                                         "type": "implements"})),
        ("c19_unresolved", "flow", "an untyped name that is not unresolved",
         lambda g, r: g["nodes"][0].__setitem__("untyped", ["nothing_is_called_this"])),
        ("c21_implements", "flow", "an overrides link into a declaration",
         lambda g, r: next(e for e in g["edges"] if e["type"] == "implements").__setitem__("type", "overrides")),
        ("c21_implements", "structure", "a class extending the interface it implements",
         lambda g, r: next(e for e in g["edges"] if e["type"] == "implements").__setitem__("type", "extends")),
        ("c22_overridden", "flow", "overridden on a method nothing overrides",
         lambda g, r: _node(g, lambda n: not n.get("declaration")).__setitem__("overridden", True)),
        ("c21_implements", "structure", "an implements link to a class the source never names",
         lambda g, r: g["edges"].append({"source": "InvoiceStore", "target": "OrderCard", "type": "implements"})),
        ("c21_implements", "flow", "an implements link to a class nothing names",
         lambda g, r: (g["nodes"].append(dict(_node(g, lambda n: n["id"] == "PricingRule.price"),
                                              id="Nowhere.price", cls="Nowhere")),
                       g["edges"].append({"source": "FlatRate.price", "target": "Nowhere.price",
                                          "type": "implements"}))),
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
        ("d02_orphans", "flow", "find_orphans that ignores implements links",
         (analyze, "find_orphans"),
         lambda n, e, real=analyze.find_orphans: real(n, [x for x in e if x[2] != "implements"])),
        ("d03_hubs", "flow", "find_hubs that finds none", (analyze, "find_hubs"), lambda n, e: []),
        # The old rule: any node of total degree 10+. It must now fail d03, because it
        # calls a shared helper and a coordinator hubs -- which is the whole point of r83.
        ("d03_hubs", "flow", "find_hubs back on total degree alone", (analyze, "find_hubs"),
         lambda n, e: [{"node": nid, **d} for nid, d in analyze.coupling(n, e).items() if d["degree"] >= 10]),
        ("d03_hubs", "flow", "find_shared_helpers that finds none",
         (analyze, "find_shared_helpers"), lambda n, e: []),
        ("d03_hubs", "flow", "find_coordinators that finds none",
         (analyze, "find_coordinators"), lambda n, e: []),
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
        ("d10_wrong_way", "flow", "find_wrong_way_deps that finds none",
         (analyze, "find_wrong_way_deps"), lambda n, e: []),
        ("d10_wrong_way", "flow", "find_wrong_way_deps that ignores the direction",
         (analyze, "find_wrong_way_deps"),
         lambda n, e: [{"source": s, "target": t, "source_instability": 0.0,
                        "target_instability": 1.0, "source_fan_in": 9} for s, t, _ in e]),
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
