#!/usr/bin/env python3
"""check_py_oracle.py -- `ast` as a second opinion on the tree-sitter Python reader.

Python is the one language this skill can parse twice: `ast` ships with the
interpreter, so a second, independent, authoritative implementation costs
nothing. Phase 2 moved extraction onto tree-sitter for every language; this is
what stops that move from being taken on trust.

    python tools/check_py_oracle.py [src-root]      # default: ./sample_src

It parses every `.py` file both ways and compares what each says was *declared*:
module functions and classes, their methods, each one's line, signature and first
docstring line, and the routes its decorators declare. Any disagreement is a
finding and exits non-zero.

Scope, stated honestly: this checks **declarations**, not **resolution**. Whether
`self.service.place_order()` resolves to `OrderService.place_order` is not
something `ast` can arbitrate here -- that logic is ours either way, and its
check is the graph coming out byte-identical.

Repo tool, not part of the skill: `ast` is not on the shipped code's path any
more, and this is the only thing that still imports it.
"""
from __future__ import annotations

import ast
import os
import sys

SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".agents", "skills", "code-archaeologist")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import paths  # noqa: E402,F401  (puts the category dirs and vendor/ on sys.path)

import py_extract as px  # noqa: E402

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data"}


def _sig_key(sig) -> str:
    """A signature reduced to what the two engines must agree on.

    They agree on the parameters; they disagree on how to *print* them, and only
    in two ways, both measured across 26 files rather than guessed:
    `ast.unparse` writes `x: int=5` where the source says `x: int = 5`, and it
    rewrites `"a"` as `'a'`. Neither changes what the signature means.

    Comparing raw text instead would leave this check permanently red on any
    normal codebase, and a check that always fails is a check nobody reads -- so
    it is normalised here, narrowly and on purpose. Everything else about a
    signature, including parameter names, order, annotations and defaults, still
    has to match exactly.
    """
    if not isinstance(sig, str):
        return sig
    return "".join(sig.split()).replace('"', "'")


def _find(root: str) -> list[str]:
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        out += [os.path.join(base, f) for f in files if f.endswith(".py")]
    return sorted(out)


# --- what `ast` says ----------------------------------------------------------

def _ast_doc(node) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def _ast_sig(fn) -> str:
    try:
        return f"{fn.name}({ast.unparse(fn.args)})"
    except Exception:
        return f"{fn.name}(...)"


def _ast_decorators(node) -> list[str]:
    out = []
    for d in node.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        if isinstance(target, ast.Attribute):
            out.append(target.attr)
        elif isinstance(target, ast.Name):
            out.append(target.id)
    return sorted(out)


def _ast_decls(src: str) -> dict:
    tree = ast.parse(src)
    out: dict[str, dict] = {}
    fn_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out[node.name] = {"kind": "class", "line": node.lineno, "doc": _ast_doc(node),
                              "decorators": _ast_decorators(node)}
            for m in node.body:
                if isinstance(m, fn_types):
                    out[f"{node.name}.{m.name}"] = {
                        "kind": "method", "line": m.lineno, "doc": _ast_doc(m),
                        "sig": _ast_sig(m), "decorators": _ast_decorators(m)}
        elif isinstance(node, fn_types):
            out[node.name] = {"kind": "function", "line": node.lineno, "doc": _ast_doc(node),
                              "sig": _ast_sig(node), "decorators": _ast_decorators(node)}
    return out


# --- what tree-sitter says ----------------------------------------------------

def _ts_doc(node) -> str:
    doc = px.docstring_of(node)
    return doc.strip().splitlines()[0] if doc.strip() else ""


def _ts_decorators(decorators) -> list[str]:
    out = []
    for d in decorators:
        inner = d.named_children[0] if d.named_children else None
        if inner is None:
            continue
        target = px.field(inner, "function") if inner.type == "call" else inner
        if target is not None and target.type == "attribute":
            out.append(px.text(px.field(target, "attribute")))
        elif target is not None and target.type == "identifier":
            out.append(px.text(target))
    return sorted(out)


def _ts_decls(src: bytes) -> dict:
    tree = px.parse(src)
    root = tree.root_node
    out: dict[str, dict] = {}
    for decorators, node in px.defs_in(root, ("class_definition", "function_definition")):
        name = px.def_name(node)
        if node.type == "class_definition":
            out[name] = {"kind": "class", "line": px.line(node), "doc": _ts_doc(node),
                         "decorators": _ts_decorators(decorators)}
            for m_decs, m in px.defs_in(px.body_of(node)):
                out[f"{name}.{px.def_name(m)}"] = {
                    "kind": "method", "line": px.line(m), "doc": _ts_doc(m),
                    "sig": px.signature(m), "decorators": _ts_decorators(m_decs)}
        else:
            out[name] = {"kind": "function", "line": px.line(node), "doc": _ts_doc(node),
                         "sig": px.signature(node), "decorators": _ts_decorators(decorators)}
    return out


def main() -> int:
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "sample_src")
    repo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    if px.parser() is None:
        print("tree-sitter python grammar not installed -- cannot compare")
        return 1

    files = _find(root)
    findings: list[str] = []
    for path in files:
        raw = open(path, "rb").read()
        rel = os.path.relpath(path, repo).replace(os.sep, "/")
        try:
            a = _ast_decls(raw.decode("utf-8"))
        except SyntaxError as exc:
            findings.append(f"{rel}: ast could not parse it ({exc})")
            continue
        b = _ts_decls(raw)
        for key in sorted(set(a) | set(b)):
            if key not in a:
                findings.append(f"{rel}:{key}: tree-sitter declared it, ast did not")
            elif key not in b:
                findings.append(f"{rel}:{key}: ast declared it, tree-sitter did not")
            else:
                for fieldname in sorted(set(a[key]) | set(b[key])):
                    x, y = a[key].get(fieldname), b[key].get(fieldname)
                    if fieldname == "sig":
                        x, y = _sig_key(x), _sig_key(y)
                    if x != y:
                        findings.append(f"{rel}:{key}.{fieldname}: ast {x!r} != tree-sitter {y!r}")

    print(f"{len(files)} file(s) compared")
    if not findings:
        print("OK   0 disagreements")
        return 0
    print(f"FAIL {len(findings)} disagreement(s):")
    for f in findings:
        print("  -", f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
