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
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import SKILL_ROOT  # noqa: E402,F401  (also puts sibling script dirs on sys.path)

import call_ctx  # noqa: E402  (where a call is written: line, loop, branch)
import doc_text  # noqa: E402  (the one doc rule, shared with every producer)
import grammars  # noqa: E402
import taxonomy  # noqa: E402  (source_dirs: the one walk filter)

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
    return string_value(literal)


# --- expressions --------------------------------------------------------------

_SIMPLE_ESCAPES = {"\\": "\\", "'": "'", '"': '"', "a": "\a", "b": "\b", "f": "\f",
                   "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\n": ""}
_ESCAPE = re.compile(r"\\(N\{[^}]*\}|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|[0-7]{1,3}|.)",
                     re.S)


def _unescape(raw: str) -> str:
    """A non-raw literal's escapes decoded the way Python does; unknown ones (`\\w`) kept."""
    def one(m):
        e = m.group(1)
        if e in _SIMPLE_ESCAPES:
            return _SIMPLE_ESCAPES[e]
        if e[0] in "xuU":
            return chr(int(e[1:], 16))
        if e[0] == "N":
            try:
                return unicodedata.lookup(e[2:-1])
            except KeyError:
                return m.group(0)
        if e[0] in "01234567":
            return chr(int(e, 8))
        return m.group(0)
    return _ESCAPE.sub(one, raw)


def string_value(node) -> str:
    """The value of a string literal, or "" for anything else.

    tree-sitter hands back the source text, escapes and all; `ast` -- the oracle --
    hands back the value. Undecoded, a docstring holding `\\\\w` read as two
    backslashes (the oracle's one disagreement on the skill's own code).
    """
    if node is None or node.type != "string":
        return ""
    raw = "".join(text(c) for c in node.children if c.type == "string_content")
    start = next((c for c in node.children if c.type == "string_start"), None)
    prefix = text(start).rstrip("'\"").lower() if start is not None else ""
    return raw if "r" in prefix else _unescape(raw)


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


_RUN_LATER = frozenset({"function_definition", "class_definition", "decorated_definition", "lambda"})


def load_time_calls(module):
    """The calls a module makes as it is imported, in a stable order: top-level
    statements and the `if __name__ == "__main__":` guard -- never a def, class or lambda
    body, which run only when something calls them."""
    out = []
    stack = [c for c in reversed(module.children) if c.type not in _RUN_LATER]
    while stack:
        n = stack.pop()
        if n.type == "call":
            out.append(n)
        stack.extend(c for c in reversed(n.children) if c.type not in _RUN_LATER)
    return out


# ---------------------------------------------------------------------------
# The producer: `find_py_files` / `extract_py_files`, the contract `js_ts_extract`
# and `langs_extract` already keep. Everything below turns a parse tree into the
# normalized dicts the builders consume, so a Python resolution rule lives in the
# Python file rather than inside `build_flow` (the asymmetry phase 10 deleted).
# ---------------------------------------------------------------------------

HTTP_VERBS = {"get", "post", "put", "patch", "delete"}


def find_py_files(root: str) -> list[str]:
    """Every `.py` file under `root`, in a fixed order (constraint 2)."""
    out: list[str] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = taxonomy.source_dirs(base, dirs)
        for fn in files:
            if fn.endswith(".py"):
                out.append(os.path.join(base, fn))
    return sorted(out)


def _base_nodes(cls):
    """Base-class expressions of a class definition (`ast`'s `cls.bases`)."""
    args = field(cls, "superclasses")
    if args is None:
        return []
    return [c for c in args.named_children if c.type != "keyword_argument"]


def _decorator_names(decorators: list) -> list[str]:
    return [name_of(d.named_children[0]) if d.named_children else "" for d in decorators]


def _module_docstring(root) -> str:
    """The module's own docstring: its first statement, when that is a string."""
    if not root.named_children:
        return ""
    first = root.named_children[0]
    if first.type != "expression_statement" or not first.named_children:
        return ""
    literal = first.named_children[0]
    if literal.type != "string":
        return ""
    return "".join(text(c) for c in literal.children if c.type == "string_content")


