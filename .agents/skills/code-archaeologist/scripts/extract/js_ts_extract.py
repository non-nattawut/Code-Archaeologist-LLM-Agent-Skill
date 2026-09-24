#!/usr/bin/env python3
"""js_ts_extract.py — JS/TS/JSX/TSX structure extraction from a tree-sitter parse.

Replaced the Node extractor (`js_bridge.py` -> `js_extract.js`, @babel/parser 7.29.8)
and deliberately kept its exact output contract: `find_js_files` /
`extract_js_files` returning one dict per file with `classes`, `functions`,
`imports` and `routes`. Keeping the contract is what let the port be verified by
diffing JSON against Babel's rather than by reading code -- the same method that
caught three real bugs when Java/Go/C# moved to tree-sitter. That diff reported
**identical output** on all six sample files, and the graphs it produced were
byte-identical to Babel's; the reference and the diff tool were deleted at step 4
of the roadmap, so the record of that comparison is the commit that made it.

Four grammars for four extensions, because they are genuinely different parsers:
`.tsx` will not parse with the TypeScript language (the `<` is ambiguous between
a type argument and a JSX tag), and `.jsx` rides along with JavaScript.

What Babel gave for free and is reconstructed here:

  leading comments   Babel attaches them to the node; tree-sitter leaves them as
                     siblings, so `_doc_above` walks back one sibling and keeps
                     the same adjacency rule -- a comment documents a node only
                     when it ends on the line directly above it.
  decorator ranges   Babel folds decorators into the decorated node's range, so
                     `@Controller(...)` on line 7 makes the class start at 7, not
                     at `class` on line 8. `_start_line` restores that.
  call order         `calls` is insertion-ordered, and the graph's edges are
                     built from it, so the walk visits `function` before
                     `arguments` exactly as Babel's key order did.

Requires `tree-sitter` plus `tree-sitter-javascript` and `tree-sitter-typescript`.
Missing either is not an error: the files are skipped with one named warning and
the rest of the graph still builds (hard constraint 1).
"""
from __future__ import annotations

import functools
import json
import os
import posixpath
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import SKILL_ROOT  # noqa: E402  (also puts sibling script dirs on sys.path)

import call_ctx  # noqa: E402  (where a call is written: line, loop, branch)
import doc_text  # noqa: E402  (the one doc-comment rule, shared with every producer)
import grammars  # noqa: E402

JS_EXTS = (".js", ".jsx", ".ts", ".tsx")
from taxonomy import next_entry, source_dirs  # noqa: E402  (one definition of "not source")
HTTP_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
HTTP_CLIENT_NAMES = frozenset({
    "axios", "api", "client", "http", "httpclient", "request", "fetcher",
    "caller", "endpoint", "ky", "superagent", "instance"
})


def _is_http_client(name: str, axios_names: set) -> bool:
    """Whether `name` acts as an HTTP client."""
    if not name:
        return False
    if name in axios_names:
        return True
    low = name.lower()
    if "axios" in low:
        return True
    if low in HTTP_CLIENT_NAMES:
        return True
    return any(low.endswith(s) for s in ("client", "http", "httpclient", "api", "apiclient", "fetcher"))


