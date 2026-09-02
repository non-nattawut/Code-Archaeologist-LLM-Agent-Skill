#!/usr/bin/env python3
"""js_bridge.py — run the Node JS/TS extractor from Python.

Frontend support is the one place this skill uses a dependency (Node + the
`@babel/parser` npm package, invoked via `js_extract.js`). This bridge finds
JS/TS files, shells out to the extractor, and returns the parsed structure. If
Node or the parser is unavailable it prints one clear warning and returns [],
so the Python-only (backend) pipeline keeps working with zero dependencies.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JS_EXTRACT = os.path.join(SCRIPT_DIR, "js_extract.js")
JS_EXTS = (".js", ".jsx", ".ts", ".tsx")
SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data", "dist", "build"}

_warned = False


def find_js_files(root: str) -> list[str]:
    found: list[str] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(JS_EXTS) and not fn.endswith(".d.ts"):
                found.append(os.path.join(base, fn))
    return found


def _warn_once(msg: str) -> None:
    global _warned
    if not _warned:
        print(msg, file=sys.stderr)
        _warned = True


def extract_js_files(files: list[str]) -> list[dict]:
    """Return the extractor's normalized JSON for the given files ([] on failure)."""
    if not files:
        return []
    if shutil.which("node") is None:
        _warn_once("  ! frontend skipped: Node.js not found on PATH "
                   "(install Node + run `npm install` in the skill to enable JS/TS parsing).")
        return []
    try:
        proc = subprocess.run(
            ["node", JS_EXTRACT, *files],
            capture_output=True, text=True, cwd=SCRIPT_DIR,
        )
    except OSError as exc:
        _warn_once(f"  ! frontend skipped: could not run node ({exc}).")
        return []
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else f"exit {proc.returncode}"
        _warn_once(f"  ! frontend skipped: {detail}")
        return []
    try:
        return json.loads(proc.stdout or "[]")
    except ValueError:
        _warn_once("  ! frontend skipped: extractor returned invalid JSON.")
        return []
