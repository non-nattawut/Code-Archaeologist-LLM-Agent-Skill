#!/usr/bin/env python3
"""manifest.py — source-freshness snapshot so the agent knows when the maps are stale.

Every build records a content-hash of every source file it scanned into
`data/cache/manifest.json`. Before answering a flow/impact question, the agent
re-scans the same roots and compares: if any file was added, changed, or deleted
since the last build, the maps are stale and must be rebuilt first.

The check is deterministic and cheap (sha1 of file contents, stdlib only) and the
report is tiny (~a few node ids), so it fits the zero-RAG budget. Keys are
`<root-basename>/<relpath>` to stay portable across checkouts — no absolute paths.

Used both as a library (build scripts call `write`) and as a CLI:
  python manifest.py --src ./backend ./frontend    # prints the staleness report

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_MANIFEST = os.path.join(DATA_DIR, "cache", "manifest.json")

SOURCE_EXTS = (".py", ".js", ".jsx", ".ts", ".tsx")
SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data"}


def _rel_key(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace("\\", "/")
    return f"{os.path.basename(os.path.normpath(root))}/{rel}"


def snapshot(roots) -> dict[str, str]:
    """Map `<root-basename>/<relpath>` -> sha1 of contents for every source file."""
    roots = [roots] if isinstance(roots, str) else roots
    files: dict[str, str] = {}
    for root in roots:
        root = os.path.abspath(root)
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in names:
                if not fn.endswith(SOURCE_EXTS):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with open(full, "rb") as fh:
                        digest = hashlib.sha1(fh.read()).hexdigest()[:12]
                except OSError:
                    continue
                files[_rel_key(full, root)] = digest
    return files


def write(roots, path: str = DEFAULT_MANIFEST) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"files": snapshot(roots)}, fh, indent=2, sort_keys=True)
        fh.write("\n")


def compare(roots, path: str = DEFAULT_MANIFEST) -> dict:
    """Diff the current source tree against the recorded manifest."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            recorded = json.load(fh).get("files", {})
    except (FileNotFoundError, ValueError):
        return {"stale": True, "reason": "no manifest — maps have never been built",
                "changed": [], "added": [], "deleted": []}

    current = snapshot(roots)
    added = sorted(k for k in current if k not in recorded)
    deleted = sorted(k for k in recorded if k not in current)
    changed = sorted(k for k in current if k in recorded and current[k] != recorded[k])
    stale = bool(added or deleted or changed)
    return {
        "stale": stale,
        "reason": "up to date" if not stale else "source changed since last build",
        "changed": changed, "added": added, "deleted": deleted,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report whether the maps are stale vs the source tree.")
    parser.add_argument("--src", nargs="+", default=["./src"],
                        help="Source roots the maps were built from")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to manifest.json")
    args = parser.parse_args(argv)
    report = compare(args.src, args.manifest)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
