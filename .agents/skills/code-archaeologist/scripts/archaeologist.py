#!/usr/bin/env python3
"""archaeologist.py — one entrypoint for the two Code Archaeologist maps.

Commands:

  project   Structure map — which classes reference/import which.
            Runs build_wiki -> build_graph.

  flow      Behavior map — method-level call / request flow.
            Runs build_flow.

  brief     Fixed-size digest of the built maps: counts, grade, entry points,
            biggest/most complex/most churned/riskiest nodes. Start here.

  check     Are the maps stale vs the current source?

  report    Review pass over every built map — smells, health grade, risk scan and
            git hotspots (report/<map>/).

Every command ends by re-rendering `data/explorer.html`: one page holding both
maps, switched from its header.

Examples:
  python archaeologist.py project --src ./src
  python archaeologist.py flow    --src ./src
  python archaeologist.py both    --src ./src
  python archaeologist.py report  --src ./src
  python archaeologist.py brief   --src ./src

Zero dependencies (Python 3.10+). Thin wrapper over the individual scripts so
each stage stays runnable on its own.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA_DIR  # noqa: E402  (also puts the script category dirs on sys.path)

STRUCTURE_DIR = os.path.join(DATA_DIR, "structure")
FLOW_DIR = os.path.join(DATA_DIR, "flow")
REPORT_DIR = os.path.join(DATA_DIR, "report")
EXPLORER_HTML = os.path.join(DATA_DIR, "explorer.html")
# One report per map, because node ids (and therefore every finding, hotspot and
# census figure) belong to one graph or the other.
GRAPHS = {
    "structure": os.path.join(STRUCTURE_DIR, "graph.json"),
    "flow": os.path.join(FLOW_DIR, "flow_graph.json"),
}

import brief           # noqa: E402
import build_wiki      # noqa: E402
import build_graph     # noqa: E402
import build_flow      # noqa: E402
import build_html      # noqa: E402
import manifest        # noqa: E402
import report          # noqa: E402


def report_json(map_name: str) -> str:
    return os.path.join(REPORT_DIR, map_name, "architecture_report.json")


def render_explorer() -> int:
    """Re-render the one page that holds both maps."""
    sources = {name: (graph, report_json(name)) for name, graph in GRAPHS.items()}
    return build_html.build(sources, EXPLORER_HTML)

def run_project(src) -> int:
    print("== Project structure map ==")
    rc = build_wiki.build(src, os.path.join(STRUCTURE_DIR, "vault"))
    if rc:
        return rc
    rc = build_graph.build(os.path.join(STRUCTURE_DIR, "vault"), STRUCTURE_DIR)
    if rc:
        return rc
    return render_explorer()


def run_flow(src) -> int:
    print("== Flow (call / request) map ==")
    rc = build_flow.build(src, os.path.join(FLOW_DIR, "notes"), os.path.join(FLOW_DIR, "flow_graph.json"))
    if rc:
        return rc
    return render_explorer()


def run_report(src) -> int:
    """Review pass over every built map: smells + grade + risks + hotspots per map,
    then re-render the explorer with both reports embedded."""
    print("== Architecture report ==")
    built = [name for name, graph in GRAPHS.items() if os.path.isfile(graph)]
    if not built:
        print("error: no map found — run `project` or `flow` first.", file=sys.stderr)
        return 1
    for name in built:
        print(f"-- {name} map --")
        report.build(src, GRAPHS[name], os.path.join(REPORT_DIR, name))
    return render_explorer()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Code Archaeologist — build the structure and/or flow maps.")
    parser.add_argument("command", choices=["project", "flow", "both", "check", "report", "brief"],
                        help="Build a map, 'check' whether the maps are stale vs the source, "
                             "'report' the review pass (grade, risks, hotspots), or 'brief' the digest")
    parser.add_argument("--src", nargs="+", default=None,
                        help="One or more source roots (e.g. --src ./backend ./frontend); "
                             "'check' and 'brief' default to the roots the last build recorded")
    args = parser.parse_args(argv)
    # The passes that scan the tree need a root; the two that only read artifacts
    # fall back to the recorded roots, so `check` / `brief` work with no arguments.
    src = args.src or ["./src"]

    if args.command == "check":
        import json
        print(json.dumps(manifest.compare(args.src), indent=2))
        return 0

    if args.command == "report":
        return run_report(src)

    if args.command == "brief":
        return brief.main(["--src", *args.src] if args.src else [])

    if args.command == "project":
        rc = run_project(src)
    elif args.command == "flow":
        rc = run_flow(src)
    else:
        rc = run_project(src) or run_flow(src)

    if not rc:
        manifest.write(src)  # record the roots + source hashes so `check` can detect drift
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