# Which grammar reads which extension. `.tsx` needs its own language, not
# TypeScript's: measured, not assumed -- OrderCard.tsx parses with `has_error`
# True under both `javascript` and `typescript`, and False only under `tsx`.
LANG_BY_EXT = {".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "tsx"}

_warned = False
_degraded = False


def find_js_files(root: str) -> list[str]:
    found: list[str] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = source_dirs(base, dirs)
        for fn in files:
            if fn.endswith(JS_EXTS) and not fn.endswith(".d.ts"):
                found.append(os.path.join(base, fn))
    return found


def frontend_degraded() -> bool:
    """True if JS/TS extraction was attempted and skipped.

    Callers must not prune per-node state on such a build: the frontend nodes are
    missing from the result but not from the codebase.
    """
    return _degraded


def _skill_path() -> str:
    """The skill folder as the user would type it (wherever it was installed)."""
    try:
        rel = os.path.relpath(SKILL_ROOT)
    except ValueError:                      # different drive on Windows
        return SKILL_ROOT
    return SKILL_ROOT if rel.startswith("..") else rel.replace("\\", "/")


def _warn_once(msg: str) -> None:
    global _warned, _degraded
    _degraded = True
    if not _warned:
        print(msg, file=sys.stderr)
        _warned = True


# --- tree helpers -------------------------------------------------------------

def _text(node) -> str:
    return node.text.decode("utf-8", "replace")


def _line(node) -> int:
    return node.start_point[0] + 1


def _field(node, name):
    return node.child_by_field_name(name) if node is not None else None


def _named(node, *types):
    return [c for c in node.named_children if c.type in types] if node is not None else []


def _doc_above(node) -> str:
    """The comment block above `node`, read exactly as `langs_extract` reads one.

    Walks previous *named* siblings so blank lines are invisible, stops at the
    first non-comment -- a comment separated from the declaration by code is not
    its doc -- and hands every consecutive block to `doc_text.clean`, which joins
    the lot into one line. That is the one rule now, so the same comment gets the
    same answer in a .ts file as it does in a .java one.

    What this gave up, deliberately: Babel hands the first statement in a file
    *every* comment that precedes it, which is how a file header once became the
    summary of whichever symbol was declared first, and the fix was an adjacency
    test -- only a comment ending on the previous line counted. The Java family
    never needed one because `package` and `import` sit between a header and the
    first declaration, and a JS/TS file's own imports do that job in practice. A
    header in a file that imports nothing is now read as the first declaration's
    doc, which is the price of one rule.
    """
    comments = []
    prev = node.prev_named_sibling
    while prev is not None and prev.type == "comment":
        comments.append(_text(prev))
        prev = prev.prev_named_sibling
    # `xml`: JSDoc borrowed Javadoc's HTML, so `<p>` is markup here as it is there.
    return doc_text.clean(comments, xml=True)


def _decorators_of(node) -> list:
    """Decorators attached to `node`, whether they sit inside it or before it.

    TypeScript puts a class's decorator on the wrapping `export_statement` and a
    method's decorator as a preceding sibling inside `class_body`, so both
    directions have to be looked at. Babel papered over this with
    `node.decorators || raw.decorators`.
    """
    decs = [c for c in node.children if c.type == "decorator"]
    prev = node.prev_sibling
    while prev is not None and prev.type == "decorator":
        decs.insert(0, prev)
        prev = prev.prev_sibling
    return decs


def _start_line(node, decorators) -> int:
    """Where Babel would say this node starts -- decorators included."""
    return min([_line(node)] + [_line(d) for d in decorators])


def _doc_for(node, decorators) -> str:
    """`_doc_above`, anchored where Babel would anchor it.

    A decorated member starts at its first decorator, so the documenting comment
    sits above *that*, not above the `method_definition`. Anchoring on the member
    finds the decorator as its previous sibling and reports no doc at all -- which
    is what the first diff against Babel showed on both Nest routes.
    """
    return _doc_above(decorators[0] if decorators else node)


# --- literals -----------------------------------------------------------------

# The current file's top-level `const X = "/literal"` strings, set by `_extract_tree`
# before anything in the file is read. A service module routinely names its base
# once (`const API_BASE_URL = "/orders"`) and writes `${API_BASE_URL}/list` in every
# call; read as `:API_BASE_URL/list`, 89 of a real frontend's calls linked nowhere.
_FILE_CONSTS: dict = {}


def _string_consts(program) -> dict:
    """`name -> value` for every top-level `const name = "string"` in one file."""
    out = {}
    for raw in program.named_children:
        node = _unwrap_export(raw)
        if node is None or node.type != "lexical_declaration" or node.child(0) is None \
                or node.child(0).type != "const":
            continue
        for dec in _named(node, "variable_declarator"):
            name, value = _field(dec, "name"), _field(dec, "value")
            if name is not None and name.type == "identifier" and value is not None \
                    and value.type == "string":
                out[_text(name)] = _url_of(value)
    return out


def _from_config_object(node, class_consts: dict | None = None) -> tuple[str, str]:
    """Extract (method, url) from an axios/fetch config object literal { url: '...', method: 'POST' }."""
    if node is None or node.type != "object":
        return "", ""
    url, method = "", "GET"
    for pair in _named(node, "pair"):
        key = _field(pair, "key")
        val = _field(pair, "value")
        if key is None or val is None:
            continue
        k = _text(key).strip("\"'")
        if k == "url":
            url = _url_of(val, class_consts)
        elif k == "method":
            method = _url_of(val, class_consts).upper() or "GET"
    return method, url


def _url_of(node, class_consts: dict | None = None, in_expr: bool = False) -> str:
    """A route-ish path from a string or template literal, else "".

    A same-file string constant stands for its value (`_FILE_CONSTS`), or class
    constant (`class_consts`), as the whole argument or inside `${...}` or `+`;
    dynamic substitutions or identifiers become a `:name` segment.
    """
    if node is None:
        return ""
    class_consts = class_consts or {}
    if node.type == "string":
        return "".join(_text(c) for c in node.children if c.type == "string_fragment")
    if node.type == "identifier":
        name = _text(node)
        if name in class_consts:
            return class_consts[name]
        if name in _FILE_CONSTS:
            return _FILE_CONSTS[name]
        return (":" + name) if in_expr else ""
    if node.type == "member_expression":
        obj = _field(node, "object")
        prop = _field(node, "property")
        prop_name = _text(prop) if prop else ""
        if obj is not None and obj.type == "this":
            if prop_name in class_consts:
                return class_consts[prop_name]
        if prop_name in _FILE_CONSTS:
            return _FILE_CONSTS[prop_name]
        return (":" + (prop_name or "param")) if in_expr else ""
    if node.type == "binary_expression":
        op = _field(node, "operator")
        if op is None:
            for c in node.children:
                if c.type == "+":
                    op = c
                    break
        if op is not None and _text(op) == "+":
            left = _url_of(_field(node, "left"), class_consts, in_expr=True)
            right = _url_of(_field(node, "right"), class_consts, in_expr=True)
            if left and right:
                return left + right
            return left or right
    if node.type == "template_string":
        out = []
        for c in node.children:
            if c.type == "string_fragment":
                out.append(_text(c))
            elif c.type == "template_substitution":
                inner = c.named_children[0] if c.named_children else None
                if inner is not None:
                    resolved = _url_of(inner, class_consts, in_expr=False)
                    if resolved:
                        out.append(resolved)
                    else:
                        param_name = ""
                        if inner.type == "identifier":
                            param_name = _text(inner)
                        elif inner.type == "member_expression":
                            prop = _field(inner, "property")
                            param_name = _text(prop) if prop else "param"
                        else:
                            param_name = "param"
                        out.append(":" + param_name)
        return "".join(out)
    return ":param" if in_expr else ""


def _method_from_options(node, class_consts: dict | None = None) -> str:
    """The `method:` of a fetch options object, defaulting to GET like Babel."""
    if node is not None and node.type == "object":
        for pair in _named(node, "pair"):
            key = _field(pair, "key")
            if key is not None and _text(key).strip("\"'") == "method":
                value = _field(pair, "value")
                if value is not None:
                    m = _url_of(value, class_consts).upper()
                    if not m and value.type == "identifier":
                        m = _text(value).upper()
                    if m:
                        return m
    return "GET"


def _callee_parts(call):
    """(identifier name, member property name, member object name) for a call."""
    fn = _field(call, "function")
    # tree-sitter-typescript parses `await api.post<T>(url)` with the await *inside* the
    # callee: call(function: await(api.post), type_arguments, arguments). Unwrapped, or
    # every awaited generic call -- the normal typed-axios shape -- lost its name and its
    # URL (a real frontend registered 12 of 86 axios calls).
    if fn is not None and fn.type == "await_expression" and fn.named_children:
        fn = fn.named_children[0]
    if fn is None:
        return "", "", ""
    if fn.type == "identifier":
        return _text(fn), "", ""
    if fn.type == "member_expression":
        prop = _field(fn, "property")
        obj = _field(fn, "object")
        prop_str = _text(prop) if prop is not None else ""
        obj_str = ""
        if obj is not None:
            if obj.type == "identifier":
                obj_str = _text(obj)
            elif obj.type == "member_expression":
                inner_prop = _field(obj, "property")
                if inner_prop is not None:
                    obj_str = _text(inner_prop)
        return "", prop_str, obj_str
    return "", "", ""


def _args(call) -> list:
    node = _field(call, "arguments")
    return list(node.named_children) if node is not None else []


# --- receiver types -----------------------------------------------------------
# An edge needs a node id, and a node id is `Class.method`. `store.save()` gives the
# method; the class has to come from what the source states about `store`. These are
# the shapes that state it. Everything else is "?" -- dropped, never guessed, which
# is the same rule `langs_extract` follows for Java/Go/C#.

def _type_name(text: str) -> str:
    """A type annotation reduced to the one class it names, or "".

    `: WidgetStore` -> `WidgetStore`, `Promise<Widget>` -> `Promise`. A union, an
    array, an object literal or a function type names no single class, so it
    reduces to "" and the receiver stays unresolved.
    """
    head = text.strip().lstrip(":").strip().split("<")[0].split(".")[-1].strip()
    return head if re.fullmatch(r"[A-Za-z_]\w*", head) else ""


def _annotation(node) -> str:
    """The class named by a node's `type:` annotation, or ""."""
    ann = _field(node, "type")
    return _type_name(_text(ann)) if ann is not None else ""


def _new_type(node) -> str:
    """`new WidgetStore()` -> `WidgetStore`, anything else -> ""."""
    if node is None or node.type != "new_expression":
        return ""
    ctor = _field(node, "constructor")
    return _text(ctor) if ctor is not None and ctor.type == "identifier" else ""


def _scope_types(node) -> dict:
    """Names inside one function whose class the source states: typed parameters,
    typed locals, and locals assigned a `new X()`.

    Nested functions are walked too -- a closure sees its enclosing consts, and
    tracking scopes to catch a shadowing parameter would cost more than it buys.
    """
    types: dict[str, str] = {}
    if node is None:
        return types

    def walk(n) -> None:
        if n.type in ("required_parameter", "optional_parameter"):
            pattern = _field(n, "pattern")
            if pattern is not None and pattern.type == "identifier":
                declared = _annotation(n)
                if declared:
                    types[_text(pattern)] = declared
        elif n.type == "variable_declarator":
            name, value = _field(n, "name"), _field(n, "value")
            if name is not None and name.type == "identifier":
                declared = _annotation(n) or _new_type(value)
                if declared:
                    types[_text(name)] = declared
        for child in n.named_children:
            walk(child)

    walk(node)
    return types


def _field_types(body) -> dict:
    """`this.<name>` -> class, from what a class body states.

    Three shapes: a typed property (`private store: WidgetStore`), a constructor
    parameter property (`constructor(private store: WidgetStore)`) and an assignment
    of a fresh instance (`this.store = new WidgetStore()`, the JS shape with no
    annotation anywhere).
    """
    types: dict[str, str] = {}
    if body is None:
        return types

    def walk(n) -> None:
        if n.type in ("public_field_definition", "field_definition"):
            name = _field(n, "property") or _field(n, "name")
            if name is not None:
                declared = _annotation(n) or _new_type(_field(n, "value"))
                if declared:
                    types[_text(name)] = declared
        elif n.type in ("required_parameter", "optional_parameter"):
            pattern = _field(n, "pattern")
            if pattern is not None and pattern.type == "identifier" and \
                    any(c.type == "accessibility_modifier" for c in n.children):
                declared = _annotation(n)
                if declared:
                    types[_text(pattern)] = declared
        elif n.type == "assignment_expression":
            left, declared = _field(n, "left"), _new_type(_field(n, "right"))
            if declared and left is not None and left.type == "member_expression":
                obj, prop = _field(left, "object"), _field(left, "property")
                if obj is not None and obj.type == "this" and prop is not None:
                    types[_text(prop)] = declared
        for child in n.named_children:
            walk(child)

    walk(body)
    return types


def _field_consts(body) -> dict[str, str]:
    """`this.<name>` -> string value, for string fields defined in a class body."""
    consts: dict[str, str] = {}
    if body is None:
        return consts

    def walk(n) -> None:
        if n.type in ("public_field_definition", "field_definition"):
            name = _field(n, "property") or _field(n, "name")
            val = _field(n, "value")
            if name is not None and val is not None and val.type == "string":
                consts[_text(name)] = _url_of(val)
        elif n.type == "assignment_expression":
            left, right = _field(n, "left"), _field(n, "right")
            if left is not None and left.type == "member_expression" and right is not None and right.type == "string":
                obj, prop = _field(left, "object"), _field(left, "property")
                if obj is not None and obj.type == "this" and prop is not None:
                    consts[_text(prop)] = _url_of(right)
        for child in n.named_children:
            walk(child)

    walk(body)
    return consts


def _receiver_type(call, types: dict, self_type: str) -> str:
    """The class a call's receiver has: "" for a bare call, "?" where unreadable."""
    fn = _field(call, "function")
    if fn is not None and fn.type == "await_expression" and fn.named_children:
        fn = fn.named_children[0]
    if fn is None or fn.type != "member_expression":
        return ""
    obj = _field(fn, "object")
    if obj is None:
        return "?"
    if obj.type == "this":
        return self_type or "?"
    if obj.type == "new_expression":                      # new WidgetStore().save()
        return _new_type(obj) or "?"
    if obj.type == "identifier":                          # typed name, or a class: DateUtil.now()
        head = _text(obj)
        return types.get(head, "") or (head if re.fullmatch(r"[A-Z]\w*", head) else "?")
    if obj.type == "member_expression":                   # this.store.save()
        inner, prop = _field(obj, "object"), _field(obj, "property")
        if inner is not None and inner.type == "this" and prop is not None:
            return types.get(_text(prop), "") or "?"
    return "?"


# --- collectors ---------------------------------------------------------------

def _axios_instances(program) -> set:
    """Names assigned from `axios.create(...)`, plus `axios` itself.

    `const api = axios.create({...})` is how most apps actually reach an API, and
    `api.get(...)` is otherwise indistinguishable from any other method call.
    Only identifiers assigned from `axios.create()` count, never an arbitrary
    object that happens to have a `.get()`.
    """
    names = {"axios"}
    factories = _instance_factories(program)
    for raw in program.named_children:
        node = _unwrap_export(raw)
        if node is None or node.type not in ("lexical_declaration", "variable_declaration"):
            continue
        for dec in _named(node, "variable_declarator"):
            name, value = _field(dec, "name"), _field(dec, "value")
            if name is None or name.type != "identifier" or value is None:
                continue
            if _is_axios_create(value) or (value.type == "call_expression"
                                           and _callee_parts(value)[0] in factories):
                names.add(_text(name))
    return names


def _is_axios_create(node) -> bool:
    return node is not None and node.type == "call_expression" and \
        _callee_parts(node)[1:] == ("create", "axios")


_FUNCTIONS = ("arrow_function", "function_expression", "function", "function_declaration")


def _instance_factories(program) -> set:
    """Top-level functions that return a fresh axios instance.

    `const make = (base) => { const i = axios.create(); ...; return i; }` then
    `export default make(apiBase)` -- one factory for several base URLs is a normal
    shape (a real frontend made every one of its 97 API calls through one), and
    without this rule none of them was an HTTP call.
    """
    found: set = set()
    for raw in program.named_children:
        node = _unwrap_export(raw)
        if node is None:
            continue
        if node.type == "function_declaration":
            pairs = [(_field(node, "name"), _field(node, "body"))]
        elif node.type in ("lexical_declaration", "variable_declaration"):
            pairs = [(_field(d, "name"), _field(_field(d, "value"), "body"))
                     for d in _named(node, "variable_declarator")
                     if _field(d, "value") is not None and _field(d, "value").type in _FUNCTIONS]
        else:
            continue
        for name, body in pairs:
            if name is not None and body is not None and _returns_instance(body):
                found.add(_text(name))
    return found


def _returns_instance(body) -> bool:
    """Does this function body return `axios.create(...)`, directly or through a local?

    Nested functions are not entered: an interceptor's `return config` is not the
    factory's return value.
    """
    if _is_axios_create(body):                                  # `() => axios.create()`
        return True
    local: set = set()
    returned: list = []

    def walk(node) -> None:
        if node.type == "variable_declarator" and _is_axios_create(_field(node, "value")):
            ident = _field(node, "name")
            if ident is not None:
                local.add(_text(ident))
        elif node.type == "return_statement" and node.named_children:
            returned.append(node.named_children[0])
        for child in node.named_children:
            if child.type not in _FUNCTIONS:
                walk(child)

    walk(body)
    return any(_is_axios_create(r) or (r.type == "identifier" and _text(r) in local)
               for r in returned)


# `method_definition` too: an object literal's `refresh() { helper() }` runs when called,
# not when the module loads.
_FUNCTION_NODES = frozenset({"arrow_function", "function_expression", "function", "method_definition",
                             "function_declaration", "class_declaration", "abstract_class_declaration",
                             "class"})


def _returns(node) -> dict:
    """{"returns": the class a `(): ProjectApi` annotation names}, or {} -- so a call on
    this function's result (`getApi().approve()`) can be typed."""
    ann = _field(node, "return_type") if node is not None else None
    declared = _type_name(_text(ann)) if ann is not None else ""
    return {"returns": declared} if declared else {}


def _member_object(call):
    """The node a member call is made on (`x` in `x.m()`), or None."""
    fn = _field(call, "function")
    if fn is not None and fn.type == "await_expression" and fn.named_children:
        fn = fn.named_children[0]
    return _field(fn, "object") if fn is not None and fn.type == "member_expression" else None


def _call_via(obj, types: dict, self_type: str) -> dict | None:
    """`via` for a call made on another call's result -- `getApi().approve()` -- in
    langs_extract's shape: the innermost call's receiver type and the calls outward."""
    if obj is None or obj.type != "call_expression":
        return None
    ident, prop, _ = _callee_parts(obj)
    if ident:
        return {"type": "", "names": [ident]}
    if not prop:
        return {"type": "?", "names": []}
    deeper = _call_via(_member_object(obj), types, self_type)
    if deeper is not None:
        return {"type": deeper["type"], "names": deeper["names"] + [prop]}
    return {"type": _receiver_type(obj, types, self_type), "names": [prop]}


def _unwrap(node):
    """The expression inside `( )`, `await`, `x as T` and `x!`."""
    while node is not None and node.type in ("parenthesized_expression", "await_expression", "as_expression",
                                             "non_null_expression", "satisfies_expression") \
            and node.named_children:
        node = node.named_children[0]
    return node


def _alias_leaves(value) -> list[str]:
    """The names a `const` can hold, when the source writes them: `a`, `c ? a : b`, `a || b`, `a ?? b`."""
    value = _unwrap(value)
    if value is None:
        return []
    if value.type == "identifier":
        return [_text(value)]
    if value.type == "ternary_expression":
        return _alias_leaves(_field(value, "consequence")) + _alias_leaves(_field(value, "alternative"))
    op = _field(value, "operator") if value.type == "binary_expression" else None
    if op is not None and op.type in ("||", "??"):
        return _alias_leaves(_field(value, "left")) + _alias_leaves(_field(value, "right"))
    return []


def _scope_bindings(root) -> tuple[dict, dict, set, dict]:
    """What one function's own declarations say about the names used in it.

    `aliases`:  `const save = id ? updateUser : createUser` -> {"save": ["updateUser", "createUser"]}
    `results`:  `const api = useSetdatApi()`                -> {"api": "useSetdatApi"}
    `declared`: every name a parameter or declaration binds -- a local, never a function to link to.
    `picked`:   `const { api, ng: svc } = useSetdatVariant()` -> {"api": ("useSetdatVariant", "api"),
                "svc": ("useSetdatVariant", "ng")}
    Nested functions are walked too, as `_scope_types` walks them.
    """
    aliases: dict[str, list[str]] = {}
    results: dict[str, str] = {}
    declared: set[str] = set()
    picked: dict[str, tuple[str, str]] = {}

    def walk(n) -> None:
        if n.type == "variable_declarator":
            name, value = _field(n, "name"), _field(n, "value")
            kind = _field(n.parent, "kind") if n.parent is not None else None
            inner = _unwrap(value) if kind is not None and kind.type == "const" else None
            callee = _callee_parts(inner)[0] if inner is not None and inner.type == "call_expression" else ""
            if name is not None and name.type == "identifier":
                declared.add(_text(name))
                if inner is not None:
                    leaves = _alias_leaves(inner)
                    if leaves:
                        aliases[_text(name)] = leaves
                    elif callee:
                        results[_text(name)] = callee
            elif name is not None and name.type == "object_pattern" and callee:
                for child in name.named_children:
                    if child.type == "shorthand_property_identifier_pattern":
                        picked[_text(child)] = (callee, _text(child))
                    elif child.type == "pair_pattern":
                        key, local = _field(child, "key"), _field(child, "value")
                        if key is not None and key.type == "property_identifier" \
                                and local is not None and local.type == "identifier":
                            picked[_text(local)] = (callee, _text(key))
        elif n.type == "shorthand_property_identifier_pattern":
            declared.add(_text(n))
        elif n.type in ("object_pattern", "array_pattern", "pair_pattern", "rest_pattern",
                        "assignment_pattern", "object_assignment_pattern"):
            # `{ onDone: cb }` binds `cb`; `{ fmt = formatDate }` binds `fmt`, never its default.
            targets = ([_field(n, "value")] if n.type == "pair_pattern"
                       else [_field(n, "left")] if n.type in ("assignment_pattern", "object_assignment_pattern")
                       else n.named_children)
            for child in targets:
                if child is not None and child.type == "identifier":
                    declared.add(_text(child))
        elif n.type in ("required_parameter", "optional_parameter"):
            pattern = _field(n, "pattern")
            if pattern is not None and pattern.type == "identifier":
                declared.add(_text(pattern))
        elif n.type == "arrow_function":
            param = _field(n, "parameter")                # `x => ...`
            if param is not None and param.type == "identifier":
                declared.add(_text(param))
        for child in n.named_children:
            walk(child)

    if root is not None:
        walk(root)
        # `root` is usually a body; the function's own parameters (`{ userId, onDone }`) sit
        # beside it, and are locals just the same.
        owner = root.parent
        if owner is not None and owner.type in _FUNCTION_NODES:
            for field in ("parameters", "parameter"):
                params = _field(owner, field)
                if params is not None and params.type == "identifier":
                    declared.add(_text(params))
                elif params is not None:
                    walk(params)
    return aliases, results, declared, picked


def _collect_calls(root, axios_names: set, types: dict | None = None,
                   self_type: str = "", load_time: bool = False,
                   class_consts: dict | None = None) -> dict:
    """Called names and HTTP calls in a subtree, in source order.

    Each call carries the class of its receiver (`type`): "" for a bare call, the
    class where the source states it, "?" where it does not. That is the shape
    `langs_extract` already emits, so `build_flow` resolves JS/TS exactly as it
    resolves Java/Go/C#. Before this the receiver was discarded and only the name
    survived, which is why no call could ever land on a JS/TS class method.

    Order matters: `calls` feeds the graph's edges, and Babel's object-key walk
    visited a call's callee before its arguments. tree-sitter's children are in
    that same order, so `getOrder(x).then(y)` still yields `then` before
    `getOrder` -- the outer call first, then what it was called on.

    A call made twice is one entry, carrying where it is written (`call_ctx.site`, folded
    across its sites by `call_ctx.merge`: first line, a loop if any site is in one, a
    branch only if every site is).
    """
    types = types or {}
    calls: list[dict] = []
    seen: dict = {}
    http: list[dict] = []
    constructs: list[str] = []      # `new ApiError(...)`: a use of the class, not a call
    # `rows.map(formatDate)`, `onClick={run}`, `t.rich(k, { b: tag })`: handed over, not called here.
    passes: list[str] = []
    aliases, results, declared, picked = _scope_bindings(root)

    def held(name: str) -> list[str]:
        """What a name stands for: the functions or objects a local `const` holds, else itself."""
        if name not in aliases:
            return [name]
        return [leaf for leaf in aliases[name] if leaf not in declared] or [name]

    def passed(value) -> None:
        value = _unwrap(value)
        if value is None:
            return
        if value.type in ("identifier", "shorthand_property_identifier"):
            name = _text(value)
            for leaf in (held(name) if name in aliases else ([] if name in declared else [name])):
                if leaf not in passes and leaf not in declared:
                    passes.append(leaf)
        elif value.type == "object":
            for child in value.named_children:
                passed(_field(child, "value") if child.type == "pair" else child)

    def add(at, recv: str, name: str, obj: str = "", via: dict | None = None) -> None:
        key = (recv, name, (via["type"], tuple(via["names"]), via.get("field", "")) if via else ())
        if name and key in seen:
            call_ctx.merge(seen[key], call_ctx.site(at, root))
        elif name:
            call = {"type": recv, "name": name, **call_ctx.site(at, root)}
            seen[key] = call
            if recv and obj and re.fullmatch(r"[A-Za-z_$][\w$]*", obj):
                # Untyped: maybe a namespace import (`errors.toMessage()`). Typed: the instance
                # an import binds, which settles a class name two files define.
                call["obj"] = obj
            if via:
                call["via"] = via       # a call on a call's result: typed from return types
            calls.append(call)

    def walk(node) -> None:
        if node.type == "call_expression":
            ident, prop, obj = _callee_parts(node)
            args = _args(node)
            if ident:
                for name in held(ident):        # `save(x)` where `const save = id ? update : create`
                    add(node, "", name)
                if ident in ("fetch", "$fetch"):
                    http.append({"method": _method_from_options(args[1] if len(args) > 1 else None, class_consts),
                                 "url": _url_of(args[0] if args else None, class_consts)})
                elif _is_http_client(ident, axios_names):
                    if args and args[0].type == "object":
                        m, u = _from_config_object(args[0], class_consts)
                        if u:
                            http.append({"method": m, "url": u})
                    elif args:
                        http.append({"method": _method_from_options(args[1] if len(args) > 1 else None, class_consts),
                                     "url": _url_of(args[0], class_consts)})
            elif prop:
                if obj in aliases and obj not in types:
                    for leaf in held(obj):      # `const api = ng ? ngApi : setdatApi; api.fetch()`
                        add(node, "?", prop, leaf)
                elif obj in results and obj not in types:
                    # `const api = useSetdatApi(); api.fetch()`: typed by what that function returns.
                    add(node, "?", prop, obj, {"type": "", "names": [results[obj]]})
                elif obj in picked and obj not in types:
                    # `const { api } = useSetdatVariant(); api.fetch()`: typed by that result's field.
                    callee, field = picked[obj]
                    add(node, "?", prop, obj, {"type": "", "names": [callee], "field": field})
                else:
                    add(node, _receiver_type(node, types, self_type), prop, obj,
                        _call_via(_member_object(node), types, self_type))
                if prop == "fetch" and obj in ("window", "globalThis"):
                    http.append({"method": _method_from_options(args[1] if len(args) > 1 else None, class_consts),
                                 "url": _url_of(args[0] if args else None, class_consts)})
                elif _is_http_client(obj, axios_names):
                    if prop in HTTP_VERBS:
                        http.append({"method": prop.upper(),
                                     "url": _url_of(args[0] if args else None, class_consts)})
                    elif prop == "request" and args and args[0].type == "object":
                        m, u = _from_config_object(args[0], class_consts)
                        if u:
                            http.append({"method": m, "url": u})
            for a in args:
                passed(a)
        elif node.type == "new_expression":
            name = _new_type(node)
            if name and name not in constructs:
                constructs.append(name)
            for a in _args(node):
                passed(a)
        elif node.type == "jsx_expression" and node.parent is not None and node.parent.type == "jsx_attribute":
            passed(node.named_children[0] if node.named_children else None)
        for child in node.children:
            # `load_time`: only what runs when the module loads, never a function body.
            if child.type != "comment" and not (load_time and child.type in _FUNCTION_NODES):
                walk(child)

    if root is not None:
        walk(root)
    out = {"calls": calls, "http": http}
    if constructs:
        out["constructs"] = constructs
    if passes:
        out["passes"] = passes
    return out


def _returned_members(fn) -> dict:
    """{"returns_members": [...]} when every `return` of a function hands back one object literal
    whose members name functions under their own names -- `return { fetchList, fetchOne }`, a
    local `const value = { ... }`, or `useMemo(() => ({ ... }), deps)` -- so `const api = f();
    api.fetchList()` reaches the function it names. Anything else returns {}."""
    objects, returned = _return_values(fn)
    shapes = []
    for r in returned:
        r = _unwrap(r)
        if r is not None and r.type == "identifier":
            r = _unwrap(objects.get(_text(r)))
        if r is not None and r.type == "call_expression" and _callee_parts(r)[0] == "useMemo":
            args = _args(r)
            r = _unwrap(_field(args[0], "body")) if args and args[0].type == "arrow_function" else None
        if r is None or r.type != "object":
            return {}
        shapes.append(sorted(k for k, v in _object_entry("", r, set(), {})["aliases"].items() if k == v))
    if not shapes or not shapes[0] or any(s != shapes[0] for s in shapes):
        return {}
    return {"returns_members": shapes[0]}


def _return_values(fn) -> tuple[dict, list]:
    """(the values a function's own locals are declared with, the expressions it returns).
    Nested functions are not entered: a callback's `return` is not this function's."""
    body = _field(fn, "body") if fn is not None else None
    local: dict = {}
    returned: list = []
    if body is None:
        return local, returned
    if body.type != "statement_block":
        return local, [body]                                 # `() => ({ ... })`

    def walk(n) -> None:
        if n.type in _FUNCTION_NODES:
            return
        if n.type == "variable_declarator":
            name = _field(n, "name")
            if name is not None and name.type == "identifier":
                local[_text(name)] = _field(n, "value")
        elif n.type == "return_statement":
            returned.append(n.named_children[0] if n.named_children else None)
        for child in n.named_children:
            walk(child)

    for child in body.named_children:
        walk(child)
    return local, returned


# --- types a member call can follow ---------------------------------------------
# `const { api } = useSetdatVariant(); api.fetchX()`: nothing about `api` is written in the
# component, but every step is written somewhere -- the hook's return type (or the
# `createContext<T>` it reads), `interface T { api: SetdatApi }`, `type SetdatApi = typeof
# setdatService`. Only those shapes: a type reference is a name or `typeof <name>`, and
# anything else (a generic, an intersection, a mapped type) stays unread.

def _union_members(node) -> list:
    return [m for c in node.named_children for m in (_union_members(c) if c.type == "union_type" else [c])]


def _type_ref(node) -> str:
    """`typeof svc` -> "typeof svc"; `V`, `V | null`, `V | undefined` -> "V"; anything else -> ""."""
    if node is not None and node.type == "type_annotation" and node.named_children:
        node = node.named_children[0]
    if node is not None and node.type == "union_type":
        rest = [m for m in _union_members(node) if _text(m) not in ("null", "undefined")]
        node = rest[0] if len(rest) == 1 else None
    if node is None:
        return ""
    if node.type == "type_query" and node.named_children and node.named_children[0].type == "identifier":
        return "typeof " + _text(node.named_children[0])
    return _text(node) if node.type == "type_identifier" else ""


def _type_entry(node) -> dict:
    """`interface V { api: SetdatApi }` / `type V = { api: typeof svc }` -> {"props": {...}};
    `type SetdatApi = typeof setdatService` -> {"is": "typeof setdatService"}; else {}."""
    body = _field(node, "body") if node.type == "interface_declaration" else _field(node, "value")
    if body is None:
        return {}
    if body.type in ("interface_body", "object_type"):
        props = {}
        for p in _named(body, "property_signature"):
            key, ref = _field(p, "name"), _type_ref(_field(p, "type"))
            if key is not None and ref:
                props[_text(key)] = ref
        return {"props": props} if props else {}
    ref = _type_ref(body)
    return {"is": ref} if ref else {}


def _context_type(value) -> str:
    """`createContext<V | null>(null)` -> "V": what every `useContext` of it returns."""
    value = _unwrap(value)
    if value is None or value.type != "call_expression" or "createContext" not in _callee_parts(value)[:2]:
        return ""
    targs = _field(value, "type_arguments")
    return _type_ref(targs.named_children[0]) if targs is not None and len(targs.named_children) == 1 else ""


def _returned_type(fn) -> dict:
    """What a function's result is, for a member lookup on it: {"returns_type": "V"} from a
    `(): V` annotation, or {"returns_context": "Ctx"} when every `return` hands back
    `useContext(Ctx)` -- directly, or through `const ctx = useContext(Ctx); ...; return ctx`."""
    ann = _field(fn, "return_type") if fn is not None else None
    if ann is not None:
        ref = _type_ref(ann)
        return {"returns_type": ref} if ref else {}
    local, returned = _return_values(fn)
    names = set()
    for r in returned:
        r = _unwrap(r)
        if r is not None and r.type == "identifier":
            r = _unwrap(local.get(_text(r)))
        args = _args(r) if r is not None and r.type == "call_expression" \
            and "useContext" in _callee_parts(r)[:2] else []
        if len(args) != 1 or args[0].type != "identifier":
            return {}
        names.add(_text(args[0]))
    return {"returns_context": names.pop()} if len(names) == 1 else {}


_COMPONENT_WRAPPERS = frozenset({"forwardRef", "memo"})


def _wrapped_function(call):
    """What `forwardRef((props, ref) => ...)`, `memo(Button)` or `React.memo(forwardRef(...))`
    wraps -- the function, or the name -- else None. The wrapper returns that component, so
    `const Button = forwardRef(...)` is a component named Button."""
    while call is not None and call.type == "call_expression":
        ident, prop, _ = _callee_parts(call)
        if (ident or prop) not in _COMPONENT_WRAPPERS:
            return None
        args = _args(call)
        call = _unwrap(args[0]) if args else None
    return call if call is not None and call.type in _FUNCTIONS + ("identifier",) else None


def _collect_jsx(root) -> dict:
    """`jsx` (is this a React component) and the components it renders.

    A tag starting with a capital letter names another component; lowercase tags
    are host elements (`div`, `span`) and say nothing about structure.
    """
    found = {"jsx": False}
    components: set = set()

    def walk(node) -> None:
        if node.type in ("jsx_element", "jsx_fragment", "jsx_self_closing_element"):
            found["jsx"] = True
            opening = node if node.type == "jsx_self_closing_element" else (
                node.child(0) if node.child_count else None)
            name_node = _field(opening, "name") if opening is not None else None
            if name_node is not None:
                name = _text(name_node)
                if name.startswith(("<", ">")):
                    name = ""
                if "." in name:
                    # `<Ctx.Provider>` / `<Form.Item>`: the last segment names a member of
                    # an object, not a component of that name -- an edge would be a guess.
                    name = ""
                if name[:1].isupper():
                    components.add(name)
        for child in node.children:
            if child.type != "comment":
                walk(child)

    if root is not None:
        walk(root)
    return {"jsx": found["jsx"], "components": sorted(components)}


# --- routes -------------------------------------------------------------------

def _decorator_info(dec) -> dict:
    """`@Get(":id")` -> {"name": "get", "arg": ":id"}; `@Injectable` -> name only."""
    inner = dec.named_children[0] if dec.named_children else None
    if inner is None:
        return {"name": "", "arg": ""}
    if inner.type == "call_expression":
        _, prop, _obj = _callee_parts(inner)
        fn = _field(inner, "function")
        name = _text(fn) if fn is not None and fn.type == "identifier" else prop
        args = _args(inner)
        return {"name": (name or "").lower(), "arg": _url_of(args[0] if args else None)}
    return {"name": _text(inner).lower(), "arg": ""}


def _join_path(prefix: str, suffix: str) -> str:
    parts = [str(p).strip("/") for p in (prefix, suffix) if p]
    return "/" + "/".join(p for p in parts if p)


def _nest_routes(class_decorators, method_decorators) -> list[dict]:
    """`@Controller('orders')` gives the prefix, `@Get(':id')` verb and suffix."""
    prefix = ""
    for dec in class_decorators:
        info = _decorator_info(dec)
        if info["name"] == "controller":
            prefix = info["arg"]
    routes = []
    for dec in method_decorators:
        info = _decorator_info(dec)
        if info["name"] in HTTP_VERBS:
            routes.append({"method": info["name"].upper(),
                           "path": _join_path(prefix, info["arg"])})
    return routes


def _express_routes(program, axios_names: set) -> list[dict]:
    """`router.post("/orders", handler)`, named handler or inline arrow.

    Only a top-level `expression_statement` counts, so a `.get()` buried in
    application logic is never mistaken for a route registration.
    """
    routes = []
    for raw in program.named_children:
        if raw.type != "expression_statement":
            continue
        call = raw.named_children[0] if raw.named_children else None
        if call is None or call.type != "call_expression":
            continue
        _ident, prop, _obj = _callee_parts(call)
        verb = (prop or "").lower()
        if verb not in HTTP_VERBS:
            continue
        args = _args(call)
        route_path = _url_of(args[0] if args else None)
        if not route_path.startswith("/"):   # a path, not a URL fetched from somewhere
            continue
        handler = args[-1] if args else None
        if handler is None:
            continue
        entry = {"method": verb.upper(), "path": route_path,
                 "line": _line(raw), "endLine": raw.end_point[0] + 1,
                 "doc": _doc_above(raw)}
        if handler.type == "identifier":
            entry["handler"] = _text(handler)         # attaches to that function's node
        elif handler.type in ("arrow_function", "function_expression", "function"):
            entry.update(_collect_calls(_field(handler, "body"), axios_names,
                                        _scope_types(handler)))
        else:
            continue
        routes.append(entry)
    return routes


# --- declarations -------------------------------------------------------------

def _unwrap_export(node):
    """`export class X {}` -> the class; a bare `export {x}` stays itself."""
    if node.type == "export_statement":
        return _field(node, "declaration") or node
    return node


def _class_entry(node, raw, axios_names: set, module_types: dict | None = None) -> dict:
    decorators = _decorators_of(node) + _decorators_of(raw) if raw is not node else _decorators_of(node)
    name = _field(node, "name")
    heritage = _named(node, "class_heritage")
    bases = []
    if heritage:
        for child in heritage[0].named_children:
            target = _field(child, "value") if child.type == "extends_clause" else child
            if target is not None and target.type in ("identifier", "type_identifier"):
                bases.append(_text(target))
            elif child.type in ("identifier", "type_identifier"):
                bases.append(_text(child))
    body = _field(node, "body")
    cls_name = _text(name) if name is not None else ""
    fields = _field_types(body)          # `this.<x>` -> class, for every method below
    consts = _field_consts(body)         # `this.<x>` -> string const
    methods = []
    for member in _named(body, "method_definition") if body is not None else []:
        key = _field(member, "name")
        if key is None:
            continue
        member_decs = _decorators_of(member)
        methods.append({
            "name": _text(key), "doc": _doc_for(member, member_decs),
            "line": _start_line(member, member_decs), "endLine": member.end_point[0] + 1,
            "routes": _nest_routes(decorators, member_decs),
            **_collect_calls(_field(member, "body"), axios_names,
                             {**(module_types or {}), **fields, **_scope_types(member)}, cls_name,
                             class_consts=consts),
            **_returns(member),
        })
    return {
        "name": _text(name) if name is not None else "",
        # `abstract class Base {}` is its own node type in TypeScript, and was not read at all.
        **({"kind": "abstract"} if node.type == "abstract_class_declaration" else {}),
        "bases": bases,
        "decorators": [d for d in (_decorator_info(x)["name"] for x in decorators) if d],
        "doc": _doc_for(raw, decorators),
        "line": _start_line(node, decorators),
        "endLine": node.end_point[0] + 1,
        "methods": methods,
    }


def _import_entry(node) -> dict:
    source = _field(node, "source")
    names = []
    bindings = []           # [local name, what it binds: "default" | "*" | an exported name]
    for clause in _named(node, "import_clause"):
        for child in clause.named_children:
            if child.type == "identifier":                       # default import
                names.append(_text(child))
                bindings.append([_text(child), "default"])
            elif child.type == "namespace_import":
                ident = child.named_children[-1] if child.named_children else None
                if ident is not None:
                    names.append(_text(ident))
                    bindings.append([_text(ident), "*"])
            elif child.type == "named_imports":
                for spec in _named(child, "import_specifier"):
                    imported, alias = _field(spec, "name"), _field(spec, "alias")
                    if imported is not None:
                        names.append(_text(imported))
                        bindings.append([_text(alias if alias is not None else imported), _text(imported)])
    return {"from": _url_of(source), "names": names, "bindings": bindings}


def _extract_tree(root, axios_names: set, module_types: dict | None = None) -> dict:
    global _FILE_CONSTS
    _FILE_CONSTS = _string_consts(root)
    # Module-level instances (`const api = new ProjectApi()`, this file's or imported)
    # type a receiver in every function here, under what the function states itself.
    mt = module_types or {}
    out = {"classes": [], "functions": [], "imports": [],
           "routes": _express_routes(root, axios_names),
           # Read by `_finish`, which knows the path, then removed from the output.
           "exports": {"names": set(), "default": None},
           # Calls made by top-level code as the module loads (`const api = createApi()`).
           "module_calls": [],
           # Functions top-level code hands to a call (`createApiInstance(getUserApiBaseUrl)`).
           "module_passes": [],
           # `export * from "./project"` and friends, followed by build_flow's imports.
           "reexports": [],
           # `export const api = { approve: async () => ... }`: its members are flow nodes.
           "objects": [],
           # `interface V { api: SetdatApi }`, `type SetdatApi = typeof svc`: followed by a member call.
           "types": {},
           # `const Ctx = createContext<V | null>(null)` -> {"Ctx": "V"}.
           "contexts": {}}

    for raw in root.named_children:
        node = _unwrap_export(raw)
        if node is None:
            continue
        exported = raw.type == "export_statement"
        default = exported and any(c.type == "default" for c in raw.children)

        if node.type == "import_statement":
            out["imports"].append(_import_entry(node))

        elif node.type in ("class_declaration", "abstract_class_declaration"):
            out["classes"].append(_class_entry(node, raw, axios_names, mt))

        elif node.type == "export_statement" and _field(node, "source") is not None:
            out["reexports"].append(_reexport_entry(node))

        elif node.type == "export_statement" and default:
            # `export default function () {}` / `export default () => ...` has no name
            # to be a node under, so its whole body used to be invisible: a Next.js
            # page written this way had no node and none of its calls.
            # `export default Dashboard` only says which function is the default.
            value = next((c for c in node.named_children if c.type in
                          ("function_expression", "arrow_function", "function", "identifier", "object",
                           "call_expression")), None)
            if value is not None and value.type == "call_expression":
                value = _wrapped_function(value)            # `export default memo(Button)`
            if value is None:
                continue
            if value.type == "identifier":
                out["exports"]["default"] = _text(value)
                continue
            if value.type == "object":                  # `export default { ... }`: named by its file
                out["objects"].append(_object_entry("", value, axios_names, mt))
                continue
            body = _field(value, "body")
            out["exports"]["default"] = ""
            out["functions"].append({
                "name": "", "doc": _doc_above(raw),
                "line": _line(raw), "endLine": raw.end_point[0] + 1, **_returns(value),
                **_returned_members(value), **_returned_type(value),
                **_collect_calls(body, axios_names, {**mt, **_scope_types(value)}), **_collect_jsx(body),
            })

        elif node.type in ("interface_declaration", "type_alias_declaration"):
            name, entry = _field(node, "name"), _type_entry(node)
            if name is not None and entry:
                out["types"][_text(name)] = entry

        elif node.type == "function_declaration":
            name = _field(node, "name")
            if name is None:
                continue
            if exported:
                out["exports"]["names"].add(_text(name))
            if default:
                out["exports"]["default"] = _text(name)
            body = _field(node, "body")
            out["functions"].append({
                "name": _text(name), "doc": _doc_above(raw),
                "line": _line(node), "endLine": node.end_point[0] + 1, **_returns(node),
                **_returned_members(node), **_returned_type(node),
                **_collect_calls(body, axios_names, {**mt, **_scope_types(node)}), **_collect_jsx(body),
            })

        elif node.type == "expression_statement":
            got = _collect_calls(node, axios_names, mt, load_time=True)
            out["module_calls"] += got["calls"]
            out["module_passes"] += got.get("passes", [])

        elif node.type in ("lexical_declaration", "variable_declaration"):
            for dec in _named(node, "variable_declarator"):
                name, value = _field(dec, "name"), _field(dec, "value")
                if value is not None and value.type not in _FUNCTION_NODES:
                    got = _collect_calls(value, axios_names, mt, load_time=True)
                    out["module_calls"] += got["calls"]
                    out["module_passes"] += got.get("passes", [])
                if name is None or name.type != "identifier" or value is None:
                    continue
                context = _context_type(value)
                if context:
                    out["contexts"][_text(name)] = context
                if value.type == "call_expression":
                    # `const Button = forwardRef((props, ref) => ...)`: the wrapped function is the component.
                    value = _wrapped_function(value) or value
                if value.type == "object":
                    out["objects"].append(_object_entry(_text(name), value, axios_names, mt))
                    continue
                if value.type not in ("arrow_function", "function_expression", "function"):
                    continue
                if exported:
                    out["exports"]["names"].add(_text(name))
                body = _field(value, "body")
                out["functions"].append({
                    "name": _text(name), "doc": _doc_above(raw),
                    "line": _line(dec), "endLine": dec.end_point[0] + 1, **_returns(value),
                    **_returned_members(value), **_returned_type(value),
                    **_collect_calls(body, axios_names, {**mt, **_scope_types(value)}), **_collect_jsx(body),
                })
    return out


def _reexport_entry(node) -> dict:
    """`export * from "./x"` -> star; `export * as api from "./x"` -> namespace `api`;
    `export { a, b as c } from "./x"` -> names {exported: original}."""
    entry = {"from": _url_of(_field(node, "source")), "names": {}}
    ns = next((c for c in node.named_children if c.type == "namespace_export"), None)
    if ns is not None:
        ident = ns.named_children[-1] if ns.named_children else None
        entry["namespace"] = _text(ident) if ident is not None else ""
    for clause in _named(node, "export_clause"):
        for spec in _named(clause, "export_specifier"):
            name, alias = _field(spec, "name"), _field(spec, "alias")
            if name is not None:
                entry["names"][_text(alias if alias is not None else name)] = _text(name)
    if ns is None and not entry["names"]:
        entry["star"] = True
    return entry


def _object_consts(obj) -> dict[str, str]:
    """`key -> string value` for string properties in an object literal."""
    consts: dict[str, str] = {}
    if obj is None:
        return consts
    for child in obj.named_children:
        if child.type == "pair":
            key, val = _field(child, "key"), _field(child, "value")
            if key is not None and val is not None and val.type == "string":
                consts[_text(key).strip("\"'")] = _url_of(val)
    return consts


def _object_entry(name: str, obj, axios_names: set, module_types: dict) -> dict:
    """`export const api = { approve: async () => ..., reject() {}, archive }`.

    An inline member is a function of its own -- a flow node `api.approve`, with its calls
    and HTTP calls, which were invisible while the object was only module-load code. A
    member that just names a function (`archive`, `archive: archive`) is an alias for it.
    """
    members, aliases = [], {}
    consts = _object_consts(obj)
    for child in obj.named_children:
        key, fn = None, None
        if child.type == "pair":
            key, value = _field(child, "key"), _field(child, "value")
            if value is not None and value.type in ("arrow_function", "function_expression", "function"):
                fn = value
            elif value is not None and value.type == "identifier" and key is not None:
                aliases[_text(key)] = _text(value)
                continue
        elif child.type == "method_definition":
            key, fn = _field(child, "name"), child
        elif child.type == "shorthand_property_identifier":
            aliases[_text(child)] = _text(child)
            continue
        if key is None or fn is None or key.type not in ("property_identifier", "identifier"):
            continue
        body = _field(fn, "body")
        members.append({
            "name": _text(key), "doc": _doc_above(child),
            "line": _line(child), "endLine": child.end_point[0] + 1, **_returns(fn),
            **_collect_calls(body, axios_names, {**module_types, **_scope_types(fn)},
                             class_consts=consts),
        })
    return {"name": name, "members": members, "aliases": aliases}


def _module_instances(program) -> dict:
    """Module-level `const api = new ProjectApi()` (or `const api: ProjectApi = ...`) ->
    {"api": "ProjectApi"}; `export default new ProjectApi()` -> {"default": "ProjectApi"}."""
    out = {}
    for raw in program.named_children:
        node = _unwrap_export(raw)
        if node is None:
            continue
        if raw.type == "export_statement" and _field(raw, "declaration") is None:
            cls = _new_type(_field(raw, "value"))
            if cls:
                out["default"] = cls
        elif node.type in ("lexical_declaration", "variable_declaration"):
            for dec in _named(node, "variable_declarator"):
                name = _field(dec, "name")
                cls = _annotation(dec) or _new_type(_field(dec, "value"))
                if name is not None and name.type == "identifier" and cls:
                    out[_text(name)] = cls
    return out


def _imported_types(program, path: str, instances: dict, keys: set) -> dict:
    """Local name -> class for an imported instance: `import { projectApi } from "@/lib/projectApi"`
    where that file declares `export const projectApi = new ProjectApi()`."""
    out = {}
    for raw in program.named_children:
        if raw.type != "import_statement":
            continue
        spec = _url_of(_field(raw, "source"))
        inst = instances.get(_resolve_import(spec, path, keys)) if spec else None
        if not inst:
            continue
        for clause in _named(raw, "import_clause"):
            for child in clause.named_children:
                if child.type == "identifier" and "default" in inst:
                    out[_text(child)] = inst["default"]
                elif child.type == "named_imports":
                    for s in _named(child, "import_specifier"):
                        name, alias = _field(s, "name"), _field(s, "alias")
                        if name is not None and _text(name) in inst:
                            out[_text(alias if alias is not None else name)] = inst[_text(name)]
    return out


def _exported_instances(program, local: set) -> dict:
    """The axios instances this module exports: {"default": bool, "names": set}.

    Covers `export default api`, `export default axios.create(...)`,
    `export const api = axios.create(...)` and `export { api as client }`.
    """
    out = {"default": False, "names": set()}
    for raw in program.named_children:
        if raw.type != "export_statement":
            continue
        value, decl = _field(raw, "value"), _field(raw, "declaration")
        if value is not None:
            if (value.type == "identifier" and _text(value) in local) or \
                    (value.type == "call_expression" and _callee_parts(value)[1:] == ("create", "axios")):
                out["default"] = True
        elif decl is not None:
            for dec in _named(decl, "variable_declarator"):
                name = _field(dec, "name")
                if name is not None and _text(name) in local:
                    out["names"].add(_text(name))
        for clause in _named(raw, "export_clause"):
            for spec in _named(clause, "export_specifier"):
                name, alias = _field(spec, "name"), _field(spec, "alias")
                if name is None or _text(name) not in local:
                    continue
                exported = _text(alias if alias is not None else name)
                if exported == "default":
                    out["default"] = True
                else:
                    out["names"].add(exported)
    return out


def _loose_json(text: str):
    """tsconfig.json / jsconfig.json are JSON with comments and trailing commas."""
    text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',
                  lambda m: m.group(0) if m.group(0).startswith('"') else "", text, flags=re.S)
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def _paths_of(config: str, depth: int = 0) -> tuple:
    """A config's `paths` as ((pattern, (absolute target, ...)), ...), following a
    relative `extends` when the file itself declares none."""
    try:
        with open(config, "r", encoding="utf-8") as fh:
            data = _loose_json(fh.read())
        opts = data.get("compilerOptions") or {}
    except (OSError, ValueError, AttributeError):
        return ()
    here = os.path.dirname(config)
    paths = opts.get("paths")
    if isinstance(paths, dict):
        base = os.path.join(here, opts.get("baseUrl") or ".")
        return tuple((pattern, tuple(os.path.normpath(os.path.join(base, t)).replace("\\", "/")
                                     for t in targets if isinstance(t, str)))
                     for pattern, targets in sorted(paths.items()) if isinstance(targets, list))
    parent = data.get("extends")
    if isinstance(parent, str) and parent.startswith(".") and depth < 5:
        parent = os.path.normpath(os.path.join(here, parent))
        return _paths_of(parent if parent.endswith(".json") else parent + ".json", depth + 1)
    return ()


