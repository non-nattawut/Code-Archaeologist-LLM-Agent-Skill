#!/usr/bin/env python3
"""build_html.py — Generate the standalone HTML explorer for both maps.

Reads the graphs (`structure/graph.json`, `flow/flow_graph.json`) plus each map's
`architecture_report.json`, and writes ONE self-contained page with all of it
embedded inline. No server, no repo access, works offline from `file://`; the
header switches between the structure map and the flow map without reloading.

The page is a three-pane explorer:

  header  brand, the Structure/Flow switch, and the active map's grade.
  left    health ring (A-F), color-by selector, node/edge/file/unused stat tiles,
          lines-of-code + language mix, and a file EXPLORER tree that filters the
          canvas.
  center  toolbar (zoom, fit, folder hulls, blast toggle, PNG export) over seven
          views of the same data — Graph, Treemap, Matrix, Tree, Flow, Cluster,
          Bundle — plus a status bar.
  right   FILE / PATTERNS / SECURITY tabs. FILE shows what the node does, its
          signature, source, blast radius (impact bar + affected list), its
          connections, git ownership, sibling functions with internal/external
          call counts, and any risk findings. PATTERNS lists smells, anti-patterns
          and idioms; SECURITY lists findings — both click through into FILE.

    python build_html.py                                  # both maps -> data/explorer.html
    python build_html.py --structure-graph "" --out flow_only.html    # one map only

`force-graph` is vendored (`templates/vendor/`) and inlined with everything else, so
the page needs no network at all. The shell is `templates/viewer.html`, so the
front-end can be edited without touching Python.

Zero external Python dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR, TEMPLATES_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "viewer.html")
VENDOR_JS_PATH = os.path.join(TEMPLATES_DIR, "vendor", "force-graph.min.js")
DEFAULT_OUT = os.path.join(DATA_DIR, "explorer.html")

# map name -> (switch label, subtitle, default graph, default report)
MAPS = {
    "structure": ("Structure", "class-level map: which entity references which",
                  os.path.join(DATA_DIR, "structure", "graph.json"),
                  os.path.join(DATA_DIR, "report", "structure", "architecture_report.json")),
    "flow": ("Flow", "method-level map: which method calls which",
             os.path.join(DATA_DIR, "flow", "flow_graph.json"),
             os.path.join(DATA_DIR, "report", "flow", "architecture_report.json")),
}
DEFAULT_SOURCES = {name: (graph, report) for name, (_, _, graph, report) in MAPS.items()}


def load_template() -> str:
    """The page shell lives in `templates/viewer.html` (plain HTML/CSS/JS with three
    placeholders) so it can be read and edited like a normal front-end file."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def load_vendor_js() -> str:
    """The graph library, vendored so the page needs no network (constraint 4).

    Inlined rather than linked because the explorer is one shareable file: a
    <script src> to a sibling would break the moment someone emails just the HTML.
    """
    try:
        with open(VENDOR_JS_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        print(f"error: vendored graph library missing at {VENDOR_JS_PATH};"
              " the explorer would render an empty canvas.")
        raise


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
    security = report.get("security", {})
    insights = report.get("insights", {})
    # Only what the page actually reads, so the embedded payload stays small.
    return {
        "analysis": report.get("analysis", {}),
        "files": report.get("files", {}),
        "security": {"summary": security.get("summary", {}),
                     "findings": [f for f in security.get("findings", [])
                                  if f.get("node") in ids or f.get("file") in files]},
        "insights": {"nodes": {k: v for k, v in insights.get("nodes", {}).items() if k in ids}},
    }


def collect(sources: dict[str, tuple[str, str]]) -> dict:
    """sources: map name -> (graph path, report path). Maps with no graph are skipped."""
    maps = {}
    for name, (graph_path, report_path) in sources.items():
        if not graph_path or not os.path.isfile(graph_path):
            continue
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
        label, subtitle = MAPS.get(name, (name.title(), name, "", ""))[:2]
        maps[name] = {"label": label, "title": subtitle, "graph": graph,
                      "report": report_for(graph_path, graph, _load(report_path))}
    return maps


def build(sources: dict[str, tuple[str, str]] | None = None, out_path: str = DEFAULT_OUT,
          title: str = "Code Archaeologist") -> int:
    maps = collect(sources or DEFAULT_SOURCES)
    if not maps:
        print("error: no graph found - run `archaeologist.py project|flow|both` first.")
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    html = (load_template()
            .replace("__VENDOR_JS__", load_vendor_js())
            .replace("__TITLE__", title)
            .replace("__MAPS_DATA__", json.dumps(maps, separators=(",", ":"))))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Wrote standalone explorer: {out_path}")
    for name, data in maps.items():
        bits = [f"{len(data['graph']['nodes'])} node(s)", f"{len(data['graph']['edges'])} edge(s)"]
        if data["report"]:
            health = data["report"].get("analysis", {}).get("health", {})
            bits += [f"grade {health.get('grade', '?')}",
                     f"{len(data['report']['security'].get('findings', []))} risk finding(s)"]
        else:
            bits.append("no report yet (run `archaeologist.py report` for the review panels)")
        print(f"  {name:<10} {', '.join(bits)}")
    print("  Open it directly in a browser (file://) - no server needed.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate the standalone HTML code explorer.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output HTML path")
    parser.add_argument("--title", default="Code Archaeologist", help="Page title")
    for name, (_, _, graph, report) in MAPS.items():
        parser.add_argument(f"--{name}-graph", default=graph,
                            help=f"{name} graph JSON (pass an empty string to leave it out)")
        parser.add_argument(f"--{name}-report", default=report,
                            help=f"architecture_report.json for the {name} map")
    args = parser.parse_args(argv)

    sources = {name: (getattr(args, f"{name}_graph"), getattr(args, f"{name}_report"))
               for name in MAPS}
    return build(sources, args.out, args.title)


if __name__ == "__main__":
    raise SystemExit(main())
