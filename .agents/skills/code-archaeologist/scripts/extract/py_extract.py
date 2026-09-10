#!/usr/bin/env python3
"""py_extract.py — the Python half of extraction, on tree-sitter instead of `ast`.

Last of the four engines to move, and the only one whose replacement adds a
dependency rather than removing one: `ast` ships with the interpreter. The reason
to do it anyway is that two engines for one job is the thing every other step of
this phase was spent deleting -- one parser, one set of node-type spellings, one
place a language's rules live.

`ast` is not gone. It stays as the **oracle**: `tools/check_py_oracle.py` parses
the same files both ways and fails on any disagreement about what was declared.
That is the whole reason a stdlib parser is worth keeping around -- it costs
nothing and it is the only second opinion this skill will ever have.

The functions here are the `ast` helpers of `build_flow.py` and `build_wiki.py`
translated node-for-node, deliberately keeping their names and their answers:

    ast.Name        -> identifier          ast.Call       -> call
    ast.Attribute   -> attribute           ast.ClassDef   -> class_definition
    ast.Assign      -> assignment          ast.FunctionDef-> function_definition
    ast.AnnAssign   -> assignment + `type` field
    decorator_list  -> the wrapping `decorated_definition`

Two shapes differ enough to be worth naming. A decorated definition is *wrapped*
in tree-sitter rather than carrying a list, so `defs_in` hands back both the
wrapper (for decorators) and the inner node (for name, line and body) -- `ast`
reports `lineno` at the `def`, and so must this. And a docstring is just the
first statement, so `docstring_of` looks for it rather than calling a helper.

Zero external dependencies beyond `tree-sitter` + `tree-sitter-python`. A missing
grammar is not an error here: callers degrade the same way they do for every
other language (hard constraint 1).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import SKILL_ROOT  # noqa: E402,F401  (also puts sibling script dirs on sys.path)

import grammars  # noqa: E402

LANG = "python"

# Statements that hold a nested suite we still want to look inside when walking a
# function body for calls and assignments.
_FUNC_TYPES = ("function_definition",)


def parser():
    """The cached Python parser, or None when the grammar is not installed."""
    return grammars.parser_for(LANG)


def read_source(path: str) -> bytes:
    r"""File contents as UTF-8 bytes with newlines normalised to `\n`.

    `ast` was handed text read through Python's universal-newline translation, so
    every source segment it produced used `\n` regardless of what was on disk.
    tree-sitter is handed bytes and reports exactly what is there, so a CRLF
    checkout produced different `code` for the same source -- and since a node's
    description cache is keyed by a hash of that code, every cached AI summary on
    a CRLF machine would silently miss. Found by exactly that: one node went
    pending after the port, on the one sample file saved with CRLF.

    Normalising here rather than at each use keeps line numbers identical (the
    newline count does not change) and gives every consumer -- hashes, clone token
    shapes, signatures -- the same bytes on every platform.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


_warned = False


def warn_missing() -> None:
    """One named warning when Python itself cannot be parsed, per process.

    Python used to need nothing installed, so this failure could not happen. It
    can now, and it must degrade like every other language rather than produce a
    silently empty graph (hard constraint 1).

    It lives here rather than in each builder because both `build_wiki` and
    `build_flow` hit it in one `both` run: a flag per builder printed the same
    sentence twice, which reads like two faults. One module, one flag, one
    message -- the same reason `js_ts_extract` only warns once.
    """
    global _warned
    if not _warned:
        _warned = True
        print(f"  ! python skipped: no tree-sitter grammar installed. Run "
              f"`{grammars.install_hint([LANG])}` to enable it.", file=sys.stderr)


def parse(src: bytes):
    """Parse `src`, or None when there is no grammar. Never raises on bad syntax.

    tree-sitter has no `SyntaxError`: a broken file yields a tree with `has_error`
    set and whatever it could recover. That is a behaviour change from `ast`,
    which refused the file outright, so callers that used to catch `SyntaxError`
    ask `tree.root_node.has_error` instead.
    """
    p = parser()
    return p.parse(src) if p is not None else None


# --- node helpers -------------------------------------------------------------

def text(node) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def line(node) -> int:
    return node.start_point[0] + 1


def end_line(node) -> int:
    return node.end_point[0] + 1


def field(node, name):
    return node.child_by_field_name(name) if node is not None else None


def walk(node):
    """Every node in the subtree, comments included -- `ast.walk`'s counterpart."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def name_of(node) -> str:
    """`ast`'s `_name_of`: the bare name a Name / Attribute / Call refers to."""
    if node is None:
        return ""
    if node.type == "identifier":
        return text(node)
    if node.type == "attribute":
        return text(field(node, "attribute"))
    if node.type == "call":
        return name_of(field(node, "function"))
    return ""


def annotation_type(ann) -> str:
    """A bare class name from a type annotation, if simple.

    `Optional[Foo]` and `List[Foo]` unwrap to `Foo`, matching what `ast` did with
    `Subscript.slice` -- the type inside the brackets is the one calls resolve
    against.
    """
    if ann is None:
        return ""
    if ann.type == "identifier":
        return text(ann)
    if ann.type == "attribute":
        return text(field(ann, "attribute"))
    if ann.type == "subscript":
        return annotation_type(field(ann, "subscript"))
    if ann.type == "type":                       # the `type` wrapper node
        return annotation_type(ann.named_children[0]) if ann.named_children else ""
    return ""