@functools.lru_cache(maxsize=None)
def _ts_paths(directory: str) -> tuple:
    """`paths` of the nearest tsconfig.json / jsconfig.json at or above `directory`."""
    for name in ("tsconfig.json", "jsconfig.json"):
        config = os.path.join(directory, name)
        if os.path.isfile(config):
            return _paths_of(config)
    parent = os.path.dirname(directory)
    return () if parent == directory else _ts_paths(parent)


def alias_targets(spec: str, importer: str) -> list[str]:
    """Where a tsconfig/jsconfig `paths` alias sends `spec` (`@/utils/x` -> `<root>/src/utils/x`):
    extension-less forward-slash paths, absolute if `importer` is. [] when no alias matches."""
    out = []
    for pattern, targets in _ts_paths(os.path.dirname(os.path.abspath(importer))):
        head, star, tail = pattern.partition("*")
        if star:
            if not (spec.startswith(head) and spec.endswith(tail) and len(spec) >= len(head) + len(tail)):
                continue
            rest = spec[len(head):len(spec) - len(tail)]
        elif spec != pattern:
            continue
        else:
            rest = ""
        out += [t.replace("*", rest) for t in targets]
    if not os.path.isabs(importer):
        out = [os.path.relpath(t).replace("\\", "/") for t in out]
    return out


