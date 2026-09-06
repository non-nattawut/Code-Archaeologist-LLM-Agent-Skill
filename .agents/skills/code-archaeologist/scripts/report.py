#!/usr/bin/env python3
"""report.py — one architecture review report from everything the maps know.

Joins the four deterministic sources into a single artifact a human (or an agent)
can read top to bottom:

  graph      node/edge/layer/language census + route entry points
  metrics    line counts per file, LOC/complexity per node
  analyze    cycles, orphans, layer violations, hubs, god objects, patterns, grade
  security   scan_security.py findings, attributed to the owning node
  git        churn, ownership and hotspot ranking (risk = churn x connectivity)

Writes both a Markdown report (for humans / PRs) and the same data as JSON (for
tools), plus the raw `security.json` and `insights.json` it collected:

    python report.py --src ./backend ./frontend
    python report.py --src ./src --graph <graph.json> --out-dir <dir>

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT_DIR = os.path.join(DATA_DIR, "report")

sys.path.insert(0, SCRIPT_DIR)
import analyze          # noqa: E402
import git_insights     # noqa: E402
import metrics          # noqa: E402
import scan_security    # noqa: E402

TOP_FINDINGS = 20
TOP_HOTSPOTS = 10
TOP_ORPHANS = 15
TOP_BIG = 10


def file_census(size: dict) -> dict:
    """Per-file line counts and the language mix — the "140,108 lines of code" panel.

    Derived from the metrics pass so the two never disagree about what a line is.
    """
    files = {k: {"lines": v["lines"], "lang": v["lang"]} for k, v in size["files"].items()}
    by_lang = {k: v["lines"] for k, v in size["languages"].items()}
    loc = size["totals"]["lines"]
    return {
        "files": dict(sorted(files.items())),
        "file_count": len(files),
        "loc": loc,
        "languages": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
        "language_pct": {k: round(100 * v / loc, 1) if loc else 0.0 for k, v in
                         sorted(by_lang.items(), key=lambda kv: -kv[1])},
    }


def census(graph: dict) -> dict:
    nodes = graph.get("nodes", [])
    layers, langs, kinds = {}, {}, {}
    routes = []
    for n in nodes:
        layers[n.get("layer", "unknown")] = layers.get(n.get("layer", "unknown"), 0) + 1
        langs[n.get("lang", "py")] = langs.get(n.get("lang", "py"), 0) + 1
        kinds[n.get("kind", "unknown")] = kinds.get(n.get("kind", "unknown"), 0) + 1
        route = n.get("route")
        if route:
            routes.append({"method": route.get("method", ""), "path": route.get("path", ""),
                           "node": n["id"]})
    edge_types: dict[str, int] = {}
    for e in graph.get("edges", []):
        edge_types[e.get("type", "")] = edge_types.get(e.get("type", ""), 0) + 1
    return {
        "nodes": len(nodes), "edges": len(graph.get("edges", [])),
        "layers": dict(sorted(layers.items())), "langs": dict(sorted(langs.items())),
        "kinds": dict(sorted(kinds.items())), "edge_types": dict(sorted(edge_types.items())),
        "routes": sorted(routes, key=lambda r: (r["path"], r["method"])),
    }


def _cell(value) -> str:
    """Keep source snippets from breaking the Markdown table."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out + [""]


def _counts(mapping: dict) -> str:
    return ", ".join(f"`{k}` {v}" for k, v in mapping.items()) or "_none_"


