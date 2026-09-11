#!/usr/bin/env python3
"""ts_extract.py — declarations and calls for thirteen languages, read from a real parse tree.

Java, Go and C# since phase 2 (inline branches, below); since phase 7 also Kotlin,
Rust, Swift, Scala, Groovy, Dart, C, C++, Ruby, PHP and Elixir (`SHAPES`, one
small table and a few readers per grammar -- Groovy through Java's branch).

Same contract as the textual extractor it replaces (`find_lang_files` /
`extract_lang_files`), so both graph builders consume it unchanged and the port
can be verified by diffing the graph rather than by reading code.

**One shared consumer, one small table per language.** Everything structural is
done once, against tree-sitter's *field names* -- `name`, `body`, `parameters`,
`type` -- which are the grammar's own semantic labels and are stable across
releases in a way node-type spelling is not. What differs per language is only
which node types are containers, methods, fields and calls, and that lives in
`SPEC` below. Adding a language is a row there plus its receiver rule, not a new
extractor.

What tree-sitter buys, exactly: declarations, bodies, parameter types and
comment attachment stop being regex problems. A Java interface method is a
`method_declaration` with no `body` field -- no pattern, no `throws` clause edge
case, no false positives from statements that merely look like declarations.

What it does not buy: **resolution**. `pricing.price()` is a call named `price`
on a receiver named `pricing`; deciding that means `PricingRule.price` needs the
declared type of `pricing`, which is a semantic question a syntax tree does not
answer. So `_calls` keeps the same three-way answer the textual extractor gave:

    ""   bare call -- the caller tries same-class, then a module function
    "X"  receiver resolved to declared type X
    "?"  receiver could not be typed; the caller counts it external, not a guess

Requires `tree-sitter` plus the grammar wheel for each language. A file whose
grammar is not installed is skipped with a named warning and the command to fix
it -- never silently dropped, because a smaller graph must not be mistakable for
a smaller codebase.

Python 3.10+.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402,F401  (puts sibling script dirs on sys.path)

import grammars  # noqa: E402

LANG_EXTS = {".java": "java", ".go": "go", ".cs": "csharp",
             # Phase 7 -- read by SHAPES below (Groovy by Java's branch).
             ".kt": "kotlin", ".kts": "kotlin", ".rs": "rust", ".swift": "swift",
             ".scala": "scala", ".groovy": "groovy", ".dart": "dart",
             ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp",
             ".rb": "ruby", ".php": "php", ".ex": "elixir", ".exs": "elixir"}
# Languages whose tree is Java's: same node types, same fields, same branch.
JAVA_LIKE = {"java", "groovy"}
from taxonomy import SKIP_DIRS  # noqa: E402  (one definition of "not source")

# Per language: which node types play which structural role. Everything else is
# shared. `container` is anything that owns methods (a class, interface, struct);
# `comment` is what can carry a doc; `call` is the call expression itself.
SPEC = {
    "java": {
        "container": {"class_declaration", "interface_declaration",
                      "enum_declaration", "record_declaration"},
        "method": {"method_declaration", "constructor_declaration"},
        "field": {"field_declaration"},
        "param": {"formal_parameter", "spread_parameter"},
        "comment": {"block_comment", "line_comment"},
        "call": {"method_invocation"},
        "bases": {"super_interfaces", "superclass"},
        "annotation": {"marker_annotation", "annotation"},
    },
    "csharp": {
        "container": {"class_declaration", "interface_declaration",
                      "struct_declaration", "record_declaration"},
        "method": {"method_declaration", "constructor_declaration"},
        "field": {"field_declaration", "property_declaration"},
        "param": {"parameter"},
        "comment": {"comment"},
        "call": {"invocation_expression"},
        "bases": {"base_list"},
        "annotation": {"attribute"},
    },
    "go": {
        "container": {"type_declaration"},
        "method": {"method_declaration", "function_declaration"},
        "field": {"field_declaration"},
        "param": {"parameter_declaration"},
        "comment": {"comment"},
        "call": {"call_expression"},
        "bases": set(),
        "annotation": set(),
    },
}
# Groovy's grammar spells classes, methods, fields and calls exactly as Java's does.
SPEC["groovy"] = dict(SPEC["java"])

SELF_WORDS = {"this", "self", "base", "super"}


# ---------------------------------------------------------------------------
# Tree helpers -- all field-based, so none of them know a language
# ---------------------------------------------------------------------------
def _text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _field(node, name: str):
    return node.child_by_field_name(name) if node is not None else None


def _field_text(node, name: str, src: bytes) -> str:
    got = _field(node, name)
    return _text(got, src) if got is not None else ""


def _line(node) -> int:
    """1-based line of a node.

    tree-sitter counts rows itself, which is why this is a `+ 1` and not a byte
    -> line conversion: the row is already correct for UTF-8 and for CRLF, both
    of which a hand-rolled character offset gets wrong.
    """
    return node.start_point[0] + 1


def _decl_line(node) -> int:
    """The line a declaration is *written* on, ignoring its annotations.

    A `class_declaration` node starts at `[ApiController]`, not at `class`, so
    using the node's own line would point every annotated declaration at its
    first attribute. The `name` field is where a reader would say it is.
    """
    name = _field(node, "name")
    return _line(name if name is not None else node)


def _end_line(node) -> int:
    return node.end_point[0] + 1


def _base_type(text: str) -> str:
    """`Map<String, Order>[]` -> `Map`, `*EventStore` -> `EventStore`.

    Returns "" for anything that does not reduce to a plain identifier. Go's
    `map[string]string` is the case that matters: squeezing it into a name would
    invent a type called `mapstringstring` and hand it to the resolver, which is
    exactly the "guess rather than drop" this extractor is not allowed to do.
    """
    text = text.strip().lstrip("*&")
    text = re.sub(r"(?:\s*\[\s*\])+$", "", text)     # Java's `Order[]`, and only that
    text = text.split("<")[0].split("(")[0]
    text = text.split(".")[-1].strip()
    # Anything still holding a bracket is a constructed type, not a named one --
    # `map[string]string`, `[]string`. Stripping the brackets would leave
    # `mapstringstring`, which reads like an identifier and is not one.
    return text if re.fullmatch(r"[A-Za-z_]\w*", text) else ""


def _doc_above(node, src: bytes, lang: str) -> str:
    """The comment block immediately above a declaration, cleaned of its markers.

    Walks previous *named* siblings so blank lines are invisible, and stops at
    the first non-comment -- a comment separated from the declaration by code is
    not its doc. Consecutive line comments are joined, which is how Go and C#
    write a doc block.
    """
    comments = []
    prev = node.prev_named_sibling
    if lang == "groovy" and prev is not None and prev.type not in SPEC[lang]["comment"]:
        # Groovy's grammar ends a field declaration that has no `;` at the next
        # token, so the doc comment of the member *below* it lands inside it.
        last = prev.named_children[-1] if prev.named_child_count else None
        if last is not None and last.type in SPEC[lang]["comment"]:
            comments.append(_text(last, src))
            prev = None
    while prev is not None and prev.type in SPEC[lang]["comment"]:
        comments.append(_text(prev, src))
        prev = prev.prev_named_sibling
    if not comments:
        return ""
    lines: list[str] = []
    for block in reversed(comments):
        block = re.sub(r"^/\*+|\*+/$", "", block.strip())
        for raw in block.splitlines():
            raw = raw.strip()
            raw = re.sub(r"^(?://+/?|\*+)\s?", "", raw)
            raw = re.sub(r"</?(?:summary|remarks|para)>", "", raw)     # C# XML doc
            raw = re.sub(r"<[^>]+>", "", raw)
            if raw.strip():
                lines.append(raw.strip())
    return " ".join(lines).strip()


def _walk(node, types: set[str], stop: set[str] = frozenset()):
    """Every descendant whose type is in `types`, not descending into `stop`."""
    for child in node.named_children:
        if child.type in types:
            yield child
        if child.type not in stop:
            yield from _walk(child, types, stop)


# ---------------------------------------------------------------------------
# Parameters, fields, locals -- the declared types resolution runs on
# ---------------------------------------------------------------------------
def _params(node, src: bytes, lang: str) -> dict[str, str]:
    """Parameter name -> declared base type, from a declaration's `parameters`."""
    return _params_of(_field(node, "parameters"), src, lang)