def _imported_names(root) -> set[str]:
    """Every name an `import` / `from ... import` binds in this module.

    `ast` gave `Import` and `ImportFrom` with a tidy `names` list. tree-sitter gives
    `import_statement` and `import_from_statement` whose children are the dotted names
    and aliases themselves, so the alias-wins rule is applied here instead of being read
    off an attribute.
    """
    names: set[str] = set()
    for node in walk(root):
        plain = node.type == "import_statement"
        if not plain and node.type != "import_from_statement":
            continue
        for child in node.named_children:
            if child.type == "dotted_name" and child == field(node, "module_name"):
                continue                      # the module in `from X import y`
            if child.type == "aliased_import":
                alias = field(child, "alias")
                if alias is not None:
                    names.add(text(alias))
            elif child.type == "dotted_name":
                # `import a.b.c` binds `a`; `from m import a.b` cannot occur.
                names.add(text(child).split(".")[0] if plain else text(child))
            elif child.type == "identifier":
                names.add(text(child))
    return names


def _routes_of(decorators: list) -> list[dict]:
    """Every {method, path} a set of decorators declares.

    A list, not a single route, because one handler routinely serves several: Flask
    writes `@app.route("/orders", methods=["GET", "POST"])`, and stacking two decorators
    on one function is normal in every framework here. Returning only the first match
    silently dropped the rest, so a POST to a handler that also accepts GET never linked
    to its frontend caller.
    """
    routes: list[dict] = []
    for d in decorators:
        call = d.named_children[0] if d.named_children else None
        if call is None or call.type != "call":
            continue
        # @router.post(...) as well as a bare `@get(...)` imported from the framework.
        fn = field(call, "function")
        if fn is None:
            continue
        if fn.type == "attribute":
            verb = text(field(fn, "attribute")).lower()
        elif fn.type == "identifier":
            verb = text(fn).lower()
        else:
            continue
        args = call_args(call)
        path = string_value(args[0]) if args else ""
        # A route path starts with "/". Without this, `@patch("subprocess.run")` --
        # unittest.mock, in a test -- was a PATCH route (found on a real repository).
        if not path.startswith("/"):
            continue
        if verb in HTTP_VERBS:
            routes.append({"method": verb.upper(), "path": path})
        elif verb in ("route", "add_url_rule"):
            methods = [m.upper() for m in sequence_strings(call_keywords(call).get("methods"))]
            for method in (methods or ["GET"]):
                routes.append({"method": method, "path": path})
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for r in sorted(routes, key=lambda r: (r["path"], r["method"])):
        if (r["method"], r["path"]) not in seen:
            seen.add((r["method"], r["path"]))
            out.append(r)
    return out


def _attr_types(cls) -> dict[str, str]:
    """Map self.<attr> -> ClassName using __init__ annotations/assignments and
    class-level annotated attributes. Python states no field types, so the type of a
    receiver has to be built from what `__init__` was handed."""
    types: dict[str, str] = {}
    body = body_of(cls)
    if body is None:
        return types

    # Class-level annotated attributes:  service: OrderService
    for targets, _value, annotation in assignments(body):
        if annotation is None:
            continue
        target = targets[0] if targets else None
        if target is not None and target.type == "identifier":
            t = annotation_type(annotation)
            if t:
                types[text(target)] = t

    init = next((m for _decs, m in defs_in(body) if def_name(m) == "__init__"), None)
    if init is None:
        return types

    param_types = param_annotations(init)

    for targets, value, annotation in assignments(init):
        for tgt in targets:
            attr = self_attr_name(tgt)
            if not attr:
                continue
            # self.attr: OrderService = ...
            if annotation is not None:
                t = annotation_type(annotation)
                if t:
                    types[attr] = t
                continue
            # self.attr = param  /  self.attr = SomeClass()
            if value is None:
                continue
            if value.type == "identifier" and param_types.get(text(value)):
                types[attr] = param_types[text(value)]
            elif value.type == "call":
                ctor = name_of(field(value, "function"))
                if ctor and ctor[:1].isupper():
                    types[attr] = ctor
    return types


