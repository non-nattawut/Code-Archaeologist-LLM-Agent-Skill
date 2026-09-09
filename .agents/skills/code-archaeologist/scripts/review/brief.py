#!/usr/bin/env python3
"""brief.py — the whole codebase in about thirty lines.

Orientation for an agent starting a session: what the maps contain, how healthy
they are, whether they are stale, the entry points, and the handful of nodes
worth knowing about (biggest, most complex, most churned, riskiest).

It reads the artifacts the other scripts already wrote — it computes nothing —
so its cost is fixed no matter how large the repo is. That is the point: reading
`architecture_report.json` costs tens of thousands of tokens on a real codebase;
reading this costs a few hundred.

    python brief.py                          # both maps, detail from the flow map
    python brief.py --map structure --top 3
    python brief.py --json                   # same digest as JSON

Run `archaeologist.py report` first for grades, risks and hotspots; without a
report this still summarizes whatever maps exist.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
REPORT_DIR = os.path.join(DATA_DIR, "report")
GRAPHS = {
    "structure": os.path.join(DATA_DIR, "structure", "graph.json"),
    "flow": os.path.join(DATA_DIR, "flow", "flow_graph.json"),
}

import console     # noqa: E402  (stdout must survive a non-UTF-8 console)
import manifest    # noqa: E402

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _map_summary(name: str) -> dict:
    """Counts + grade for one map, from its graph and (if built) its report."""
    graph = _load(GRAPHS[name])
    if not (graph or {}).get("nodes"):
        return {}          # missing, or the empty skeleton the installer seeds
    rep = _load(os.path.join(REPORT_DIR, name, "architecture_report.json")) or {}
    health = (rep.get("analysis") or {}).get("health") or {}
    return {
        "nodes": len(graph.get("nodes", [])),
        "edges": len(graph.get("edges", [])),
        "approx": sum(1 for n in graph.get("nodes", []) if n.get("approx")),
        "grade": health.get("grade"),
        "score": health.get("score"),
        "reported": rep.get("generated"),
        "report": rep,
    }


def _freshness(src) -> dict:
    """manifest.compare, but tolerant: anything it cannot answer means 'unknown'.

    With no roots, `compare` uses the ones the last build recorded — which is why
    `brief` with no --src reports freshness instead of guessing at `./src`.
    """
    try:
        return manifest.compare(src)
    except Exception:                       # a missing manifest must not break the digest
        return {}


def collect(src=None, focus: str = "flow", top: int = 5) -> dict:
    maps = {name: s for name in GRAPHS if (s := _map_summary(name))}
    if focus not in maps and maps:
        focus = next(iter(maps))

    rep = maps.get(focus, {}).get("report") or {}
    smells = rep.get("analysis") or {}
    size = rep.get("metrics") or {}
    security = rep.get("security") or {}
    insights = rep.get("insights") or {}
    census = rep.get("census") or {}

    findings = sorted(security.get("findings", []),
                      key=lambda f: (SEV_ORDER.get(f.get("severity"), 9), f.get("file", ""), f.get("line", 0)))

    roots = src or size.get("roots")
    digest = {
        "maps": {k: {x: v[x] for x in ("nodes", "edges", "approx", "grade", "score", "reported")} for k, v in maps.items()},
        "focus": focus,
        "freshness": _freshness(roots),
        "size": size.get("totals") or {},
        "languages": size.get("languages") or {},
        "routes": census.get("routes", [])[:top],
        "summary": smells.get("summary") or {},
        "longest": size.get("top_loc", [])[:top],
        "complex": size.get("top_complexity", [])[:top],
        "hotspots": insights.get("hotspots", [])[:top],
        "risks": findings[:top],
        "orphans": (smells.get("orphans") or [])[:top],
        "debt": (rep.get("debt") or {}).get("summary") or {},
        "tests": (rep.get("tests") or {}).get("summary") or {},
    }
    return digest


def to_text(d: dict) -> str:
    out = ["Code Archaeologist brief"]
    out.append("")
    out.append("MAPS")
    for name, m in d["maps"].items():
        grade = f"grade {m['grade']} ({m['score']}/100)" if m.get("grade") else "no report yet"
        approx = f"  ({m['approx']} approximate)" if m.get("approx") else ""
        out.append(f"  {name:<10} {m['nodes']:>4} node(s) {m['edges']:>4} edge(s)  {grade}{approx}")
    fresh = d["freshness"]
    if fresh:
        state = "STALE" if fresh.get("stale") else "up to date"
        counts = [len(fresh.get(k, [])) for k in ("changed", "added", "deleted")]
        # Zero counts under a STALE verdict mean the reason is not per-file (no manifest,
        # roots not found). Printing "0 changed, 0 added, 0 deleted" there would contradict
        # the verdict, so say why instead.
        detail = (f"{counts[0]} changed, {counts[1]} added, {counts[2]} deleted"
                  if any(counts) else fresh.get("reason", ""))
        out.append(f"  freshness  {state}" + (f" ({detail})" if detail and fresh.get("stale") else ""))
    if not any(m.get("grade") for m in d["maps"].values()):
        out.append("  (run `archaeologist.py report --src <roots>` for grades, risks and hotspots)")
    if any(m.get("approx") for m in d["maps"].values()):
        out.append("  approximate = Java/Go/C#, read textually rather than parsed. Unresolvable")
        out.append("               calls were dropped, so their coupling is a lower bound. Say so")
        out.append("               when you answer a question about those files.")

    t = d["size"]
    if t:
        langs = ", ".join(f"{k} {v['lines']}" for k, v in d["languages"].items())
        out += ["", "SIZE",
                f"  {t['files']} file(s), {t['lines']:,} lines "
                f"({t['code']:,} code, {t['comment']:,} comment, {t['blank']:,} blank)"
                + (f" - {langs}" if langs else "")]

    s = d["summary"]
    out += ["", f"{d['focus'].upper()} MAP"]
    if s:
        out.append(f"  smells     cycles {s.get('cycles', 0)}, orphans {s.get('orphans', 0)}, "
                   f"layer violations {s.get('layer_violations', 0)}, hubs {s.get('hubs', 0)}, "
                   f"god objects {s.get('god_objects', 0)}")

    def block(label: str, rows: list[str]) -> None:
        for i, row in enumerate(rows):
            out.append(f"  {label if i == 0 else '':<10} {row}")

    block("entries", [f"{r['method']} {r['path']} -> {r['node']}" for r in d["routes"]])
    block("longest", [f"{x['id']} {x['loc']} line(s), cx {x['complexity']}" for x in d["longest"]])
    block("complex", [f"{x['id']} cx {x['complexity']} ({x['file']}:{x['line']})" for x in d["complex"]])
    block("hotspots", [f"{x['node']} risk {x['risk']} ({x['commits']} commit(s)"
                       + (f", {x['owner']})" if x.get("owner") else ")") for x in d["hotspots"]])
    block("risks", [f"{f['severity']:<6} {f['rule']} {f['file']}:{f['line']}"
                    + (f" -> {f['node']}" if f.get("node") else "") for f in d["risks"]])
    block("orphans", d["orphans"])
    if d["debt"]:
        tags = ", ".join(f"{k} {v}" for k, v in d["debt"]["by_tag"].items()) or "none"
        block("debt", [f"{d['debt']['markers']} marker(s) ({tags}), "
                       f"{d['debt']['dead_nodes']} dead node(s), {d['debt']['dead_files']} dead file(s)"])
    if d["tests"]:
        t = d["tests"]
        block("tests", [f"{t['referenced']}/{t['considered']} node(s) named by a test "
                        f"({t['referenced_pct']}%), {t['test_files']} test file(s)"])

    out += ["", "NEXT",
            "  trace_path.py --graph <graph.json> --from <A> --to <B>     how does it get there",
            "  trace_path.py --graph <graph.json> --impact-of <node>      what breaks if it changes",
            "  read data/<map>/notes/<node>.md                            what one node does"]
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="A fixed-size digest of the built maps.")
    parser.add_argument("--src", nargs="+", default=None, help="Source roots, for the freshness check")
    parser.add_argument("--map", dest="focus", default="flow", choices=sorted(GRAPHS),
                        help="Which map the detail sections describe (default: flow)")
    parser.add_argument("--top", type=int, default=5, help="Rows per detail section")
    parser.add_argument("--json", action="store_true", help="Emit the digest as JSON")
    args = parser.parse_args(argv)
    console.safe_stdout()

    digest = collect(args.src, args.focus, args.top)
    if not digest["maps"]:
        print("error: no map built yet - run `archaeologist.py both --src <roots>` first", file=sys.stderr)
        return 1
    print(json.dumps(digest, indent=2) if args.json else to_text(digest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
