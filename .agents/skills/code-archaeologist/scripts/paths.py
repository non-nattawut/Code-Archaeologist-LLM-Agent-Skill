"""paths — the one definition of where this skill's files live.

Every script resolves its inputs and outputs from the skill root rather than the
current working directory (hard constraint 3), and every script imports its
siblings by bare module name (`import taxonomy`). Both used to be re-derived in
each file with a `SCRIPT_DIR` / `SKILL_ROOT` pair, which broke the moment the
scripts were grouped into `core/`, `extract/`, `review/` and `query/` — the
number of `dirname` calls stopped being the same for every file.

So the layout lives here once, and importing this module also puts `scripts/`
and each category directory on `sys.path`. That import side effect is the point:
it is what keeps the ~35 existing cross-category imports working unchanged, and
what lets any script still be run directly from any working directory.

It also puts `<skill>/vendor` in front of them, which is where the tree-sitter
wheels are installed: the skill's dependencies live inside the skill, so they
never enter the environment the user runs everything else in, and deleting the
skill folder removes every trace of them. The prepend is conditional, so a
machine that installed the wheels the old way -- straight into site-packages --
keeps working with no vendor directory at all.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import os
import sys

SCRIPTS_ROOT = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPTS_ROOT)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
TEMPLATES_DIR = os.path.join(SKILL_ROOT, "templates")

# Where `pip install --target` puts the tree-sitter runtime and grammar wheels.
# Git-ignored: the wheels are built for one interpreter version and one OS, so
# this directory is machine-local in the same way node_modules/ is.
VENDOR_DIR = os.path.join(SKILL_ROOT, "vendor")

# Script categories, in dependency order: core is imported by everything, query
# and review sit on top. The order only matters for sys.path precedence, which
# never collides today (module names are unique across categories).
CATEGORIES = ("core", "extract", "review", "query")


def long_path(path: str) -> str:
    """`path`, usable past Windows' 260-character MAX_PATH.

    Every node gets a file named after its id -- a vault page, a flow note -- and
    a name defined in several files is qualified by its *path* when its stem is
    not enough (core/ids.py). In a monorepo that id is long, and the skill folder
    already sits a few directories deep, so `open()` failed with a bare
    FileNotFoundError and the whole build died. Found by tools/time_build.py on a
    real repository (phase 6d). The `\\\\?\\` prefix lifts the limit; elsewhere, and
    for short paths, the path is returned unchanged.
    """
    if os.name != "nt":
        return path
    full = os.path.abspath(path)
    if len(full) < 240 or full.startswith("\\\\?\\"):
        return path
    return "\\\\?\\" + full


def skill_rel(path: str) -> str:
    """`path` relative to the skill, with `/` -- or absolute when it has no relative form.

    Every report records which graph it was built from. On Windows a graph on another
    drive than the skill has no relative path at all, and `os.path.relpath` raised --
    in five places, each a hand-rolled copy of the same line. Found in phase 9 by a
    regression case whose graph lived in the temp directory (C:) while the skill sits
    on D:; `build_graph` had the same shape in phase 5.
    """
    try:
        return os.path.relpath(path, SKILL_ROOT).replace("\\", "/")
    except ValueError:
        return os.path.abspath(path).replace("\\", "/")


def _install() -> None:
    """Put scripts/, every category dir and vendor/ on sys.path, nearest-first."""
    for name in reversed(CATEGORIES):
        d = os.path.join(SCRIPTS_ROOT, name)
        if d not in sys.path:
            sys.path.insert(0, d)
    if SCRIPTS_ROOT not in sys.path:
        sys.path.insert(0, SCRIPTS_ROOT)
    # Last insert, so it ends up first: a vendored wheel wins over a copy in
    # site-packages. Skipped when absent, which is what keeps a plain
    # `pip install` working for anyone who already ran one.
    if os.path.isdir(VENDOR_DIR) and VENDOR_DIR not in sys.path:
        sys.path.insert(0, VENDOR_DIR)


_install()