def _local_types(fn, seed: dict[str, str], decl=None, module: dict[str, str] | None = None) -> dict[str, str]:
    """Local variable -> ClassName from param annotations and `x = SomeClass()`.

    `fn` is the node to walk and `decl` the definition whose parameters to read. They
    differ for a decorated function: `ast` folded decorators into the node it walked, so
    the walk has to start at the wrapper to count the same call sites, while the
    parameters only exist on the definition inside it. `module` is the file's typed
    globals; a parameter or assignment of the same name hides one.
    """
    types = dict(seed)
    if module:
        params = params_of(decl if decl is not None else fn)
        hidden = {text(n) for n in walk(params) if n.type == "identifier"} if params is not None else set()
        hidden |= {text(t) for targets, _value, _ann in assignments(fn)
                   for t in targets if t.type == "identifier"}
        types = {**{k: v for k, v in module.items() if k not in hidden}, **types}
    types.update({k: v for k, v in param_annotations(decl if decl is not None else fn).items() if v})
    for targets, value, _annotation in assignments(fn):
        if value is None or value.type != "call":
            continue
        ctor = name_of(field(value, "function"))
        if ctor and ctor[:1].isupper():
            for tgt in targets:
                if tgt.type == "identifier":
                    types[text(tgt)] = ctor
    return types


def _calls(fn, attr_types: dict[str, str], local_types: dict[str, str]) -> list[dict]:
    """Every call site in `fn`, each as {name, type} and sometimes `recv`.

    `type` is what the *source* states about the receiver, in the vocabulary the other
    two producers use:

      ""        a bare call -- `helper()` -- which only a module function can answer
      "self"    `self.method()`, which only the enclosing class can answer
      "Cls"     a receiver whose class the source states (a typed attribute, parameter,
                local, or module global)
      "?"       a receiver whose type is not stated; with `recv` when that receiver is a
                bare name, because the graph may still know it as a class name and the
                producer cannot see the graph

    Deciding the type here and the target in `build_flow` is the split every other
    language already has: tree-sitter gives declarations, never resolution. Each entry
    also carries where it is written (`call_ctx.site`: `line`, and `loop` / `cond`).
    """
    out: list[dict] = []
    for node in calls_in(fn):
        func = field(node, "function")
        if func is None:
            continue
        site = call_ctx.site(node, fn)
        if func.type == "attribute":
            method = text(field(func, "attribute"))
            base = field(func, "object")
            base_name = text(base) if base is not None and base.type == "identifier" else ""
            if is_self_attr(base):                                  # self.attr.method()
                cls = attr_types.get(self_attr_name(base))
                out.append({"name": method, "type": cls or "?", **site})
            elif base_name == "self":                               # self.method()
                out.append({"name": method, "type": "self", **site})
            elif base_name in local_types:                          # typed param/local/global
                out.append({"name": method, "type": local_types[base_name], **site})
            elif base_name:                                         # maybe `ClassName.method()`
                out.append({"name": method, "type": "?", "recv": base_name, **site})
            else:
                out.append({"name": method, "type": "?", **site})
        elif func.type == "identifier":
            out.append({"name": text(func), "type": "", **site})
    return out


def _bare_calls(node) -> list[str]:
    """Bare names this subtree calls -- `helper()`, `Page()`. A method call states its
    receiver, which is the flow map's question, not the structure map's. Read from the
    definition itself, never the decorated wrapper: a decorator is not a reference the
    body makes."""
    return sorted({text(f) for n in calls_in(node) for f in [field(n, "function")]
                   if f is not None and f.type == "identifier"})


def _member(node, decorators, attr_types: dict[str, str], module: dict[str, str]) -> dict:
    """One `def` as the builders want it: its range opens at the first decorator
    (finding #6), while its `code` is the text from `def` onward -- `ast` walked
    decorators as part of the function but reported the segment from `def`, and both
    counts have to stay what they were."""
    outer = node.parent if decorators else node
    decos = _decorator_names(decorators)
    return {
        "name": def_name(node),
        "line": line(outer), "endLine": end_line(node),
        "doc": doc_text.join(docstring_of(node)),
        "signature": signature(node),
        "decorators": decos,
        "routes": _routes_of(decorators),
        "abstract": any(d.split(".")[-1] == "abstractmethod" for d in decos),
        "code": text(node),
        "bare_calls": _bare_calls(node),
        "calls": _calls(outer, attr_types, _local_types(outer, attr_types, decl=node, module=module)),
    }


