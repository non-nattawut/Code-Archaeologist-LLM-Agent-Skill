#!/usr/bin/env python3
"""build_wiki.py — Deterministic AST scanner -> Markdown vault.

Scans Python source under --src, extracts every top-level class (and module-level
functions grouped into a per-module page) using the stdlib `ast` module, and emits
one `<Entity>.md` per class into data/vault/. Every reference to another discovered
entity is written using strict Obsidian wikilink syntax: [[EntityName]].

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys

# ---------------------------------------------------------------------------
# Path resolution (relative to the skill root, not the CWD)
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_VAULT = os.path.join(DATA_DIR, "structure", "vault")
TEMPLATE_PATH = os.path.join(SKILL_ROOT, "templates", "wiki_page_template.md")

sys.path.insert(0, SCRIPT_DIR)
from taxonomy import infer_layer  # noqa: E402

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data"}


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def _name_of(node: ast.expr) -> str:
    """Best-effort dotted name for a decorator/base expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def iter_py_files(src: str):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def _rel_source(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace("\\", "/")
    return f"{os.path.basename(os.path.normpath(root))}/{rel}"


def extract_entities(roots: list[str]) -> list[dict]:
    """Return a list of entity dicts describing classes and module function-groups
    across one or more source roots."""
    entities: list[dict] = []
    for root in roots:
        for path in iter_py_files(root):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    source = fh.read()
                tree = ast.parse(source, filename=path)
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"  ! skipped {path}: {exc}", file=sys.stderr)
                continue

            rel = _rel_source(path, root)
            _extract_from_tree(tree, source, rel, entities)
    return entities


def _extract_from_tree(tree, source, rel, entities):
    # Module-level imported names (for reference resolution).
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imports.add(a.asname or a.name)

    module_funcs: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            entities.append(_class_entity(node, rel, imports, source))
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            module_funcs.append({
                "name": node.name,
                "doc": (ast.get_docstring(node) or "").strip().splitlines()[0:1],
            })

    if module_funcs:
        mod_name = os.path.splitext(os.path.basename(rel))[0]
        entities.append({
            "name": _module_entity_name(mod_name),
            "kind": "module",
            "source": rel,
            "bases": [],
            "decorators": [],
            "doc": (ast.get_docstring(tree) or "").strip(),
            "methods": [{"name": f["name"], "doc": (f["doc"][0] if f["doc"] else "")}
                        for f in module_funcs],
            "imports": sorted(imports),
        })


def _module_entity_name(mod: str) -> str:
    # snake_case module -> CamelCase-ish entity id, kept stable and readable.
    return "".join(part.capitalize() for part in mod.split("_")) + "Module"


def _class_entity(node: ast.ClassDef, rel: str, imports: set[str], source: str) -> dict:
    bases = [_name_of(b) for b in node.bases if _name_of(b)]
    decorators = [_name_of(d) for d in node.decorator_list if _name_of(d)]
    methods = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(item) or ""
            first = doc.strip().splitlines()[0] if doc.strip() else ""
            methods.append({"name": item.name, "doc": first})
    return {
        "name": node.name,
        "kind": "class",
        "source": rel,
        "bases": bases,
        "decorators": decorators,
        "doc": (ast.get_docstring(node) or "").strip(),
        "methods": methods,
        "imports": sorted(imports),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def load_template() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def wikilink(name: str, known: set[str]) -> str:
    return f"[[{name}]]" if name in known else f"`{name}`"


def render_entity(ent: dict, known: set[str], template: str) -> str:
    references: set[str] = set()

    bases_md = []
    for b in ent["bases"]:
        bases_md.append(f"- {wikilink(b, known)}")
        if b in known:
            references.add(b)
    decorators_md = []
    for d in ent["decorators"]:
        decorators_md.append(f"- {wikilink(d, known)}")
        if d in known:
            references.add(d)

    # Imports that match known entities become references too.
    for imp in ent.get("imports", []):
        if imp in known and imp != ent["name"]:
            references.add(imp)

    methods_md = []
    for m in ent["methods"]:
        doc = f" — {m['doc']}" if m["doc"] else ""
        methods_md.append(f"- `{m['name']}()`{doc}")

    refs_md = [f"- {wikilink(r, known)}" for r in sorted(references) if r != ent["name"]]

    summary = ent["doc"] if ent["doc"] else "_No docstring provided._"

    out = template
    out = out.replace("{{name}}", ent["name"])
    out = out.replace("{{layer}}", infer_layer(ent["name"], ent["decorators"], ent["bases"]))
    out = out.replace("{{source}}", ent["source"])
    out = out.replace("{{kind}}", ent["kind"])
    out = out.replace("{{summary}}", summary)
    out = out.replace("{{bases}}", "\n".join(bases_md) if bases_md else "_None._")
    out = out.replace("{{decorators}}", "\n".join(decorators_md) if decorators_md else "_None._")
    out = out.replace("{{methods}}", "\n".join(methods_md) if methods_md else "_None._")
    out = out.replace("{{references}}", "\n".join(refs_md) if refs_md else "_None._")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build(src, vault: str) -> int:
    roots = [os.path.abspath(s) for s in ([src] if isinstance(src, str) else src)]
    missing = [r for r in roots if not os.path.isdir(r)]
    if missing:
        print(f"error: source root(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    os.makedirs(vault, exist_ok=True)
    template = load_template()

    print(f"Scanning {', '.join(roots)} ...")
    entities = extract_entities(roots)
    if not entities:
        print("No Python entities found. Nothing to write.")
        return 0

    # First pass: registry of all known entity names for wikilink resolution.
    known = {e["name"] for e in entities}

    # Clean stale generated pages so re-runs are idempotent.
    for fn in os.listdir(vault):
        if fn.endswith(".md"):
            os.remove(os.path.join(vault, fn))

    written = 0
    for ent in entities:
        page = render_entity(ent, known, template)
        # Sanitize filename (entity names are identifiers, but be safe).
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", ent["name"])
        with open(os.path.join(vault, f"{safe}.md"), "w", encoding="utf-8") as fh:
            fh.write(page)
        written += 1

    print(f"Wrote {written} vault page(s) to {vault}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Scan Python source into a Markdown wiki vault.")
    parser.add_argument("--src", nargs="+", default=["./src"],
                        help="One or more source roots (e.g. --src ./backend ./frontend)")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Output vault directory")
    args = parser.parse_args(argv)
    return build(args.src, args.vault)


if __name__ == "__main__":
    raise SystemExit(main())
