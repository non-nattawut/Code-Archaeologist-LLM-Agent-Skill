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

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import os
import sys

SCRIPTS_ROOT = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPTS_ROOT)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
TEMPLATES_DIR = os.path.join(SKILL_ROOT, "templates")

# Script categories, in dependency order: core is imported by everything, query
# and review sit on top. The order only matters for sys.path precedence, which
# never collides today (module names are unique across categories).
CATEGORIES = ("core", "extract", "review", "query")


def _install() -> None:
    """Put scripts/ and every category dir on sys.path, nearest-first."""
    for name in reversed(CATEGORIES):
        d = os.path.join(SCRIPTS_ROOT, name)
        if d not in sys.path:
            sys.path.insert(0, d)
    if SCRIPTS_ROOT not in sys.path:
        sys.path.insert(0, SCRIPTS_ROOT)


_install()