def _module_key(path: str) -> str:
    """A file as an import specifier would name it: no extension, `/index` dropped."""
    key = os.path.splitext(path)[0].replace("\\", "/")
    return key[: -len("/index")] if key.endswith("/index") else key


def _resolve_import(spec: str, importer: str, keys: set) -> str | None:
    """The one module key an import specifier names, or None -- never a guess.

    Relative specifiers resolve exactly, and so does an alias the nearest
    tsconfig/jsconfig `paths` declares. Anything else is matched as a path suffix
    after a bare alias segment (`@/`, `~/`, `#/`): `@/services/api` is the file
    ending in `/services/api`, if exactly one does.
    """
    if spec.startswith("."):
        base = posixpath.dirname(importer.replace("\\", "/"))
        key = posixpath.normpath(posixpath.join(base, spec))
        return key if key in keys else None
    for target in alias_targets(spec, importer):
        key = target[: -len("/index")] if target.endswith("/index") else target
        if key in keys:
            return key
    head, _, rest = spec.partition("/")
    tail = "/" + (rest if head in ("@", "~", "#") and rest else spec)
    hits = [k for k in keys if k.endswith(tail)]
    if len(hits) > 1:
        # Two apps in one repository each with `@/services/x`: an alias is the importer's
        # own package's, so keep the files inside it -- the nearest package.json/tsconfig.
        home = _package_root(os.path.dirname(os.path.abspath(importer)))
        if home:
            home = home.replace("\\", "/").rstrip("/") + "/"
            hits = [k for k in hits if os.path.abspath(k).replace("\\", "/").startswith(home)]
    return hits[0] if len(hits) == 1 else None


