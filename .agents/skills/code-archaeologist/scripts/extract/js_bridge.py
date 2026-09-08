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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import SKILL_ROOT  # noqa: E402  (also puts sibling script dirs on sys.path)

# The extractor script sits next to this file; Node is run from that directory
# so `require("@babel/parser")` resolves against the skill's own node_modules.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JS_EXTRACT = os.path.join(SCRIPT_DIR, "js_extract.js")
JS_EXTS = (".js", ".jsx", ".ts", ".tsx")
SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data", "dist", "build"}

_warned = False
_degraded = False


def find_js_files(root: str) -> list[str]:
    found: list[str] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(JS_EXTS) and not fn.endswith(".d.ts"):
                found.append(os.path.join(base, fn))
    return found


def _skill_path() -> str:
    """The skill folder as the user would type it (wherever the skill was installed)."""
    try:
        rel = os.path.relpath(SKILL_ROOT)
    except ValueError:                      # different drive on Windows
        return SKILL_ROOT
    return SKILL_ROOT if rel.startswith("..") else rel.replace("\\", "/")


def frontend_degraded() -> bool:
    """True if JS/TS extraction was attempted and skipped (no Node, no parser, bad output).

    Callers must not prune per-node state on such a build: the frontend nodes are
    missing from the result but not from the codebase.
    """
    return _degraded


def _warn_once(msg: str) -> None:
    # Every skip path funnels through here, so this is also where "the frontend
    # is missing from this build" gets recorded.
    global _warned, _degraded
    _degraded = True
    if not _warned:
        print(msg, file=sys.stderr)
        _warned = True


def extract_js_files(files: list[str]) -> list[dict]:
    """Return the extractor's normalized JSON for the given files ([] on failure)."""
    if not files:
        return []
    if shutil.which("node") is None:
        _warn_once(f"  ! frontend skipped: Node.js not found on PATH (install Node, then "
                   f"`cd {_skill_path()} && npm install` to enable JS/TS parsing).")
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
        stderr = proc.stderr.strip()
        if "MISSING_DEP" in stderr:         # the parser was never installed
            _warn_once(f"  ! frontend skipped: @babel/parser is not installed. Run "
                       f"`cd {_skill_path()} && npm install` to enable JS/TS parsing.")
            return []
        detail = stderr.splitlines()[-1] if stderr else f"exit {proc.returncode}"
        _warn_once(f"  ! frontend skipped: {detail}")
        return []
    try:
        return json.loads(proc.stdout or "[]")
    except ValueError:
        _warn_once("  ! frontend skipped: extractor returned invalid JSON.")
        return []
