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