@functools.lru_cache(maxsize=None)
def _package_root(directory: str) -> str:
    """The nearest folder at or above `directory` holding a package.json, tsconfig.json or
    jsconfig.json, or ""."""
    if any(os.path.isfile(os.path.join(directory, f))
           for f in ("package.json", "tsconfig.json", "jsconfig.json")):
        return directory
    parent = os.path.dirname(directory)
    return "" if parent == directory else _package_root(parent)


def _imported_instances(program, path: str, exporters: dict, keys: set) -> set:
    """Local names bound to an axios instance another file exports."""
    names: set = set()
    for raw in program.named_children:
        if raw.type != "import_statement":
            continue
        spec = _url_of(_field(raw, "source"))
        exp = exporters.get(_resolve_import(spec, path, keys)) if spec else None
        if not exp:
            continue
        for clause in _named(raw, "import_clause"):
            for child in clause.named_children:
                if child.type == "identifier" and exp["default"]:
                    names.add(_text(child))
                elif child.type == "named_imports":
                    for s in _named(child, "import_specifier"):
                        name, alias = _field(s, "name"), _field(s, "alias")
                        if name is not None and _text(name) in exp["names"]:
                            names.add(_text(alias if alias is not None else name))
    return names


def _parse(path: str):
    """The tree for one JS/TS file, or None (unknown extension, missing grammar, unreadable)."""
    ext = os.path.splitext(path)[1].lower()
    lang = LANG_BY_EXT.get(ext)
    if lang is None:
        return None
    parser = grammars.parser_for(lang)
    if parser is None:
        broken = grammars.runtime_error()
        if broken:
            _warn_once(f"  ! frontend skipped: {broken}")
        else:
            # Name every JS/TS wheel that is missing, not just this file's. Two
            # wheels cover four extensions, so hinting only the one that failed
            # first sends the user to fix half the problem and meet the same
            # warning again on the next build.
            _warn_once(f"  ! frontend skipped: no tree-sitter grammar installed. Run "
                       f"`{grammars.install_hint(set(LANG_BY_EXT.values()))}`"
                       f" to enable JS/TS parsing.")
        return None
    try:
        with open(path, "rb") as fh:
            src = fh.read()
    except OSError as exc:
        print(f"  ! skipped {path}: {exc}", file=sys.stderr)
        return None
    return parser.parse(src)