def _params_of(params, src: bytes, lang: str) -> dict[str, str]:
    """The same, given the parameter list itself -- Go's receiver is one of these."""
    out: dict[str, str] = {}
    if params is None:
        return out
    for p in params.named_children:
        if p.type not in SPEC[lang]["param"]:
            continue
        name = _field_text(p, "name", src)
        declared = _field_text(p, "type", src)
        if lang == "csharp" and not declared:
            # C# writes `Type name` with both as fields; older grammars label the
            # type only positionally, so fall back to the first named child.
            kids = [c for c in p.named_children if c.type != "attribute_list"]
            declared = _text(kids[0], src) if len(kids) > 1 else ""
            name = name or (_text(kids[-1], src) if kids else "")
        base = _base_type(declared)
        if base and re.fullmatch(r"[A-Za-z_]\w*", name):
            out[name] = base
    return out


def _fields(container, src: bytes, lang: str) -> dict[str, str]:
    """Field/property name -> declared base type for one container."""
    out: dict[str, str] = {}
    body = _field(container, "body")
    if body is None and lang == "go":
        body = container
    if body is None:
        return out
    for f in _walk(body, SPEC[lang]["field"], stop=SPEC[lang]["method"]):
        declared = _base_type(_field_text(f, "type", src))
        names: list[str] = []
        if lang in JAVA_LIKE:
            for d in f.named_children:
                if d.type == "variable_declarator":
                    names.append(_field_text(d, "name", src))
        elif lang == "go":
            names = [_text(c, src) for c in f.named_children if c.type == "field_identifier"]
            if not declared:
                declared = _base_type(_field_text(f, "type", src))
        else:
            # C#: a property states `type` and `name` on itself; a field wraps
            # both in a `variable_declaration`, so read that rather than the
            # whole child's text -- which would give the type *and* the name.
            name = _field_text(f, "name", src)
            if name:
                names.append(name)
            decl = next((c for c in f.named_children if c.type == "variable_declaration"), None)
            if decl is not None:
                declared = declared or _base_type(_field_text(decl, "type", src))
                for d in decl.named_children:
                    if d.type == "variable_declarator":
                        names.append(_field_text(d, "name", src) or _text(d, src).split("=")[0].strip())
        for name in names:
            if name and declared:
                out[name] = declared
    return out


NEW_LOCAL_RE = re.compile(r"(?:^|[^\w.])(?:var|[\w.<>\[\]]+)\s+(\w+)\s*=\s*new\s+([\w.]+)\s*[(<{]")
GO_LOCAL_RE = re.compile(r"(\w+)\s*:=\s*&?(?:\w+\.)?(\w+)\{")
GO_CTOR_RE = re.compile(r"(\w+)\s*:=\s*(?:\w+\.)?New(\w+)\s*\(")
GO_VAR_RE = re.compile(r"\bvar\s+(\w+)\s+\*?(?:\w+\.)?(\w+)\b")


def _locals(body_text: str, lang: str) -> dict[str, str]:
    """Local variable -> type, from the constructions that state it outright.

    Still text, deliberately. These are the shapes where the type is written on
    the same line as the assignment, and matching them on the tree would mean
    four more node types per language for no extra precision.
    """
    types: dict[str, str] = {}
    if lang == "go":
        for name, cls in GO_LOCAL_RE.findall(body_text):
            types[name] = cls
        for name, cls in GO_CTOR_RE.findall(body_text):
            types[name] = cls
        for name, cls in GO_VAR_RE.findall(body_text):
            types.setdefault(name, cls)
    else:
        for name, cls in NEW_LOCAL_RE.findall(body_text):
            types[name] = _base_type(cls)
    return {k: v for k, v in types.items() if v}


# ---------------------------------------------------------------------------
# Calls -- the one part tree-sitter does not answer
# ---------------------------------------------------------------------------
def _receiver_and_name(call, src: bytes, lang: str) -> tuple[str, str]:
    """(receiver text, method name) for one call node, or ("", "") to skip it."""
    if lang in JAVA_LIKE:
        name = _field_text(call, "name", src)
        obj = _field(call, "object")
        return (_text(obj, src) if obj is not None else ""), name
    fn = _field(call, "function")
    if fn is None:
        return "", ""
    if lang == "csharp":
        if fn.type == "member_access_expression":
            return _field_text(fn, "expression", src), _field_text(fn, "name", src)
        if fn.type == "identifier":
            return "", _text(fn, src)
        return "", ""
    if fn.type == "selector_expression":                      # go
        return _field_text(fn, "operand", src), _field_text(fn, "field", src)
    if fn.type == "identifier":
        return "", _text(fn, src)
    return "", ""


def _calls(body, src: bytes, lang: str, types: dict[str, str], recv_name: str = "") -> list[dict]:
    """Call sites in a body, with the receiver resolved to a declared type."""
    out: list[dict] = []
    if body is None:
        return out
    for call in _walk(body, SPEC[lang]["call"]):
        recv, name = _receiver_and_name(call, src, lang)
        if not name or not re.fullmatch(r"[A-Za-z_]\w*", name):
            continue
        recv = recv.replace(" ", "")
        if not recv:
            out.append({"type": "", "name": name})
            continue
        parts = recv.split(".")
        head = parts[0]
        if head in SELF_WORDS and len(parts) == 1:
            out.append({"type": "", "name": name})        # `this.m()` is same-class
            continue
        resolved = ""
        if len(parts) == 1:
            resolved = types.get(head, "")
        elif len(parts) == 2 and (head in SELF_WORDS or head == recv_name):
            resolved = types.get(parts[1], "")            # this.field.m() / r.field.m()
        out.append({"type": resolved or "?", "name": name})
    return out


