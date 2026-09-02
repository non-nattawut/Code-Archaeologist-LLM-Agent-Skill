#!/usr/bin/env python3
"""apply_descriptions.py — cache AI-written method summaries.

Part of the hybrid flow pipeline. `build_flow.py` writes
`data/pending_descriptions.json` listing methods that need a natural-language
summary (no docstring, not already cached). The agent reads that file, writes a
one-line summary per method, and passes them here as JSON `{ "<id>": "<summary>" }`.

This merges each summary into `data/descriptions.json`, keyed by node id with the
current source hash (taken from the pending file) so the cache invalidates
automatically when the method's source changes. Re-run `build_flow.py` afterward
and the summaries flow into flow_graph.json / flow.html.

Usage:
  python apply_descriptions.py --input summaries.json
  cat summaries.json | python apply_descriptions.py        # or via stdin

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DESCRIPTIONS_PATH = os.path.join(DATA_DIR, "descriptions.json")
PENDING_PATH = os.path.join(DATA_DIR, "pending_descriptions.json")


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return default


def _save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Cache AI-written method summaries into descriptions.json.")
    parser.add_argument("--input", help="JSON file of {id: summary}. Reads stdin if omitted.")
    args = parser.parse_args(argv)

    raw = open(args.input, "r", encoding="utf-8").read() if args.input else sys.stdin.read()
    try:
        summaries = json.loads(raw)
    except ValueError as exc:
        print(f"error: input is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(summaries, dict):
        print("error: input must be a JSON object of {id: summary}", file=sys.stderr)
        return 2

    pending = _load_json(PENDING_PATH, {})
    cache = _load_json(DESCRIPTIONS_PATH, {})

    applied, skipped = 0, []
    for node_id, summary in summaries.items():
        info = pending.get(node_id)
        if not info or "hash" not in info:
            skipped.append(node_id)
            continue
        cache[node_id] = {"hash": info["hash"], "summary": str(summary).strip()}
        applied += 1

    _save_json(DESCRIPTIONS_PATH, cache)
    print(f"Applied {applied} summary(ies) to {DESCRIPTIONS_PATH}")
    if skipped:
        print(f"  skipped (not in pending / unknown): {', '.join(skipped)}", file=sys.stderr)
    print("  Now re-run build_flow.py (or archaeologist.py flow) to refresh the graph & HTML.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
