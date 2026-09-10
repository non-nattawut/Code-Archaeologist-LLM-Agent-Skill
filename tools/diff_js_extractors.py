#!/usr/bin/env python3
"""diff_js_extractors.py -- diff the tree-sitter JS/TS extractor against Babel's.

The phase-2 deletion order says no engine is removed before the thing that
replaces it has been checked against it, and that the check is a *diff of the
output*, not a reading of the code. This is that check for JS/TS: it runs
`js_bridge` -> `js_extract.js` (@babel/parser) and `js_ts_extract` (tree-sitter)
over the same files and reports every field that differs.

    python tools/diff_js_extractors.py [src-root]        # default: ./sample_src

Exit code 0 means the two agree exactly. Run it before deleting anything, and
keep its output -- once `js_extract.js` is gone this comparison cannot be made
again.

Repo tool, not part of the skill: it imports both extractors, which is the one
thing the shipped code must never do.
"""
from __future__ import annotations

import json
import os
import sys

SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".agents", "skills", "code-archaeologist")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import paths  # noqa: E402,F401  (puts the category dirs and vendor/ on sys.path)

import js_bridge  # noqa: E402
import js_ts_extract  # noqa: E402


def _rel(entry: dict, root: str) -> dict:
    """Same file key on both sides, so the diff is about content."""
    out = dict(entry)
    out["file"] = os.path.relpath(entry["file"], root).replace(os.sep, "/")
    return out


def _walk(path: str, a, b, out: list) -> None:
    """Every leaf difference between two JSON-ish trees, as `path: a != b`."""
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}  ({a!r} vs {b!r})")
        return
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                out.append(f"{path}.{key}: missing in babel, tree-sitter has {b[key]!r}")
            elif key not in b:
                out.append(f"{path}.{key}: missing in tree-sitter, babel has {a[key]!r}")
            else:
                _walk(f"{path}.{key}", a[key], b[key], out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}\n    babel      : {a!r}\n"
                       f"    tree-sitter: {b!r}")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(f"{path}[{i}]", x, y, out)
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")


def main() -> int:
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "sample_src")
    repo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    files = sorted(js_bridge.find_js_files(root))
    if not files:
        print(f"no JS/TS files under {root}")
        return 1

    babel = [_rel(e, repo) for e in js_bridge.extract_js_files(files)]
    tsit = [_rel(e, repo) for e in js_ts_extract.extract_js_files(files)]
    if js_bridge.frontend_degraded():
        print("babel extractor unavailable -- cannot diff (this is the reference)")
        return 1
    if js_ts_extract.frontend_degraded():
        print("tree-sitter extractor unavailable -- cannot diff")
        return 1

    by_file = {e["file"]: e for e in babel}
    diffs: list[str] = []
    for entry in tsit:
        name = entry["file"]
        if name not in by_file:
            diffs.append(f"{name}: only tree-sitter produced this file")
            continue
        _walk(name, by_file.pop(name), entry, diffs)
    for name in by_file:
        diffs.append(f"{name}: only babel produced this file")

    print(f"{len(files)} file(s) compared")
    if not diffs:
        print("OK   identical output")
        return 0
    print(f"FAIL {len(diffs)} difference(s):")
    for d in diffs:
        print("  -", d)
    return 1


if __name__ == "__main__":
    sys.exit(main())
