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

import os
import posixpath
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import SKILL_ROOT  # noqa: E402  (also puts sibling script dirs on sys.path)

import grammars  # noqa: E402

JS_EXTS = (".js", ".jsx", ".ts", ".tsx")
from taxonomy import SKIP_DIRS  # noqa: E402  (one definition of "not source")
HTTP_VERBS = ("get", "post", "put", "patch", "delete")

# Which grammar reads which extension. `.tsx` needs its own language, not
# TypeScript's: measured, not assumed -- OrderCard.tsx parses with `has_error`
# True under both `javascript` and `typescript`, and False only under `tsx`.
LANG_BY_EXT = {".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "tsx"}

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
    """First line of the comment directly above `node`, or "".

    Babel hands the first statement in a file *every* comment that precedes it,
    which is how a file header once became the summary of whichever symbol
    happened to be declared first. Its fix was an adjacency test, and this keeps
    it: only a comment ending on the previous line counts, and only the last one
    of a run, which is the immediately preceding sibling.
    """
    prev = node.prev_sibling
    while prev is not None and prev.type not in ("comment",):
        if prev.is_named or _text(prev).strip():
            return ""
        prev = prev.prev_sibling
    if prev is None or prev.end_point[0] + 1 != _line(node) - 1:
        return ""
    raw = _text(prev)
    if raw.startswith("//"):
        body = raw[2:]
    elif raw.startswith("/*"):
        body = raw[2:-2] if raw.endswith("*/") else raw[2:]
    else:
        body = raw
    for line in body.split("\n"):
        cleaned = line.lstrip()
        if cleaned.startswith("*"):
            cleaned = cleaned[1:]
        cleaned = cleaned.strip()
        if cleaned:
            return cleaned
    return ""


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


def _url_of(node) -> str:
    """A route-ish path from a string or template literal, else "".

    A same-file string constant stands for its value (`_FILE_CONSTS`), as the whole
    argument or inside `${...}`; any other substitution becomes a `:name` segment.
    """
    if node is None:
        return ""
    if node.type == "identifier":
        return _FILE_CONSTS.get(_text(node), "")
    if node.type == "string":
        return "".join(_text(c) for c in node.children if c.type == "string_fragment")
    if node.type == "template_string":
        out = []
        for c in node.children:
            if c.type == "string_fragment":
                out.append(_text(c))
            elif c.type == "template_substitution":
                inner = c.named_children[0] if c.named_children else None
                if inner is not None and inner.type == "identifier" and _text(inner) in _FILE_CONSTS:
                    out.append(_FILE_CONSTS[_text(inner)])
                else:
                    out.append(":" + (_text(inner) if inner is not None and inner.type == "identifier"
                                      else "param"))
        return "".join(out)
    return ""


def _method_from_options(node) -> str:
    """The `method:` of a fetch options object, defaulting to GET like Babel."""
    if node is not None and node.type == "object":
        for pair in _named(node, "pair"):
            key = _field(pair, "key")
            if key is not None and _text(key).strip("\"'") == "method":
                value = _field(pair, "value")
                if value is not None and value.type == "string":
                    return _url_of(value).upper()
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
        return "", (_text(prop) if prop is not None else ""), (
            _text(obj) if obj is not None and obj.type == "identifier" else "")
    return "", "", ""


def _args(call) -> list:
    node = _field(call, "arguments")
    return list(node.named_children) if node is not None else []


# --- receiver types -----------------------------------------------------------
# An edge needs a node id, and a node id is `Class.method`. `store.save()` gives the
# method; the class has to come from what the source states about `store`. These are
# the shapes that state it. Everything else is "?" -- dropped, never guessed, which
# is the same rule `ts_extract` follows for Java/Go/C#.

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
            name = _field(n, "name")
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
    if obj.type == "identifier":
        return types.get(_text(obj), "") or "?"
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


def _collect_calls(root, axios_names: set, types: dict | None = None,
                   self_type: str = "") -> dict:
    """Called names and HTTP calls in a subtree, in source order.

    Each call carries the class of its receiver (`type`): "" for a bare call, the
    class where the source states it, "?" where it does not. That is the shape
    `ts_extract` already emits, so `build_flow` resolves JS/TS exactly as it
    resolves Java/Go/C#. Before this the receiver was discarded and only the name
    survived, which is why no call could ever land on a JS/TS class method.

    Order matters: `calls` feeds the graph's edges, and Babel's object-key walk
    visited a call's callee before its arguments. tree-sitter's children are in
    that same order, so `getOrder(x).then(y)` still yields `then` before
    `getOrder` -- the outer call first, then what it was called on.
    """
    types = types or {}
    calls: list[dict] = []
    seen: set = set()
    http: list[dict] = []

    def add(recv: str, name: str) -> None:
        if name and (recv, name) not in seen:
            seen.add((recv, name))
            calls.append({"type": recv, "name": name})

    def walk(node) -> None:
        if node.type == "call_expression":
            ident, prop, obj = _callee_parts(node)
            args = _args(node)
            if ident:
                add("", ident)
                if ident == "fetch":
                    http.append({"method": _method_from_options(args[1] if len(args) > 1 else None),
                                 "url": _url_of(args[0] if args else None)})
            elif prop:
                add(_receiver_type(node, types, self_type), prop)
                if obj in axios_names and prop in HTTP_VERBS:
                    http.append({"method": prop.upper(),
                                 "url": _url_of(args[0] if args else None)})
        for child in node.children:
            if child.type != "comment":
                walk(child)

    if root is not None:
        walk(root)
    return {"calls": calls, "http": http}


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
                    name = name.rsplit(".", 1)[1]
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


def _class_entry(node, raw, axios_names: set) -> dict:
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
                             {**fields, **_scope_types(member)}, cls_name),
        })
    return {
        "name": _text(name) if name is not None else "",
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
    for clause in _named(node, "import_clause"):
        for child in clause.named_children:
            if child.type == "identifier":                       # default import
                names.append(_text(child))
            elif child.type == "namespace_import":
                ident = child.named_children[-1] if child.named_children else None
                if ident is not None:
                    names.append(_text(ident))
            elif child.type == "named_imports":
                for spec in _named(child, "import_specifier"):
                    imported = _field(spec, "name")
                    if imported is not None:
                        names.append(_text(imported))
    return {"from": _url_of(source), "names": names}


def _extract_tree(root, axios_names: set) -> dict:
    global _FILE_CONSTS
    _FILE_CONSTS = _string_consts(root)
    out = {"classes": [], "functions": [], "imports": [],
           "routes": _express_routes(root, axios_names)}

    for raw in root.named_children:
        node = _unwrap_export(raw)
        if node is None:
            continue

        if node.type == "import_statement":
            out["imports"].append(_import_entry(node))

        elif node.type == "class_declaration":
            out["classes"].append(_class_entry(node, raw, axios_names))

        elif node.type == "function_declaration":
            name = _field(node, "name")
            if name is None:
                continue
            body = _field(node, "body")
            out["functions"].append({
                "name": _text(name), "doc": _doc_above(raw),
                "line": _line(node), "endLine": node.end_point[0] + 1,
                **_collect_calls(body, axios_names, _scope_types(node)), **_collect_jsx(body),
            })

        elif node.type in ("lexical_declaration", "variable_declaration"):
            for dec in _named(node, "variable_declarator"):
                name, value = _field(dec, "name"), _field(dec, "value")
                if name is None or name.type != "identifier" or value is None:
                    continue
                if value.type not in ("arrow_function", "function_expression", "function"):
                    continue
                body = _field(value, "body")
                out["functions"].append({
                    "name": _text(name), "doc": _doc_above(raw),
                    "line": _line(dec), "endLine": dec.end_point[0] + 1,
                    **_collect_calls(body, axios_names, _scope_types(value)), **_collect_jsx(body),
                })
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


def _module_key(path: str) -> str:
    """A file as an import specifier would name it: no extension, `/index` dropped."""
    key = os.path.splitext(path)[0].replace("\\", "/")
    return key[: -len("/index")] if key.endswith("/index") else key


def _resolve_import(spec: str, importer: str, keys: set) -> str | None:
    """The one module key an import specifier names, or None -- never a guess.

    Relative specifiers resolve exactly. Anything else is matched as a path suffix
    after a bare alias segment (`@/`, `~/`, `#/`), because tsconfig `paths` are not
    read: `@/services/api` is the file ending in `/services/api`, if exactly one does.
    """
    if spec.startswith("."):
        base = posixpath.dirname(importer.replace("\\", "/"))
        key = posixpath.normpath(posixpath.join(base, spec))
        return key if key in keys else None
    head, _, rest = spec.partition("/")
    tail = "/" + (rest if head in ("@", "~", "#") and rest else spec)
    hits = [k for k in keys if k.endswith(tail)]
    return hits[0] if len(hits) == 1 else None


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


def extract_file(path: str, axios_names: set | None = None) -> dict | None:
    tree = _parse(path)
    if tree is None:
        return None
    out = _extract_tree(tree.root_node, _axios_instances(tree.root_node) | (axios_names or set()))
    out["file"] = path
    return out


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
    exporters = {}
    for path, tree in parsed:
        exp = _exported_instances(tree.root_node, _axios_instances(tree.root_node) - {"axios"})
        if exp["default"] or exp["names"]:
            exporters[_module_key(path)] = exp
    results = []
    for path, tree in parsed:
        names = _axios_instances(tree.root_node)
        if exporters:
            names |= _imported_instances(tree.root_node, path, exporters, keys)
        out = _extract_tree(tree.root_node, names)
        out["file"] = path
        results.append(out)
    return results


if __name__ == "__main__":
    import json
    args = sys.argv[1:]
    root = args[0] if args else "."
    targets = sorted(find_js_files(os.path.abspath(root)))
    print(json.dumps(extract_js_files(targets), indent=2, sort_keys=True))
