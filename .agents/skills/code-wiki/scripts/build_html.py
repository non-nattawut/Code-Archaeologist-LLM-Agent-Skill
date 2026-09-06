#!/usr/bin/env python3
"""build_html.py — Generate the standalone, shareable HTML explorer.

Reads a graph JSON (structure `graph.json` or flow `flow_graph.json`) — optionally
enriched with that map's `architecture_report.json` — and writes a single
self-contained HTML file with all the data embedded inline (no server, no repo
access, works offline from `file://`).

The page is a three-pane explorer:

  left    health ring (A-F grade), color-by selector, node/edge/file/unused stat
          tiles, lines-of-code + language mix, and a file EXPLORER tree that
          filters the canvas.
  center  toolbar (zoom, fit, folder hulls, blast toggle, PNG export) over seven
          views of the same data — Graph, Treemap, Matrix, Tree, Flow, Cluster,
          Bundle — plus a status bar.
  right   FILE / PATTERNS / SECURITY tabs. FILE shows what the node does, its
          signature, source, blast radius (impact bar + affected list), its
          connections, git ownership, sibling functions with internal/external
          call counts, and any risk findings. PATTERNS lists smells, anti-patterns
          and idioms; SECURITY lists findings — both click through into FILE.

`force-graph` is loaded from a CDN; everything else is inline. Re-run any time.

    python build_html.py                                    # -> data/structure/graph.html
    python build_html.py --graph data/flow/flow_graph.json --out data/flow/flow.html \
        --title "Request Flow" --report data/report/flow/architecture_report.json

Zero external Python dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "structure", "graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "structure", "graph.html")

TEMPLATE_PATH = os.path.join(SKILL_ROOT, "templates", "viewer.html")


def load_template() -> str:
    """The page shell lives in `templates/viewer.html` (plain HTML/CSS/JS with three
    placeholders) so it can be read and edited like a normal front-end file."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _load(path: str | None) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        print(f"warning: {path} is not valid JSON; skipping it.")
        return {}


def report_for(graph_path: str, graph: dict, report: dict) -> dict:
    """Keep only the report data that belongs to THIS graph.

    Reports are built per map, and the two maps use different node ids (class vs
    Class.method), so a report for the other map would silently mis-attribute
    every finding, hotspot and grade.
    """
    if not report:
        return {}
    if os.path.basename(report.get("graph", "")) != os.path.basename(graph_path):
        print(f"warning: {report.get('graph')} was built for another map; ignoring it.")
        return {}
    ids = {n["id"] for n in graph.get("nodes", [])}
    files = {(n.get("source") or "").split(":")[0] for n in graph.get("nodes", [])}
    security = dict(report.get("security", {}))
    security["findings"] = [f for f in security.get("findings", [])
                            if f.get("node") in ids or f.get("file") in files]
    insights = dict(report.get("insights", {}))
    insights["nodes"] = {k: v for k, v in insights.get("nodes", {}).items() if k in ids}
    return {"analysis": report.get("analysis", {}), "files": report.get("files", {}),
            "census": report.get("census", {}), "security": security, "insights": insights}


def build(graph_path: str, out_path: str, title: str, report_path: str | None = None) -> int:
    if os.path.isfile(graph_path):
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    else:
        print(f"warning: {graph_path} not found; embedding an empty graph.")
        graph = {"nodes": [], "edges": []}

    report = report_for(graph_path, graph, _load(report_path))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    html = (load_template()
            .replace("__TITLE__", title)
            .replace("__GRAPH_DATA__", json.dumps(graph, indent=2))
            .replace("__REPORT_DATA__", json.dumps(report)))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Wrote standalone viewer: {out_path}")
    print(f"  {len(graph.get('nodes', []))} node(s), {len(graph.get('edges', []))} edge(s)")
    if report:
        health = report.get("analysis", {}).get("health", {})
        print(f"  report embedded: grade {health.get('grade', '?')}, "
              f"{len(report.get('security', {}).get('findings', []))} risk finding(s), "
              f"{len(report.get('insights', {}).get('nodes', {}))} node(s) with git history")
    else:
        print("  no report embedded (run `archaeologist.py report` for grade/churn/risk panels)")
    print("  Open it directly in a browser (file://) - no server needed.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate the standalone HTML code explorer.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to graph.json / flow_graph.json")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output HTML path")
    parser.add_argument("--title", default="Code Archaeologist — Graph", help="Page title/heading")
    parser.add_argument("--report", default=None,
                        help="architecture_report.json for this map; adds the health ring, "
                             "churn/risk color modes, ownership, and the Patterns/Security tabs")
    args = parser.parse_args(argv)
    return build(args.graph, args.out, args.title, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