def to_markdown(data: dict) -> str:
    stats, smells, security, insights = (data["census"], data["analysis"],
                                         data["security"], data["insights"])
    files = data["files"]
    h = smells["health"]
    lines = [
        f"# Architecture report — {os.path.basename(data['graph'])}",
        "",
        f"Generated {data['generated']} · {stats['nodes']} nodes · {stats['edges']} edges",
        "",
        f"## Health: **{h['grade']}** ({h['score']}/100)",
        "",
    ]
    lines += _table(["Deduction", "Points"],
                    [[k.replace("_", " "), f"-{v}"] for k, v in h["deductions"].items() if v])
    lines += [
        f"Dead-code ratio {h['dead_code_pct']}% · cycles {smells['summary']['cycles']} · "
        f"layer violations {smells['summary']['layer_violations']} · "
        f"security findings {security['summary']['total']}",
        "",
        "## Census",
        "",
        f"- Source: {files['file_count']} file(s), {files['loc']:,} lines "
        f"({', '.join(f'{k} {v}%' for k, v in files['language_pct'].items()) or 'n/a'})",
        f"- Layers: {_counts(stats['layers'])}",
        f"- Kinds: {_counts(stats['kinds'])}",
        f"- Languages: {_counts(stats['langs'])}",
        f"- Edge types: {_counts(stats['edge_types'])}",
        "",
        "## Entry points (routes)",
        "",
    ]
    lines += _table(["Method", "Path", "Handler"],
                    [[r["method"], f"`{r['path']}`", f"`{r['node']}`"] for r in stats["routes"]])

    size = data.get("metrics") or {}
    if size:
        t = size["totals"]
        lines += [
            "## Size & complexity",
            "",
            f"- {t['files']} file(s), {t['lines']:,} lines — {t['code']:,} code, "
            f"{t['comment']:,} comment, {t['blank']:,} blank "
            f"(comment ratio {round(100 * t['comment_ratio'])}%)",
            "- Complexity is McCabe: 1 + every branch. Python nodes only.",
            "",
            "### Longest nodes",
            "",
        ]
        lines += _table(["Node", "LOC", "Complexity", "Location"],
                        [[f"`{x['id']}`", x["loc"], x["complexity"], f"`{x['file']}:{x['line']}`"]
                         for x in size["top_loc"]])
        lines += ["### Most complex nodes", ""]
        lines += _table(["Node", "Complexity", "LOC", "Location"],
                        [[f"`{x['id']}`", x["complexity"], x["loc"], f"`{x['file']}:{x['line']}`"]
                         for x in size["top_complexity"]])
        lines += ["### Largest files", ""]
        lines += _table(["File", "Lines", "Code"],
                        [[f"`{x['file']}`", x["lines"], x["code"]] for x in size["top_files"]])

    lines += ["## Smells", "", "### Circular dependencies", ""]
    lines += _table(["Cycle"], [[" → ".join(f"`{n}`" for n in c)] for c in smells["cycles"]])
    lines += ["### Backwards layer dependencies", ""]
    lines += _table(["From", "To", "Direction"],
                    [[f"`{v['source']}`", f"`{v['target']}`", f"{v['from']} → {v['to']}"]
                     for v in smells["layer_violations"]])
    lines += [f"### Orphans (no callers, not an entry point) — {len(smells['orphans'])}", ""]
    lines += _table(["Node"], [[f"`{n}`"] for n in smells["orphans"][:TOP_ORPHANS]])

    lines += ["## Anti-patterns & idioms", "", "### High coupling (hubs)", ""]
    lines += _table(["Node", "Fan-in", "Fan-out"],
                    [[f"`{x['node']}`", x["fan_in"], x["fan_out"]] for x in smells["hubs"]])
    lines += ["### God objects", ""]
    lines += _table(["Entity", "Reason", "Count"],
                    [[f"`{g['name']}`", g["reason"], g["count"]] for g in smells["god_objects"]])
    lines += ["### Detected idioms", ""]
    lines += _table(["Idiom", "Nodes"],
                    [[k, ", ".join(f"`{n}`" for n in v)] for k, v in smells["patterns"].items()])

    sev = security["summary"]["by_severity"]
    lines += [f"## Security & risk — {security['summary']['total']} finding(s) "
              f"(high {sev['high']}, medium {sev['medium']}, low {sev['low']})", ""]
    lines += _table(["Severity", "Rule", "Location", "Owner", "Snippet"],
                    [[f["severity"], f["rule"], f"`{f['file']}:{f['line']}`",
                      f"`{f['node']}`" if f["node"] else "—",
                      "`" + f["snippet"].replace("`", "'") + "`"]
                     for f in security["findings"][:TOP_FINDINGS]])

    hotspots = insights.get("hotspots", [])
    lines += ["## Hotspots (churn × connectivity)", ""]
    lines += _table(["Node", "Commits", "Fan-in", "Fan-out", "Risk", "Owner"],
                    [[f"`{x['node']}`", x["commits"], x["fan_in"], x["fan_out"], x["risk"],
                      x["owner"] or "—"] for x in hotspots[:TOP_HOTSPOTS]])
    if insights.get("summary", {}).get("note"):
        lines += [f"_{insights['summary']['note']}_", ""]

    lines += [
        "## Dig deeper",
        "",
        "```bash",
        "# how does a request travel between two nodes?",
        "python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>",
        "# what breaks if this changes?",
        "python scripts/trace_path.py --graph <graph.json> --impact-of <node>",
        "# what does my current diff affect?",
        "python scripts/trace_path.py --graph <graph.json> --impact-of-diff",
        "```",
        "",
    ]
    return "\n".join(lines)


def build(src, graph_path: str = DEFAULT_GRAPH, out_dir: str = DEFAULT_OUT_DIR) -> dict:
    with open(graph_path, "r", encoding="utf-8") as fh:
        graph = json.load(fh)

    os.makedirs(out_dir, exist_ok=True)
    security = scan_security.scan(src, graph_path)
    insights = git_insights.build(src, graph_path)
    analysis = analyze.report(graph_path, security["summary"]["by_severity"])
    size = metrics.build(src, graph_path, os.path.join(out_dir, "metrics.json"), TOP_BIG)

    data = {
        "graph": os.path.relpath(graph_path, SKILL_ROOT).replace("\\", "/"),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "census": census(graph), "files": file_census(size), "analysis": analysis,
        "security": security, "insights": insights, "metrics": size,
    }

    writes = {
        "security.json": security,
        "insights.json": insights,
        "architecture_report.json": data,
    }
    for name, payload in writes.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    md_path = os.path.join(out_dir, "architecture_report.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(to_markdown(data))

    print(f"Wrote {md_path}")
    print(f"  grade {analysis['health']['grade']} ({analysis['health']['score']}/100), "
          f"{security['summary']['total']} risk finding(s), "
          f"{len(insights.get('hotspots', []))} ranked hotspot(s)")
    print(f"  {size['totals']['lines']} line(s) across {size['totals']['files']} file(s), "
          f"longest node {size['top_loc'][0]['id'] if size['top_loc'] else 'n/a'}")
    print(f"  also: architecture_report.json, security.json, insights.json, metrics.json in {out_dir}")
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the combined architecture review report.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph to report on")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Where to write the report files")
    args = parser.parse_args(argv)
    if not os.path.isfile(args.graph):
        print(f"error: graph not found at {args.graph} — build a map first", file=sys.stderr)
        return 1
    build(args.src, args.graph, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