def is_self_attr(node) -> bool:
    """`self.<attr>`, the anchor for every field-typed call resolution."""
    if node is None or node.type != "attribute":
        return False
    obj = field(node, "object")
    return obj is not None and obj.type == "identifier" and text(obj) == "self"


def self_attr_name(node) -> str:
    return text(field(node, "attribute")) if is_self_attr(node) else ""


# --- declarations -------------------------------------------------------------

def _unwrap(node):
    """(decorators, definition) for a child of a block or module."""
    if node.type == "decorated_definition":
        return ([c for c in node.children if c.type == "decorator"],
                field(node, "definition"))
    return ([], node)


def defs_in(block, types=_FUNC_TYPES):
    """Direct children of `block` of the given types, with their decorators.

    Yields `(decorators, node)`. Only direct children, exactly like iterating
    `tree.body` or `cls.body` -- a function nested inside another function is not
    a node of its own in either engine.
    """
    if block is None:
        return
    for child in block.named_children:
        decorators, definition = _unwrap(child)
        if definition is not None and definition.type in types:
            yield decorators, definition


def body_of(node):
    return field(node, "body")


def def_name(node) -> str:
    return text(field(node, "name"))


def params_of(node):
    """The `parameters` node of a function definition."""
    return field(node, "parameters")


def signature(node) -> str:
    """`name(params)` -- the parameter list as written, on one line.

    `ast` built this with `ast.unparse(fn.args)`, which reformats; tree-sitter
    hands back exactly what was typed, and **that includes the line breaks**. A
    parameter list wrapped across three lines produced a `signature` containing
    newlines -- fine in a file, wrong in a graph field that gets rendered into a
    vault page, a context pack and a node label. Found by running the `ast` oracle
    over the skill's own 26 files, where the sample's 6 had no wrapped signature
    to expose it.

    So whitespace runs collapse to one space. What is deliberately *not*
    normalised is spelling: `x: int = 5` keeps its spaces where `ast.unparse`
    would print `x: int=5`, and `""` stays `""` rather than becoming `''`. The
    source's own spelling is the better answer -- it is what the reader sees in
    the file -- and `tools/check_py_oracle.py` compares the two modulo exactly
    that formatting.
    """
    params = params_of(node)
    inner = text(params).strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    return f"{def_name(node)}({' '.join(inner.split())})"


def param_annotations(node) -> dict[str, str]:
    """`param name -> annotated class name` for one function definition."""
    out: dict[str, str] = {}
    params = params_of(node)
    if params is None:
        return out
    for child in params.named_children:
        if child.type == "typed_parameter":
            ident = next((c for c in child.named_children if c.type == "identifier"), None)
            target = annotation_type(field(child, "type"))
            if ident is not None and target:
                out[text(ident)] = target
        elif child.type == "typed_default_parameter":
            ident = field(child, "name")
            target = annotation_type(field(child, "type"))
            if ident is not None and target:
                out[text(ident)] = target
    return out


def docstring_of(node) -> str:
    """The function's or class's docstring, or "".

    A docstring is not a node type -- it is the first statement, when that
    statement is a bare string. `ast.get_docstring` also runs `cleandoc`; every
    caller here takes `.strip().splitlines()[0]`, so the leading quote handling is
    all that has to match.
    """
    block = body_of(node)
    if block is None or not block.named_children:
        return ""
    first = block.named_children[0]
    if first.type != "expression_statement" or not first.named_children:
        return ""
    literal = first.named_children[0]
    if literal.type != "string":
        return ""
    content = [c for c in literal.children if c.type == "string_content"]
    return "".join(text(c) for c in content)


# --- expressions --------------------------------------------------------------

def string_value(node) -> str:
    """The text of a string literal, or "" for anything else."""
    if node is None or node.type != "string":
        return ""
    return "".join(text(c) for c in node.children if c.type == "string_content")


def call_args(node):
    """Positional argument nodes of a call, keywords excluded."""
    arglist = field(node, "arguments")
    if arglist is None:
        return []
    return [c for c in arglist.named_children if c.type != "keyword_argument"]


def call_keywords(node) -> dict:
    """`keyword -> value node` for one call."""
    arglist = field(node, "arguments")
    out = {}
    if arglist is None:
        return out
    for child in arglist.named_children:
        if child.type == "keyword_argument":
            key = field(child, "name")
            if key is not None:
                out[text(key)] = field(child, "value")
    return out


def sequence_strings(node) -> list[str]:
    """String elements of a list/tuple literal, for `methods=["GET", "POST"]`."""
    if node is None or node.type not in ("list", "tuple"):
        return []
    return [string_value(c) for c in node.named_children if c.type == "string"]


def assignments(scope):
    """Every assignment in `scope`, as (targets, value, annotated_type).

    One generator for what `ast` split across `Assign` and `AnnAssign`: in
    tree-sitter both are `assignment`, and an annotation is just a `type` field
    being present.
    """
    for node in walk(scope):
        if node.type != "assignment":
            continue
        left, right = field(node, "left"), field(node, "right")
        if left is None:
            continue
        targets = ([c for c in left.named_children if c.type in ("identifier", "attribute")]
                   if left.type in ("pattern_list", "tuple_pattern") else [left])
        yield targets, right, field(node, "type")


def calls_in(scope):
    """Every `call` node in `scope`, in a stable order."""
    return [n for n in walk(scope) if n.type == "call"]
