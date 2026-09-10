#!/usr/bin/env python3
"""ts_extract.py — Java/Go/C# declarations and calls, read from a real parse tree.

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

LANG_EXTS = {".java": "java", ".go": "go", ".cs": "csharp"}
SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data", "dist", "build"}

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
        if lang == "java":
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
    if lang == "java":
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
        routes.append({"method": verb or "ANY", "path": path, "handler": handler,
                       "line": _line(call),
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


IMPORT_TYPES = {"java": {"import_declaration"}, "csharp": {"using_directive"}, "go": set()}


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
    classes, functions = _containers(root, src, lang)
    routes = _go_routes(root, src) if lang == "go" else []
    return {"file": path, "lang": lang, "approx": True,
            "imports": _imports(root, src, lang),
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
