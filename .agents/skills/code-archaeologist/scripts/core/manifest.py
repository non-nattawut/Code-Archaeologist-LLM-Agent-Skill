#!/usr/bin/env python3
"""manifest.py — source-freshness snapshot so the agent knows when the maps are stale.

Every build records the roots it scanned and a content-hash of every source file
under them into `data/cache/manifest.json`. Before answering a flow/impact
question, the agent re-scans the same roots and compares: if any file was added,
changed, or deleted since the last build, the maps are stale and must be rebuilt
first. The roots are recorded so the check can be run without repeating them.

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)

import grammars  # noqa: E402  (which languages this machine can parse)
DEFAULT_MANIFEST = os.path.join(DATA_DIR, "cache", "manifest.json")

# Files the skill looks at. The graph builders parse only .py and .js/.ts, but the
# file-level passes (lines, risk scan, debt, tests) work on any of these.
SOURCE_EXTS = (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
               ".java", ".kt", ".kts", ".go", ".rs", ".cs", ".rb", ".php",
               ".swift", ".scala", ".groovy", ".dart", ".ex", ".exs",
               ".c", ".cc", ".cpp", ".h", ".hpp")
SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data"}


def _rel_key(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace("\\", "/")
    return f"{os.path.basename(os.path.normpath(root))}/{rel}"


def rel_roots(roots) -> list[str]:
    """Source roots in a portable, deterministic form for report artifacts.

    Absolute paths bake the build machine's layout into committed reports, so the
    same source produces different bytes on another checkout. Store them relative
    to the CWD with forward slashes instead; they stay resolvable for the
    freshness check when run from the project root (the documented workflow).
    Falls back to the basename when no relative path exists (e.g. another drive).
    """
    out = []
    for r in ([roots] if isinstance(roots, str) else roots):
        try:
            rel = os.path.relpath(r)
        except ValueError:
            rel = os.path.basename(os.path.normpath(r))
        out.append(rel.replace("\\", "/"))
    return out


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
        json.dump({"roots": rel_roots(roots), "grammars": grammars.versions(),
                   "files": snapshot(roots)},
                  fh, indent=2, sort_keys=True)
        fh.write("\n")


def recorded_roots(path: str = DEFAULT_MANIFEST) -> list[str]:
    """The roots the last build scanned, so `check` and `brief` need no --src."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return list(json.load(fh).get("roots") or [])
    except (OSError, ValueError):
        return []


def compare(roots=None, path: str = DEFAULT_MANIFEST) -> dict:
    """Diff the current source tree against the recorded manifest.

    With no roots, re-use the ones the last build recorded — asking "are the maps
    stale" should not require repeating where they came from.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            recorded = data.get("files", {})
    except (FileNotFoundError, ValueError):
        return {"stale": True, "reason": "no manifest - maps have never been built",
                "changed": [], "added": [], "deleted": []}

    roots = roots or list(data.get("roots") or [])
    if not roots:
        return {"stale": True, "reason": "manifest records no roots - rebuild, or pass --src",
                "changed": [], "added": [], "deleted": []}

    # A root that is not there cannot be compared. Saying so beats reporting every
    # recorded file as deleted, which is what an empty scan would otherwise look like.
    gone = [r for r in ([roots] if isinstance(roots, str) else roots) if not os.path.isdir(r)]
    if gone:
        return {"stale": True, "reason": f"source root(s) not found from here: {', '.join(gone)}",
                "changed": [], "added": [], "deleted": []}

    current = snapshot(roots)
    added = sorted(k for k in current if k not in recorded)
    deleted = sorted(k for k in recorded if k not in current)
    changed = sorted(k for k in current if k in recorded and current[k] != recorded[k])
    stale = bool(added or deleted or changed)

    # The source can be untouched and the graph still wrong: extraction depends on
    # which tree-sitter grammars are installed, so the same repo on two machines
    # yields different graphs. A graph that is smaller because a wheel is missing
    # must not be mistakable for a graph of a smaller codebase.
    was = data.get("grammars") or {}
    now = grammars.versions()
    grammar_note = ""
    if was != now:
        gone = sorted(set(was) - set(now))
        new = sorted(set(now) - set(was))
        moved = sorted(k for k in set(was) & set(now) if was[k] != now[k])
        bits = ([f"lost {', '.join(gone)}"] if gone else []) + \
               ([f"gained {', '.join(new)}"] if new else []) + \
               ([f"upgraded {', '.join(moved)}"] if moved else [])
        grammar_note = "grammars changed since last build (" + "; ".join(bits) + ")"
        stale = True

    if not stale:
        reason = "up to date"
    elif grammar_note and not (added or deleted or changed):
        reason = grammar_note
    elif grammar_note:
        reason = f"source changed since last build; {grammar_note}"
    else:
        reason = "source changed since last build"
    return {
        "stale": stale, "reason": reason,
        "changed": changed, "added": added, "deleted": deleted,
        "grammars": now,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report whether the maps are stale vs the source tree.")
    parser.add_argument("--src", nargs="+", default=None,
                        help="Source roots the maps were built from (default: the ones recorded by the last build)")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to manifest.json")
    args = parser.parse_args(argv)
    report = compare(args.src, args.manifest)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
