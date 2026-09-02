#!/usr/bin/env python3
"""archaeologist.py — one entrypoint for the two Code Archaeologist maps.

Two independent commands:

  project   Structure map — which classes reference/import which.
            Runs build_wiki -> build_graph -> build_html (graph.html).

  flow      Behavior map — method-level call / request flow.
            Runs build_flow -> build_html (flow.html).

Examples:
  python archaeologist.py project --src ./src
  python archaeologist.py flow    --src ./src
  python archaeologist.py both     --src ./src

Zero dependencies (Python 3.10+). Thin wrapper over the individual scripts so
each stage stays runnable on its own.
"""
from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")

sys.path.insert(0, SCRIPT_DIR)
import build_wiki      # noqa: E402
import build_graph     # noqa: E402
import build_flow      # noqa: E402
import build_html      # noqa: E402


def run_project(src) -> int:
    print("== Project structure map ==")
    rc = build_wiki.build(src, os.path.join(DATA_DIR, "vault"))
    if rc:
        return rc
    rc = build_graph.build(os.path.join(DATA_DIR, "vault"), DATA_DIR)
    if rc:
        return rc
    return build_html.build(
        os.path.join(DATA_DIR, "graph.json"),
        os.path.join(DATA_DIR, "graph.html"),
        "Code Archaeologist — Project Structure",
    )


def run_flow(src) -> int:
    print("== Flow (call / request) map ==")
    rc = build_flow.build(src, os.path.join(DATA_DIR, "flow"), os.path.join(DATA_DIR, "flow_graph.json"))
    if rc:
        return rc
    return build_html.build(
        os.path.join(DATA_DIR, "flow_graph.json"),
        os.path.join(DATA_DIR, "flow.html"),
        "Code Archaeologist — Request Flow",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Code Archaeologist — build the structure and/or flow maps.")
    parser.add_argument("command", choices=["project", "flow", "both"], help="Which map to build")
    parser.add_argument("--src", nargs="+", default=["./src"],
                        help="One or more source roots (e.g. --src ./backend ./frontend)")
    args = parser.parse_args(argv)

    if args.command == "project":
        return run_project(args.src)
    if args.command == "flow":
        return run_flow(args.src)
    rc = run_project(args.src)
    return rc or run_flow(args.src)


if __name__ == "__main__":
    raise SystemExit(main())