@functools.lru_cache(maxsize=None)
def _next_root(directory: str) -> str:
    """The Next.js app root holding `directory`, or "" outside a Next app.

    The nearest folder with a `next.config.*`; failing that, the nearest package.json
    decides -- it is the package boundary, so a `next` dependency there makes it the
    root and its absence means this is not a Next app.
    """
    if any(os.path.isfile(os.path.join(directory, f"next.config.{ext}"))
           for ext in ("js", "mjs", "cjs", "ts")):
        return directory
    pkg = os.path.join(directory, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        except (OSError, ValueError, AttributeError, TypeError):
            return ""
        return directory if "next" in deps else ""
    parent = os.path.dirname(directory)
    return "" if parent == directory else _next_root(parent)


def _finish(out: dict, path: str) -> dict:
    """What only a file's path decides: the name of an anonymous default export (its
    file stem, which is how everything imports it) and, inside a Next.js app, the
    convention under which the framework calls each exported function (`entry`)."""
    out["file"] = path
    exports = out.pop("exports")
    full = os.path.abspath(path)
    root = _next_root(os.path.dirname(full))
    rel = os.path.relpath(full, root).replace(os.sep, "/") if root else ""
    for obj in out["objects"]:
        if obj["name"] == "":                    # `export default { ... }`, imported by its file
            obj["name"] = os.path.splitext(os.path.basename(path))[0]
            out["default"] = obj["name"]
        elif exports["default"] and obj["name"] == exports["default"]:
            out["default"] = obj["name"]         # `const setdatApi = { ... }; export default setdatApi`
    for fn in out["functions"]:
        default = fn["name"] == "" or fn["name"] == exports["default"]
        if fn["name"] == "":
            fn["name"] = os.path.splitext(os.path.basename(path))[0]
        if default:
            out["default"] = fn["name"]      # what `import X from "<this file>"` binds
        if root and (default or fn["name"] in exports["names"]):
            why = next_entry(rel, fn["name"], default)
            if why:
                fn["entry"] = why
    return out


def extract_file(path: str, axios_names: set | None = None) -> dict | None:
    tree = _parse(path)
    if tree is None:
        return None
    own = _module_instances(tree.root_node)
    own.pop("default", None)
    return _finish(_extract_tree(tree.root_node, _axios_instances(tree.root_node) | (axios_names or set()),
                                 own), path)


def extract_js_files(files: list[str]) -> list[dict]:
    """The normalized per-file structure for `files` ([] when nothing parses).

    An axios instance is usually created once and imported everywhere
    (`services/api.ts` exports `axios.create(...)`), so every file is parsed before
    any is read: an import resolving to exactly one file that exports an instance
    binds that name too. Reading each file alone found 0 HTTP calls in a real
    Next.js frontend, and so no cross-stack edge at all.
    """
    parsed = [(p, t) for p in files for t in [_parse(p)] if t is not None]
    keys = {_module_key(p) for p, _ in parsed}
    by_key: dict[str, str] = {}
    for p in sorted(p for p, _ in parsed):
        by_key.setdefault(_module_key(p), p)
    exporters = {}
    for path, tree in parsed:
        exp = _exported_instances(tree.root_node, _axios_instances(tree.root_node) - {"axios"})
        if exp["default"] or exp["names"]:
            exporters[_module_key(path)] = exp
    instances = {}
    for path, tree in parsed:
        inst = _module_instances(tree.root_node)
        if inst:
            instances[_module_key(path)] = inst
    results = []
    for path, tree in parsed:
        names = _axios_instances(tree.root_node)
        if exporters:
            names |= _imported_instances(tree.root_node, path, exporters, keys)
        module_types = {**(_imported_types(tree.root_node, path, instances, keys) if instances else {}),
                        **instances.get(_module_key(path), {})}
        module_types.pop("default", None)             # a keyword, never a variable
        out = _finish(_extract_tree(tree.root_node, names, module_types), path)
        for imp in out["imports"] + out["reexports"]:
            # The file an import names, so build_flow can follow the binding.
            key = _resolve_import(imp["from"], path, keys) if imp.get("from") else None
            if key in by_key:
                imp["path"] = by_key[key]
        results.append(out)
    return results


if __name__ == "__main__":
    import json
    args = sys.argv[1:]
    root = args[0] if args else "."
    targets = sorted(find_js_files(os.path.abspath(root)))
    print(json.dumps(extract_js_files(targets), indent=2, sort_keys=True))