def _class(node, decorators, module: dict[str, str]) -> dict:
    bases = [name_of(b) for b in _base_nodes(node)]
    attr_types = _attr_types(node)
    methods = [_member(m, m_decos, attr_types, module)
               for m_decos, m in defs_in(body_of(node))]
    base_names = {b.split(".")[-1] for b in bases}
    # Python states it by convention: a `Protocol` is an interface, an `ABC` or a class
    # with an `@abstractmethod` is abstract.
    kind = ("interface" if "Protocol" in base_names
            else "abstract" if any(m["abstract"] for m in methods) or "ABC" in base_names
            else "class")
    outer = node.parent if decorators else node
    return {
        "name": def_name(node), "kind": kind,
        "line": line(outer), "endLine": end_line(node),
        "doc": doc_text.join(docstring_of(node)),
        "bases": bases,
        "decorators": _decorator_names(decorators),
        "bare_calls": _bare_calls(node),
        "methods": methods,
    }


def _own_globals(root) -> dict[str, str]:
    """This file's top-level `store = Store()` / `store: Store = ...` (finding #27)."""
    types: dict[str, str] = {}
    for stmt in root.named_children:
        if stmt.type != "expression_statement":
            continue
        for targets, value, annotation in assignments(stmt):
            cls = annotation_type(annotation) if annotation is not None else ""
            if not cls and value is not None and value.type == "call":
                ctor = name_of(field(value, "function"))
                cls = ctor if ctor[:1].isupper() else ""
            for tgt in targets:
                if cls and tgt.type == "identifier":
                    types[text(tgt)] = cls
    return types


def _imported_globals(root, own: dict[str, dict[str, str]]) -> dict[str, str]:
    """Each unaliased `from m import store` whose module is exactly one parsed file
    typing `store`. The file's own assignment wins, so the caller merges this first."""
    modules = {k[:-3].replace(os.sep, "/").replace("/", "."): k
               for k in own if k.endswith(".py")}
    imported: dict[str, str] = {}
    for node in walk(root):
        if node.type != "import_from_statement":
            continue
        mod = field(node, "module_name")
        name = text(mod).lstrip(".") if mod is not None else ""
        hits = [r for m, r in modules.items() if name and (m == name or m.endswith("." + name))]
        if len(hits) != 1:
            continue
        for child in node.named_children:
            if child.type == "dotted_name" and child != mod and text(child) in own[hits[0]]:
                imported[text(child)] = own[hits[0]][text(child)]
    return imported


def _module_calls(root) -> list[str]:
    """The bare names a module calls as it is imported -- what marks a callee
    `entry: module`, since top-level code has no node to draw a link from."""
    out: list[str] = []
    for call in load_time_calls(root):
        fn = field(call, "function")
        if fn is not None and fn.type == "identifier":
            out.append(text(fn))
    return out


def _parse_file(path: str):
    """(source bytes, root node) for one file, or None -- warning once per run."""
    try:
        raw = read_source(path)
    except OSError as exc:
        print(f"  ! skipped {path}: {exc}", file=sys.stderr)
        return None
    tree = parse(raw)
    if tree is None:
        warn_missing()
        return None
    return tree.root_node


def extract_py_files(paths: list[str]) -> list[dict]:
    """The normalized per-file structure for `paths` ([] when nothing parses).

    Every file is parsed before any is read, because a call through a global resolves
    across files: `from store import widgets` types `widgets` from the module that
    assigns it (finding #27). That is the same reason `extract_js_files` parses first.
    """
    parsed = [(p, root) for p in paths for root in [_parse_file(p)] if root is not None]
    own = {p: _own_globals(root) for p, root in parsed}
    results = []
    for path, root in parsed:
        module = {**_imported_globals(root, own), **own[path]}
        classes, functions = [], []
        for decorators, node in defs_in(root, ("class_definition", "function_definition")):
            if node.type == "class_definition":
                classes.append(_class(node, decorators, module))
            else:
                functions.append(_member(node, decorators, {}, module))
        results.append({
            "file": path, "lang": "py",
            "doc": doc_text.join(_module_docstring(root)),
            "imports": sorted(_imported_names(root)),
            "classes": classes, "functions": functions,
            "module_calls": _module_calls(root),
        })
    return results


if __name__ == "__main__":
    import json
    args = sys.argv[1:]
    targets = find_py_files(os.path.abspath(args[0] if args else "."))
    print(json.dumps(extract_py_files(targets), indent=2, sort_keys=True))