def _dedupe_calls(calls: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for c in sorted(calls, key=lambda c: (c["type"], c["name"])):
        key = (c["type"], c["name"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Routes -- not in any tags query; read from annotations and router calls
# ---------------------------------------------------------------------------
JAVA_VERBS = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
              "PatchMapping": "PATCH", "DeleteMapping": "DELETE"}
CS_VERBS = {"HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT",
            "HttpPatch": "PATCH", "HttpDelete": "DELETE"}
REQUEST_METHOD_RE = re.compile(r"RequestMethod\.(\w+)")
HTTP_VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
GO_ROUTE_FUNCS = {"HandleFunc", "Handle", "GET", "POST", "PUT", "PATCH", "DELETE",
                  "Get", "Post", "Put", "Patch", "Delete"}


def _join_path(prefix: str, suffix: str) -> str:
    parts = [p.strip("/") for p in (prefix, suffix) if p and p.strip("/")]
    return "/" + "/".join(parts)


def _annotations(node, src: bytes, lang: str) -> list[dict]:
    """Annotations/attributes attached to a declaration: name, first string arg, text."""
    out: list[dict] = []
    if not SPEC[lang]["annotation"]:
        return out
    for child in node.named_children:
        if child.type not in ("modifiers", "attribute_list"):
            continue
        for anno in _walk(child, SPEC[lang]["annotation"]) if child.type == "modifiers" \
                else child.named_children:
            if anno.type not in SPEC[lang]["annotation"]:
                continue
            out.append({"name": _base_type(_field_text(anno, "name", src)),
                        "arg": _first_string(anno, src),
                        "text": _text(anno, src)})
    return out


def _first_string(node, src: bytes) -> str:
    """The first string literal inside a node, unquoted."""
    for lit in _walk(node, {"string_literal", "interpreted_string_literal",
                            "raw_string_literal", "verbatim_string_literal"}):
        return _text(lit, src).strip('@$"`\'')
    return ""


def _class_prefix(annos: list[dict], lang: str, cls_name: str) -> str:
    for a in annos:
        if lang == "java" and a["name"] in ("RequestMapping", "Path") and a["arg"]:
            return a["arg"]
        if lang == "csharp" and a["name"] == "Route" and a["arg"]:
            # ASP.NET's `[controller]` token means the class name without its suffix.
            return a["arg"].replace("[controller]", re.sub(r"Controller$", "", cls_name))
    return ""


def _method_routes(annos: list[dict], prefix: str, lang: str) -> list[dict]:
    verbs = JAVA_VERBS if lang == "java" else CS_VERBS
    routes = []
    for a in annos:
        if a["name"] in verbs:
            routes.append({"method": verbs[a["name"]], "path": _join_path(prefix, a["arg"])})
        elif lang == "java" and a["name"] == "RequestMapping":
            for verb in (REQUEST_METHOD_RE.findall(a["text"]) or ["ANY"]):
                routes.append({"method": verb.upper(), "path": _join_path(prefix, a["arg"])})
    return routes


def _statement_of(node):
    """The statement a node sits in, so a comment above it can be found.

    A route registration is an expression buried inside a call; its doc comment
    is a sibling of the *statement*, not of the call. Climbing to the statement
    is what makes `// Liveness probe` belong to the route below it.
    """
    cur = node
    while cur.parent is not None and cur.parent.type not in ("statement_list", "block", "source_file"):
        cur = cur.parent
    return cur


def _go_routes(root, src: bytes) -> list[dict]:
    """Router registrations anywhere in the file (they live inside main/NewRouter)."""
    routes = []
    for call in _walk(root, SPEC["go"]["call"]):
        fn = _field(call, "function")
        if fn is None or fn.type != "selector_expression":
            continue
        verb_name = _field_text(fn, "field", src)
        if verb_name not in GO_ROUTE_FUNCS:
            continue
        args = _field(call, "arguments")
        if args is None:
            continue
        literals = [a for a in args.named_children]
        pattern = _first_string(args, src)
        if not pattern:
            continue
        verb = verb_name.upper() if verb_name.upper() in HTTP_VERBS else ""
        path = pattern
        head, _, rest = pattern.partition(" ")
        if head.upper() in HTTP_VERBS and rest:          # `mux.HandleFunc("GET /x", h)`
            verb, path = head.upper(), rest.strip()
        handler = ""
        if len(literals) > 1:
            tail = _text(literals[-1], src).strip().split(".")[-1]
            handler = tail if re.fullmatch(r"[A-Za-z_]\w*", tail) else ""
        # endLine is what gives an inline handler (`mux.HandleFunc("GET /x", func...)`)
        # a readable range. Without it the endpoint node got `end: 0`, and every pass
        # that reads ranges -- duplicates first -- quietly filed it as a synthetic node
        # with no body. Found by tools/check_graph.py (c06), not by anything failing.
        routes.append({"method": verb or "ANY", "path": path, "handler": handler,
                       "line": _line(call), "endLine": _end_line(_statement_of(call)),
                       "doc": _doc_above(_statement_of(call), src, "go")})
    return routes


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------
def _method(node, src: bytes, lang: str, fields: dict[str, str],
            prefix: str, recv_name: str = "") -> dict:
    """One method/function record, shaped exactly like the textual extractor's."""
    params = _params(node, src, lang)
    types = dict(fields)
    types.update(params)
    body = _field(node, "body")
    if body is not None:
        types.update(_locals(_text(body, src), lang))
    annos = _annotations(node, src, lang)
    entry = {
        "name": _field_text(node, "name", src),
        "doc": _doc_above(node, src, lang),
        "line": _decl_line(node),
        "endLine": _end_line(node),
        "params": params,
        "calls": _dedupe_calls(_calls(body, src, lang, types, recv_name)),
        "routes": _method_routes(annos, prefix, lang),
        "http": [],
    }
    if body is None:
        # No `body` field at all: an interface member or an `abstract` method.
        # tree-sitter states this outright -- no pattern, no false positives.
        entry["declaration"] = True
    return entry


def _bases(node, src: bytes, lang: str) -> list[str]:
    out = []
    for child in node.named_children:
        if child.type in SPEC[lang]["bases"]:
            for part in re.split(r"[,\s]+", _text(child, src)):
                part = _base_type(re.sub(r"^(?:implements|extends|:)$", "", part))
                if part and part not in ("implements", "extends"):
                    out.append(part)
    return [b for b in out if b]


def _containers(root, src: bytes, lang: str) -> tuple[list[dict], list[dict]]:
    """(classes, functions) for one file."""
    classes: list[dict] = []
    go_types: dict[str, dict] = {}

    if lang == "go":
        for decl in _walk(root, {"type_declaration"}):
            for spec in decl.named_children:
                if spec.type != "type_spec":
                    continue
                name = _field_text(spec, "name", src)
                shape = _field(spec, "type")
                if not name or shape is None:
                    continue
                go_types[name] = {
                    "name": name, "bases": [], "decorators": [],
                    "doc": _doc_above(decl, src, lang),
                    "line": _decl_line(spec), "endLine": _end_line(decl),
                    "fields": _fields(shape, src, lang), "methods": [],
                }
        functions = []
        for fn in _walk(root, {"method_declaration", "function_declaration"}):
            recv = _field(fn, "receiver")
            if recv is None:
                functions.append(_method(fn, src, lang, {}, ""))
                continue
            recv_params = _params_of(recv, src, lang)
            owner = next(iter(recv_params.values()), "")
            recv_name = next(iter(recv_params), "")
            holder = go_types.get(owner)
            fields = holder["fields"] if holder else {}
            entry = _method(fn, src, lang, fields, "", recv_name)
            if holder:
                holder["methods"].append(entry)
            else:
                functions.append(entry)
        return [go_types[k] for k in sorted(go_types)], functions

    for node in _walk(root, SPEC[lang]["container"]):
        name = _field_text(node, "name", src)
        if not name:
            continue
        annos = _annotations(node, src, lang)
        prefix = _class_prefix(annos, lang, name)
        fields = _fields(node, src, lang)
        body = _field(node, "body")
        methods = []
        if body is not None:
            for m in body.named_children:
                if m.type == "constructor_declaration":
                    # Deliberate parity with the extractor this replaces: a
                    # constructor is not a graph node there, and changing that
                    # here would mix a behaviour change into a port. It is a
                    # one-word change in SPEC when someone wants it.
                    continue
                if m.type in SPEC[lang]["method"] and _field_text(m, "name", src):
                    methods.append(_method(m, src, lang, fields, prefix))
        classes.append({
            "name": name,
            "bases": _bases(node, src, lang),
            "decorators": [a["name"] for a in annos],
            "doc": _doc_above(node, src, lang),
            "line": _decl_line(node), "endLine": _end_line(node),
            "fields": fields, "methods": methods,
        })
    return classes, []


IMPORT_TYPES = {"java": {"import_declaration"}, "csharp": {"using_directive"}, "go": set(),
                "groovy": {"import_declaration"}}


# ---------------------------------------------------------------------------
# Phase 7 languages -- one walker, one small shape per grammar
# ---------------------------------------------------------------------------
# Java/Go/C# above were ported line for line from the textual extractor, which is
# why their per-language branches are inline. The ten languages phase 7 added
# share one walker instead (Groovy's tree is Java's, so it takes Java's branch):
# each grammar names its container / method / comment node types here, and the few
# places a tree is genuinely shaped differently get one small reader each -- a
# Rust method lives in an `impl`, a Dart method is a signature *beside* its body,
# a C function's name sits inside nested declarators, an Elixir `def` is a macro
# call. Resolution is `_calls`'s three-way answer plus one rule these languages
# lean on: a receiver that is itself a type name (`WidgetStore.save` in Elixir,
# `Widget::new` in Rust, `Store::get` in PHP) resolves to that type.
SHAPES = {
    "kotlin": {"container": {"class_declaration", "object_declaration"},
               "method": {"function_declaration"}, "comment": {"block_comment", "line_comment"}},
    "rust": {"container": {"struct_item", "enum_item", "trait_item"},
             "method": {"function_item", "function_signature_item"},
             "comment": {"line_comment", "block_comment"}},
    "swift": {"container": {"class_declaration", "protocol_declaration"},
              "method": {"function_declaration", "protocol_function_declaration"},
              "comment": {"comment", "multiline_comment"}},
    "scala": {"container": {"class_definition", "object_definition", "trait_definition"},
              "method": {"function_definition", "function_declaration"},
              "comment": {"comment", "block_comment"}},
    "dart": {"container": {"class_definition", "mixin_declaration"},
             "method": {"method_signature", "function_signature"},
             "comment": {"comment", "documentation_comment"}},
    "c": {"container": set(), "method": {"function_definition"}, "comment": {"comment"}},
    "cpp": {"container": {"class_specifier", "struct_specifier"},
            "method": {"function_definition"}, "comment": {"comment"}},
    "ruby": {"container": {"class", "module"}, "method": {"method", "singleton_method"},
             "comment": {"comment"}},
    "php": {"container": {"class_declaration", "interface_declaration", "trait_declaration"},
            "method": {"method_declaration", "function_definition"}, "comment": {"comment"}},
    # Elixir has no declaration nodes: `defmodule` and `def` are calls, so these
    # are the *names* of the macros (see `_gkind`), not node types.
    "elixir": {"container": {"defmodule"}, "method": {"def", "defp"}, "comment": {"comment"}},
}
_BODY_TYPES = {"class_body", "enum_class_body", "template_body", "declaration_list",
               "field_declaration_list", "body_statement", "protocol_body"}
_SKIP_ABOVE = {"attribute_item", "annotated_expression", "access_specifier"}
_KT_NAMES = {"identifier", "simple_identifier"}
_KT_TYPES = {"user_type", "nullable_type"}
_G_SELF = SELF_WORDS | {"parent", "static"}
_G_BASES = {"kotlin": {"delegation_specifier"}, "swift": {"inheritance_specifier"},
            "scala": {"extends_clause"}, "dart": {"superclass", "interfaces", "mixins"},
            "cpp": {"base_class_clause"}, "ruby": {"superclass"},
            "php": {"base_clause", "class_interface_clause"}}
_BASE_WORDS = {"extends", "implements", "with", "public", "private", "protected", "virtual",
               "class", "struct"}
_G_CALLS = {"kotlin": {"call_expression"}, "rust": {"call_expression"}, "swift": {"call_expression"},
            "scala": {"call_expression"}, "c": {"call_expression"}, "cpp": {"call_expression"},
            "ruby": {"call"}, "elixir": {"call"},
            "php": {"member_call_expression", "nullsafe_member_call_expression",
                    "function_call_expression", "scoped_call_expression"}}
# Macros and special forms: calls in the grammar, never a function of the code's own.
_EX_MACROS = {"def", "defp", "defmodule", "defmacro", "defmacrop", "defstruct", "defprotocol",
              "defimpl", "defdelegate", "defexception", "if", "unless", "for", "case", "cond",
              "with", "fn", "quote", "unquote", "import", "alias", "require", "use", "raise",
              "try", "receive"}
RUST_VERBS = {"get", "post", "put", "patch", "delete", "head"}
# A local whose type is written where it is made -- the same idea as `_locals`.
_G_LOCALS = {
    "kotlin": re.compile(r"\b(?:val|var)\s+(\w+)(?:\s*:\s*[\w.<>?]+)?\s*=\s*([A-Z]\w*)\s*\("),
    "scala": re.compile(r"\b(?:val|var)\s+(\w+)(?:\s*:\s*[\w.\[\]]+)?\s*=\s*(?:new\s+)?([A-Z]\w*)\s*[(\[{]"),
    "swift": re.compile(r"\b(?:let|var)\s+(\w+)(?:\s*:\s*[\w.<>?]+)?\s*=\s*([A-Z]\w*)\s*\("),
    "dart": re.compile(r"\b(?:final|var|const|[A-Z]\w*)\s+(\w+)\s*=\s*(?:new\s+|const\s+)?([A-Z]\w*)\s*\("),
    "rust": re.compile(r"\blet\s+(?:mut\s+)?(\w+)(?:\s*:\s*[\w:<>&']+)?\s*=\s*([A-Z]\w*)\s*(?:\{|::)"),
    "php": re.compile(r"\$(\w+)\s*=\s*new\s+\\?(?:\w+\\)*([A-Z]\w*)"),
    "ruby": re.compile(r"\b(\w+)\s*=\s*([A-Z]\w*)\.new\b"),
}
_CPP_LOCAL = re.compile(r"(?m)^\s*(?:const\s+)?([A-Z]\w*)\s*[*&]?\s*(\w+)\s*(?:;|\(|\{|=)")


def _child(node, types):
    """The first direct named child of one of `types`, or None."""
    if node is None:
        return None
    return next((c for c in node.named_children if c.type in types), None)


def _first_of(node, types):
    """The first named descendant of one of `types` (depth first), or None."""
    if node is None:
        return None
    for c in node.named_children:
        if c.type in types:
            return c
        found = _first_of(c, types)
        if found is not None:
            return found
    return None


def _gkind(node, src: bytes, lang: str) -> str:
    """A node's structural role: its type -- or, for an Elixir macro call, the macro."""
    if lang == "elixir" and node.type == "call":
        target = _field(node, "target")
        return _text(target, src) if target is not None and target.type == "identifier" else ""
    return node.type


def _gname_node(node, src: bytes, lang: str):
    """The node holding a declaration's name, or None."""
    if lang == "elixir":
        args = _child(node, {"arguments"})
        head = args.named_children[0] if args is not None and args.named_child_count else None
        if head is not None and head.type == "binary_operator":      # def f(x) when guard
            head = _field(head, "left")
        if head is not None and head.type == "call":                  # def f(x)
            head = _field(head, "target")
        return head if head is not None and head.type in ("identifier", "alias") else None
    if lang == "dart" and node.type == "method_signature":
        node = _child(node, {"function_signature", "getter_signature", "setter_signature"})
        return _field(node, "name") if node is not None else None
    if lang in ("c", "cpp") and node.type == "function_definition":
        d = _field(node, "declarator")
        while d is not None and d.type not in ("identifier", "field_identifier",
                                               "qualified_identifier", "destructor_name"):
            d = _field(d, "declarator")
        return d
    return _field(node, "name")


def _gbody(node, lang: str):
    """Where a container's members live."""
    if lang == "elixir":
        return _child(node, {"do_block"})
    return _field(node, "body") or _child(node, _BODY_TYPES)


def _gmbody(node, lang: str):
    """A method's body, or None for a signature."""
    if lang == "dart":
        nxt = node.next_named_sibling
        return nxt if nxt is not None and nxt.type == "function_body" else None
    if lang == "elixir":
        return _child(node, {"do_block"}) or _child(node, {"arguments"})
    if lang == "kotlin":
        return _child(node, {"function_body"})
    return _field(node, "body")


def _ktext(node, types, src: bytes) -> str:
    got = _child(node, types)
    return _text(got, src) if got is not None else ""


def _gparam_pairs(node, src: bytes, lang: str):
    """(name, declared type text) for each parameter; the type is "" where none is written."""
    if lang == "kotlin":
        plist = _child(node, {"function_value_parameters"})
        for p in plist.named_children if plist is not None else []:
            if p.type == "parameter":
                yield _ktext(p, _KT_NAMES, src), _ktext(p, _KT_TYPES, src)
    elif lang == "swift":
        for p in node.named_children:
            names = p.children_by_field_name("name") if p.type == "parameter" else []
            if len(names) > 1:                        # `name: Type` -- both are `name` fields
                yield _text(names[0], src), _text(names[-1], src)
    elif lang == "dart":
        sig = _child(node, {"function_signature"}) if node.type == "method_signature" else node
        plist = _child(sig, {"formal_parameter_list"})
        for p in _walk(plist, {"formal_parameter"}) if plist is not None else []:
            yield _field_text(p, "name", src), _ktext(p, {"type_identifier"}, src)
    elif lang in ("c", "cpp"):
        fd = _field(node, "declarator")
        while fd is not None and fd.type != "function_declarator":
            fd = _field(fd, "declarator")
        plist = _field(fd, "parameters") if fd is not None else None
        for p in plist.named_children if plist is not None else []:
            if p.type in ("parameter_declaration", "optional_parameter_declaration"):
                d = _field(p, "declarator")
                ident = d if d is not None and d.type == "identifier" else _first_of(d, {"identifier"})
                yield (_text(ident, src) if ident is not None else ""), _field_text(p, "type", src)
    elif lang == "php":
        plist = _field(node, "parameters")
        for p in plist.named_children if plist is not None else []:
            yield _field_text(p, "name", src).lstrip("$"), _field_text(p, "type", src)
    elif lang in ("rust", "scala"):
        plist = _field(node, "parameters")
        for p in plist.named_children if plist is not None else []:
            if p.type == "parameter":
                yield _field_text(p, "pattern" if lang == "rust" else "name", src), _field_text(p, "type", src)
    # ruby, elixir: no declared types to read


def _gparams(node, src: bytes, lang: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, declared in _gparam_pairs(node, src, lang):
        base = _base_type(declared)
        if base and re.fullmatch(r"[A-Za-z_]\w*", name):
            out[name] = base
    return out


def _gfields(node, src: bytes, lang: str) -> dict[str, str]:
    """Field name -> declared base type for one container."""
    out: dict[str, str] = {}

    def put(name: str, declared: str) -> None:
        base = _base_type(declared)
        if name and base:
            out[name] = base

    body = _gbody(node, lang)
    methods = SHAPES[lang]["method"]
    if lang == "kotlin":
        params = _child(_child(node, {"primary_constructor"}), {"class_parameters"})
        for p in params.named_children if params is not None else []:
            if p.type == "class_parameter":                       # class Service(val store: Store)
                put(_ktext(p, _KT_NAMES, src), _ktext(p, _KT_TYPES, src))
        for prop in _walk(body, {"property_declaration"}, methods) if body is not None else []:
            var = _child(prop, {"variable_declaration"})
            if var is not None:
                put(_ktext(var, _KT_NAMES, src), _ktext(var, _KT_TYPES, src))
    elif lang == "rust":
        for f in _walk(body, {"field_declaration"}) if body is not None else []:
            put(_field_text(f, "name", src), _field_text(f, "type", src))
    elif lang == "swift":
        for prop in _walk(body, {"property_declaration"}, methods) if body is not None else []:
            ident = _first_of(_field(prop, "name"), {"simple_identifier"})
            ann = _child(prop, {"type_annotation"})
            put(_text(ident, src) if ident is not None else "",
                _field_text(ann, "name", src) if ann is not None else "")
    elif lang == "scala":
        params = _field(node, "class_parameters")
        for p in params.named_children if params is not None else []:
            if p.type == "class_parameter":
                put(_field_text(p, "name", src), _field_text(p, "type", src))
        for v in _walk(body, {"val_definition", "var_definition"}, methods) if body is not None else []:
            put(_field_text(v, "pattern", src), _field_text(v, "type", src))
    elif lang == "dart":
        for d in body.named_children if body is not None else []:
            if d.type == "declaration":                           # final Store store;
                declared = _ktext(d, {"type_identifier"}, src)
                for ident in _walk(d, {"initialized_identifier"}):
                    name = _first_of(ident, {"identifier"})
                    put(_text(name, src) if name is not None else "", declared)
    elif lang == "cpp":
        for f in body.named_children if body is not None else []:
            if f.type == "field_declaration":
                d = _field(f, "declarator")
                ident = d if d is not None and d.type == "field_identifier" else _first_of(d, {"field_identifier"})
                put(_text(ident, src) if ident is not None else "", _field_text(f, "type", src))
    elif lang == "php":
        for p in _walk(node, {"property_promotion_parameter"}):   # __construct(private Store $store)
            put(_field_text(p, "name", src).lstrip("$"), _field_text(p, "type", src))
        for prop in _walk(body, {"property_declaration"}) if body is not None else []:
            declared = _field_text(prop, "type", src)
            for el in _walk(prop, {"property_element"}):
                name = _first_of(el, {"variable_name"})
                put(_text(name, src).lstrip("$") if name is not None else "", declared)
    return out


def _grecv(call, src: bytes, lang: str) -> tuple[str, str]:
    """(receiver text, method name) for one call node, or ("", "") to skip it."""
    if lang in ("kotlin", "swift"):
        head = call.named_children[0] if call.named_child_count else None
        if head is None:
            return "", ""
        if head.type == "navigation_expression":
            if lang == "swift":
                suffix = _field(head, "suffix")
                name = _field(suffix, "suffix") if suffix is not None else None
                return _field_text(head, "target", src), (_text(name, src) if name is not None else "")
            kids = head.named_children
            recv = src[head.start_byte:kids[-1].start_byte].decode("utf-8", "replace")
            return recv.rstrip(".?"), _text(kids[-1], src)
        return ("", _text(head, src)) if head.type in _KT_NAMES else ("", "")
    if lang in ("rust", "scala", "c", "cpp"):
        fn = _field(call, "function")
        if fn is None:
            return "", ""
        if fn.type == "field_expression":
            recv = _field(fn, "value") if lang in ("rust", "scala") else _field(fn, "argument")
            return (_text(recv, src) if recv is not None else ""), _field_text(fn, "field", src)
        if fn.type in ("scoped_identifier", "qualified_identifier"):
            scope = _field(fn, "path") if lang == "rust" else _field(fn, "scope")
            return (_text(scope, src) if scope is not None else ""), _field_text(fn, "name", src)
        return ("", _text(fn, src)) if fn.type == "identifier" else ("", "")
    if lang == "ruby":
        recv = _field(call, "receiver")
        return (_text(recv, src) if recv is not None else ""), _field_text(call, "method", src)
    if lang == "php":
        if call.type == "function_call_expression":
            return "", _field_text(call, "function", src)
        obj = _field(call, "object") or _field(call, "scope")
        return (_text(obj, src) if obj is not None else ""), _field_text(call, "name", src)
    if lang == "elixir":
        target = _field(call, "target")
        if target is not None and target.type == "dot":
            return _field_text(target, "left", src), _field_text(target, "right", src)
        if target is not None and target.type == "identifier" and _text(target, src) not in _EX_MACROS:
            return "", _text(target, src)
    return "", ""


def _gcalls(body, src: bytes, lang: str) -> list[tuple[str, str]]:
    """(receiver, name) for every call site in a body."""
    if body is None:
        return []
    if lang == "ruby":
        return [_grecv(call, src, lang) for call in _walk(body, _G_CALLS[lang])] + _rb_bare_calls(body, src)
    if lang != "dart":
        return [_grecv(call, src, lang) for call in _walk(body, _G_CALLS[lang])]
    # Dart has no call node: `store.save(x)` is `identifier, selector(.save),
    # selector(arguments)` side by side, so a call is read off the sibling sequence.
    out = []
    stack = [body]
    while stack:
        node = stack.pop()
        kids = node.named_children
        for i, kid in enumerate(kids):
            if kid.type != "selector" or _child(kid, {"argument_part"}) is None or not i:
                continue
            prev = kids[i - 1]
            if prev.type == "selector":
                sel = _child(prev, {"unconditional_assignable_selector", "conditional_assignable_selector"})
                ident = _child(sel, {"identifier"})
                if ident is not None:
                    recv = "".join(_text(k, src) for k in kids[:i - 1])
                    out.append((recv, _text(ident, src)))
            elif prev.type == "identifier" and (i == 1 or kids[i - 2].type != "selector"):
                out.append(("", _text(prev, src)))     # a bare call: nothing chained before it
        stack.extend(kids)
    return out


def _rb_bare_calls(body, src: bytes) -> list[tuple[str, str]]:
    """Ruby's argument-less calls: `index`, with no parentheses, parses as an identifier.

    In Ruby a bare name that is not a parameter or a local *is* a method call (or a
    NameError), so reading it as one is the language's own rule, not a guess. Found
    by the Rails fixture, where `def create; index; end` produced no edge at all.
    """
    method = body.parent
    local = {_text(p, src) for p in _walk(_field(method, "parameters"), {"identifier"})} \
        if method is not None and _field(method, "parameters") is not None else set()
    for node in _walk(body, {"assignment", "operator_assignment"}):
        left = _field(node, "left")
        if left is not None and left.type == "identifier":
            local.add(_text(left, src))
    for node in _walk(body, {"for", "block_parameters", "lambda_parameters"}):
        target = _field(node, "pattern") if node.type == "for" else node
        if target is not None:
            local |= {_text(i, src) for i in ([target] if target.type == "identifier"
                                               else _walk(target, {"identifier"}))}
    out = []
    for ident in _walk(body, {"identifier"}):
        parent = ident.parent
        if parent is not None and parent.type == "call" and ident == _field(parent, "method"):
            continue                                  # a call's own name: already read
        if parent is not None and parent.type in ("assignment", "operator_assignment") \
                and ident == _field(parent, "left"):
            continue
        if parent is not None and parent.type in ("for", "block_parameters", "lambda_parameters"):
            continue
        if _text(ident, src) not in local:
            out.append(("", _text(ident, src)))
    return out


def _gresolve(pairs, types: dict[str, str]) -> list[dict]:
    """`_calls`'s three-way answer, plus: a receiver that is a type name is that type."""
    out = []
    for recv, name in pairs:
        if not name or not re.fullmatch(r"[A-Za-z_]\w*", name):
            continue
        recv = re.sub(r"\s+", "", recv).replace("?.", ".").replace("->", ".").replace("::", ".")
        recv = recv.replace("$", "").lstrip("@")
        if not recv:
            out.append({"type": "", "name": name})
            continue
        parts = recv.split(".")
        head = parts[0]
        if head in _G_SELF and len(parts) == 1:
            out.append({"type": "", "name": name})
            continue
        resolved = ""
        if len(parts) == 1:
            resolved = types.get(head, "") or (head if re.fullmatch(r"[A-Z]\w*", head) else "")
        elif len(parts) == 2 and head in _G_SELF:
            resolved = types.get(parts[1], "")
        out.append({"type": resolved or "?", "name": name})
    return out


def _glocals(body_text: str, lang: str) -> dict[str, str]:
    if lang == "cpp":
        return {name: t for t, name in _CPP_LOCAL.findall(body_text)}
    rx = _G_LOCALS.get(lang)
    return dict(rx.findall(body_text)) if rx is not None else {}


def _clean_doc(comments: list[str]) -> str:
    lines: list[str] = []
    for block in reversed(comments):
        block = re.sub(r"^/\*+|\*+/$", "", block.strip())
        for raw in block.splitlines():
            raw = re.sub(r"^(?://+[/!]?|\*+|#+)\s?", "", raw.strip())
            if raw.strip():
                lines.append(raw.strip())
    return " ".join(lines).strip()


def _gdoc(node, src: bytes, lang: str) -> str:
    """The comment block right above a declaration -- or an Elixir `@doc` / `@moduledoc`."""
    if lang == "elixir":
        if _gkind(node, src, lang) == "defmodule":
            for c in (_child(node, {"do_block"}) or node).named_children:
                call = _field(c, "operand") if c.type == "unary_operator" else None
                if call is not None and call.type == "call" and _gkind(call, src, lang) == "moduledoc":
                    s = _first_of(call, {"quoted_content"})
                    return _text(s, src).strip() if s is not None else ""
            return ""
        prev = node.prev_named_sibling
        while prev is not None and prev.type == "unary_operator":   # @doc, @spec, @impl ...
            call = _field(prev, "operand")
            if call is not None and call.type == "call" and _gkind(call, src, lang) == "doc":
                s = _first_of(call, {"quoted_content"})
                return _text(s, src).strip() if s is not None else ""
            prev = prev.prev_named_sibling
        return ""
    prev = node.prev_named_sibling
    while prev is not None and prev.type in _SKIP_ABOVE:
        prev = prev.prev_named_sibling
    if prev is None and node.parent is not None and node.parent.type == "body_statement":
        prev = node.parent.prev_named_sibling       # Ruby: a class's first member's comment
    comments = []
    while prev is not None and prev.type in SHAPES[lang]["comment"]:
        comments.append(_text(prev, src))
        prev = prev.prev_named_sibling
    return _clean_doc(comments)


def _kanno(anno, scope, src: bytes) -> dict:
    """A Kotlin annotation. `scope` holds its argument when the grammar put it beside it."""
    ut = _first_of(anno, {"user_type"})
    idents = [c for c in (ut.named_children if ut is not None else []) if c.type in _KT_NAMES]
    arg = _first_string(anno, src)
    if not arg and scope is not anno:
        for c in scope.named_children:
            if c.type not in ("annotation", "annotated_expression"):
                arg = _first_string(c, src) or arg
    return {"name": _text(idents[-1], src) if idents else "", "arg": arg, "text": _text(anno, src)}


def _gannos(node, src: bytes, lang: str) -> list[dict]:
    """Annotations/attributes on a declaration: name, first string argument, text."""
    out: list[dict] = []
    if lang == "kotlin":
        for a in _walk(_child(node, {"modifiers"}), {"annotation"}) if _child(node, {"modifiers"}) else []:
            out.append(_kanno(a, a, src))
        # A class's annotations before `class` parse as a sibling expression.
        prev = node.prev_named_sibling
        while prev is not None and prev.type == "annotated_expression":
            for scope in [prev] + list(_walk(prev, {"annotated_expression"})):
                out += [_kanno(a, scope, src) for a in scope.named_children if a.type == "annotation"]
            prev = prev.prev_named_sibling
    elif lang == "rust":
        prev = node.prev_named_sibling
        while prev is not None and prev.type in ("attribute_item", "line_comment", "block_comment"):
            attr = _child(prev, {"attribute"}) if prev.type == "attribute_item" else None
            ident = _child(attr, {"identifier", "scoped_identifier"})
            if ident is not None:
                out.append({"name": _text(ident, src).split("::")[-1],
                            "arg": _first_string(attr, src), "text": _text(attr, src)})
            prev = prev.prev_named_sibling
    return out


def _gbases(node, src: bytes, lang: str) -> list[str]:
    out: list[str] = []
    for child in _walk(node, _G_BASES.get(lang, set()), stop=_BODY_TYPES | {"do_block"}):
        for part in re.split(r"[,\s:<>()]+", _text(child, src)):
            base = _base_type(part)
            if base and base not in _BASE_WORDS and base not in out:
                out.append(base)
    return out


def _gmethod(node, src: bytes, lang: str, fields: dict[str, str], prefix: str) -> dict:
    """One method/function record, in `_method`'s shape."""
    name_node = _gname_node(node, src, lang)
    params = _gparams(node, src, lang)
    body = _gmbody(node, lang)
    types = dict(fields)
    types.update(params)
    if body is not None:
        types.update(_glocals(_text(body, src), lang))
    annos = _gannos(node, src, lang)
    routes = []
    if lang == "kotlin":
        routes = _method_routes(annos, prefix, "java")
    entry = {
        "name": _text(name_node, src).split("::")[-1],
        "doc": _gdoc(node, src, lang),
        "line": _line(name_node),
        "endLine": _end_line(body if lang == "dart" and body is not None else node),
        "params": params,
        "calls": _dedupe_calls(_gresolve(_gcalls(body, src, lang), types)),
        "routes": routes,
        "http": [],
    }
    if body is None and lang not in ("ruby", "elixir"):
        entry["declaration"] = True               # an interface / abstract / trait signature
    return entry


def _gclass(node, src: bytes, lang: str, is_method) -> dict | None:
    name_node = _gname_node(node, src, lang)
    if name_node is None:
        return None
    name = _text(name_node, src)
    annos = _gannos(node, src, lang)
    prefix = _class_prefix(annos, "java", name) if lang == "kotlin" else ""
    fields = _gfields(node, src, lang)
    body = _gbody(node, lang)
    methods = [_gmethod(m, src, lang, fields, prefix)
               for m in (body.named_children if body is not None else [])
               if is_method(m) and _gname_node(m, src, lang) is not None]
    return {"name": name, "bases": _gbases(node, src, lang),
            "decorators": [a["name"] for a in annos if a["name"]],
            "doc": _gdoc(node, src, lang), "line": _line(name_node), "endLine": _end_line(node),
            "fields": fields, "methods": methods}


def _generic(root, src: bytes, lang: str) -> tuple[list[dict], list[dict], list[dict]]:
    """(classes, functions, routes) for one file of a SHAPES language."""
    shape = SHAPES[lang]

    def is_container(n) -> bool:
        return _gkind(n, src, lang) in shape["container"]

    def is_method(n) -> bool:
        return _gkind(n, src, lang) in shape["method"]

    classes: list[dict] = []
    by_name: dict[str, dict] = {}

    def containers(node) -> None:
        for child in node.named_children:
            if is_container(child):
                rec = _gclass(child, src, lang, is_method)
                if rec is not None:
                    classes.append(rec)
                    by_name.setdefault(rec["name"], rec)
                body = _gbody(child, lang)
                if body is not None:
                    containers(body)                    # a nested class
            elif not is_method(child):
                containers(child)

    functions: list[dict] = []
    routes: list[dict] = []

    def attach(holder: str, m) -> None:
        rec = by_name.get(holder)
        entry = _gmethod(m, src, lang, rec["fields"] if rec else {}, "")
        (rec["methods"] if rec else functions).append(entry)

    def free(node) -> None:
        for child in node.named_children:
            if is_container(child):
                continue
            if lang == "rust" and child.type == "impl_item":
                # `impl Store { fn save(&self) }` -- methods of a type declared elsewhere
                # in the file. A type from another file keeps its methods as functions,
                # the rule Go's receivers already follow.
                holder = _base_type(_field_text(child, "type", src))
                trait = _base_type(_field_text(child, "trait", src))
                if trait and holder in by_name and trait not in by_name[holder]["bases"]:
                    by_name[holder]["bases"].append(trait)
                body = _field(child, "body")
                for m in body.named_children if body is not None else []:
                    if is_method(m) and _gname_node(m, src, lang) is not None:
                        attach(holder, m)
            elif is_method(child):
                name_node = _gname_node(child, src, lang)
                if name_node is None:
                    continue
                qualified = _text(name_node, src)
                if lang == "cpp" and "::" in qualified:          # int Store::save() {...}
                    attach(qualified.split("::")[-2], child)
                    continue
                entry = _gmethod(child, src, lang, {}, "")
                annos = _gannos(child, src, lang) if lang == "rust" else []
                for a in annos:                                  # #[post("/widgets")] async fn h
                    if a["name"] in RUST_VERBS and a["arg"]:
                        routes.append({"method": a["name"].upper(), "path": _join_path("", a["arg"]),
                                       "handler": entry["name"], "line": entry["line"],
                                       "endLine": entry["endLine"], "doc": entry["doc"]})
                functions.append(entry)
            else:
                free(child)

    containers(root)
    free(root)
    return classes, functions, routes


def _imports(root, src: bytes, lang: str) -> list[dict]:
    out = []
    for node in _walk(root, IMPORT_TYPES[lang]):
        dotted = _text(node, src)
        dotted = re.sub(r"^(?:import|using)\s+(?:static\s+)?", "", dotted).strip().rstrip(";").strip()
        if dotted:
            out.append({"from": dotted, "names": [dotted.split(".")[-1]]})
    return out


# ---------------------------------------------------------------------------
# Public interface -- unchanged from the extractor this replaces
# ---------------------------------------------------------------------------
_warned: set[str] = set()


def extract_file(path: str) -> dict | None:
    lang = LANG_EXTS.get(os.path.splitext(path)[1].lower())
    if lang is None:
        return None
    parser = grammars.parser_for(lang)
    if parser is None:
        if lang not in _warned:
            _warned.add(lang)
            # A runtime that will not load is a different failure from a grammar
            # that was never installed, and the fixes are different too. Saying
            # "no grammar installed" to someone whose grammar is right there
            # sends them to reinstall what they already have.
            broken = grammars.runtime_error()
            if broken:
                # One runtime, one message: it is the same sentence for every
                # language, and repeating it per language reads like three
                # separate faults.
                if "" not in _warned:
                    _warned.add("")
                    langs = ", ".join(sorted(LANG_EXTS.values()))
                    print(f"  ! {langs} skipped: {broken}", file=sys.stderr)
            else:
                hint = grammars.install_hint([lang])
                print(f"  ! {lang} skipped: no tree-sitter grammar installed."
                      f" Run `{hint}` to enable it.", file=sys.stderr)
        return None
    try:
        with open(path, "rb") as fh:
            src = fh.read()
    except OSError as exc:
        print(f"  ! skipped {path}: {exc}", file=sys.stderr)
        return None

    root = parser.parse(src).root_node
    if lang in SHAPES:
        classes, functions, routes = _generic(root, src, lang)
        imports: list[dict] = []        # the graphs resolve through declared types, not imports
    else:
        classes, functions = _containers(root, src, lang)
        routes = _go_routes(root, src) if lang == "go" else []
        imports = _imports(root, src, lang)
    return {"file": path, "lang": lang, "imports": imports,
            "classes": classes, "functions": functions, "routes": routes}


def find_lang_files(root: str) -> list[str]:
    """Every Java/Go/C# file under `root`, in a fixed order (constraint 2)."""
    out: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for fn in sorted(names):
            if os.path.splitext(fn)[1].lower() in LANG_EXTS:
                out.append(os.path.join(dirpath, fn))
    return out


def extract_lang_files(paths: list[str]) -> list[dict]:
    """One record per file, mirroring the interface both graph builders expect."""
    return [rec for rec in (extract_file(p) for p in sorted(paths)) if rec]


def skipped_languages(paths) -> list[str]:
    """Languages present in `paths` whose grammar is not installed."""
    seen = {LANG_EXTS[os.path.splitext(p)[1].lower()]
            for p in paths if os.path.splitext(p)[1].lower() in LANG_EXTS}
    return grammars.missing(seen)


def main(argv=None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(
        description="Java/Go/C# extraction via tree-sitter (debugging aid; the graph builders call this as a library).")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    args = parser.parse_args(argv)
    records = []
    for root in args.src:
        records += extract_lang_files(find_lang_files(os.path.abspath(root)))
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
