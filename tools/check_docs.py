#!/usr/bin/env python3
"""check_docs.py -- mechanical half of this repo's docs-sync rule.

CLAUDE.md working principle 6 says the docs change in the same commit as the
behaviour they describe. A rule with no check is a wish: CLAUDE.md's own pipeline
diagram silently lost `brief` for several commits, and nothing noticed.

So this checks only facts a machine can settle, never prose:

  1. every script under scripts/ is listed in README.md's structure tree and
     named somewhere in CLAUDE.md
  2. every `scripts/...` path quoted in any doc points at a file that exists
  3. every kind/layer value in taxonomy.py appears in templates/TAXONOMY.md

It is a repo development tool -- it reads files that are not part of the
installed skill -- so it lives here, not in the skill's own scripts/.

Exit 0 when clean, 1 with one line per problem otherwise.
Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import ast
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(REPO, ".agents", "skills", "code-archaeologist")
SCRIPTS = os.path.join(SKILL, "scripts")
TAXONOMY_PY = os.path.join(SCRIPTS, "core", "taxonomy.py")
TAXONOMY_MD = os.path.join(SKILL, "templates", "TAXONOMY.md")

# Every doc that quotes a command path. Relative to the repo root.
DOCS = [
    "README.md",
    "docs/USAGE.md",
    "CLAUDE.md",
    "docs/PRESENTATION.html",
    ".agents/skills/code-archaeologist/SKILL.md",
    ".agents/skills/code-archaeologist/templates/TAXONOMY.md",
]

PATH_RE = re.compile(r"scripts/(?:[a-z_0-9]+/)*[a-z_0-9]+\.(?:py|js)")


def _read(rel: str) -> str:
    with open(os.path.join(REPO, rel), "r", encoding="utf-8") as fh:
        return fh.read()


def _scripts() -> list[str]:
    """Every shipped script, as a scripts/-relative posix path."""
    out = []
    for base, dirs, files in os.walk(SCRIPTS):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in sorted(files):
            if fn.endswith((".py", ".js")):
                rel = os.path.relpath(os.path.join(base, fn), SCRIPTS)
                out.append(rel.replace("\\", "/"))
    return sorted(out)


def check_inventory(problems: list[str]) -> None:
    """(1) Every script is in the README tree and named in CLAUDE.md."""
    readme = _read("README.md")
    claude = _read("CLAUDE.md")
    for rel in _scripts():
        name = os.path.basename(rel)
        if name not in readme:
            problems.append(f"README.md: structure tree does not list {rel}")
        if name not in claude:
            problems.append(f"CLAUDE.md: no mention of {rel}")


def check_paths(problems: list[str]) -> None:
    """(2) Every quoted scripts/ path resolves to a real file."""
    for doc in DOCS:
        seen = set()
        for m in PATH_RE.finditer(_read(doc)):
            p = m.group(0)
            if p in seen:
                continue
            seen.add(p)
            if not os.path.isfile(os.path.join(SKILL, p)):
                problems.append(f"{doc}: quotes {p}, which does not exist")


def check_taxonomy(problems: list[str]) -> None:
    """(3) Every kind/layer value in taxonomy.py is documented."""
    tree = ast.parse(_read(os.path.relpath(TAXONOMY_PY, REPO)))
    md = _read(os.path.relpath(TAXONOMY_MD, REPO))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id in ("KINDS", "LAYERS")):
            continue
        for elt in getattr(node.value, "elts", []):
            if isinstance(elt, ast.Constant) and f"`{elt.value}`" not in md:
                problems.append(
                    f"templates/TAXONOMY.md: {target.id} value `{elt.value}` is undocumented")


def main() -> int:
    problems: list[str] = []
    check_inventory(problems)
    check_paths(problems)
    check_taxonomy(problems)
    if problems:
        print(f"check_docs: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("check_docs: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
