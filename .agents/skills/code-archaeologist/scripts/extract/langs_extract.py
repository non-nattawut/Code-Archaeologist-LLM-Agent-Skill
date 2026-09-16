#!/usr/bin/env python3
"""langs_extract.py — declarations and calls for thirteen languages, read from a real parse tree.

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

import call_ctx  # noqa: E402  (where a call is written: line, loop, branch)
import doc_text  # noqa: E402  (the one doc-comment rule, shared with every producer)
import grammars  # noqa: E402

LANG_EXTS = {".java": "java", ".go": "go", ".cs": "csharp",
             # Phase 7 -- read by SHAPES below (Groovy by Java's branch).
             ".kt": "kotlin", ".kts": "kotlin", ".rs": "rust", ".swift": "swift",
             ".scala": "scala", ".groovy": "groovy", ".dart": "dart",
             ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp",
             ".rb": "ruby", ".php": "php", ".ex": "elixir", ".exs": "elixir"}
# Languages whose tree is Java's: same node types, same fields, same branch.
JAVA_LIKE = {"java", "groovy"}
from taxonomy import framework_entry, source_dirs  # noqa: E402  (one definition of "not source")

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
    """The first line of a declaration, its annotations and attributes included.

    Until finding #6 this was the line of the `name` field, so a Spring or ASP.NET
    method's range started *below* `@PostMapping` / `[HttpPost]` -- the very lines
    that route and guard it -- while a decorated TS method's started at its first
    decorator. One rule now, in every language: a node's range covers everything it
    owns, so a finding on an annotation line is attributed to the method it annotates.
    Java and C# keep annotations and attributes inside the declaration node, so its
    own start is that line.
    """
    return _line(node)


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


# ---------------------------------------------------------------------------
# Overloads -- parameter kinds on declarations, argument kinds on calls
# ---------------------------------------------------------------------------
# These languages let one class define a name more than once, and every overload is
# its own node (`build_flow._local_names`). So each method records its parameter
# types twice over -- `sig` for its id, `kinds` to match a call against -- and each
# call its argument kinds. Until this, an overload set was one node carrying every
# overload's calls but one overload's range (finding #8). No other language needs it.
OVERLOADING = {"java", "groovy", "csharp", "kotlin", "scala", "swift", "cpp"}

_PRIMITIVES = {
    "#int": {"int", "long", "short", "byte", "integer", "int16", "int32", "int64", "uint", "ulong",
             "ushort", "sbyte", "uint16", "uint32", "uint64", "size_t", "unsigned"},
    "#float": {"float", "double", "decimal"},
    "#string": {"string"},
    "#bool": {"bool", "boolean"},
    "#char": {"char", "character"},
}


def _kind_of_type(text: str) -> str:
    """A declared type as calls are matched against it.

    A primitive family (`int`, `Int` and `Int32` are all `#int`), else the plain type
    name, else "*" -- an array, pointer, generic, function type or nothing readable,
    which accepts any argument rather than risk refusing the right overload.
    """
    m = re.fullmatch(r"\s*(?:const\s+)?([\w.:]+)\s*\??\s*", text or "")
    if not m:
        return "*"
    base = m.group(1).replace("::", ".").split(".")[-1]
    for kind, names in _PRIMITIVES.items():
        if base.lower() in names:
            return kind
    return base


def _sig_type(text: str) -> str:
    """A declared type as it is spelled in an overloaded node's id.

    `List<String>` -> `List`, `java.util.Map` -> `Map`, `char*` -> `charPtr`,
    `String...` -> `String[]`, nothing readable -> `_`. Every id is also a note's file
    name, so nothing Windows forbids in one (`<>:"/\\|?*`) may survive.
    """
    t = (text or "").replace("...", "[]")
    while True:
        stripped = re.sub(r"<[^<>]*>", "", t)
        if stripped == t:
            break
        t = stripped
    t = re.sub(r"\b(?:const|final|volatile)\b", "", t).replace("::", ".")
    t = re.sub(r"\w+\.", "", t)                          # namespaces and packages
    t = t.replace("*", "Ptr").replace("?", "Opt")
    return re.sub(r'[\s<>:"/\\|]', "", t) or "_"


_LITERAL_KINDS = {
    **dict.fromkeys(("decimal_integer_literal", "hex_integer_literal", "octal_integer_literal",
                     "binary_integer_literal", "integer_literal", "long_literal", "hex_literal",
                     "bin_literal", "oct_literal"), "#int"),
    **dict.fromkeys(("decimal_floating_point_literal", "hex_floating_point_literal",
                     "real_literal", "floating_point_literal"), "#float"),
    **dict.fromkeys(("string_literal", "text_block", "verbatim_string_literal", "raw_string_literal",
                     "interpolated_string_expression", "line_string_literal",
                     "multi_line_string_literal", "string", "concatenated_string"), "#string"),
    **dict.fromkeys(("true", "false", "boolean_literal"), "#bool"),
    **dict.fromkeys(("character_literal", "char_literal"), "#char"),
}


def _arg_nodes(call, lang: str) -> list:
    """A call's argument expressions, in order."""
    if lang in ("kotlin", "swift"):
        # Swift wraps the arguments in a `call_suffix`; the pinned Kotlin grammar puts
        # `value_arguments` straight under the call (found by r33: every Kotlin call
        # read as zero arguments, so no overload ever matched).
        holder = _child(call, {"call_suffix"}) or call
        args = _child(holder, {"value_arguments"})
        out = [a.named_children[-1] for a in (args.named_children if args is not None else [])
               if a.type == "value_argument" and a.named_children]
        trailing = _child(holder, {"annotated_lambda", "lambda_literal"})
        return out + ([trailing] if trailing is not None else [])
    args = _field(call, "arguments")
    out = [a for a in (args.named_children if args is not None else []) if "comment" not in a.type]
    if lang == "csharp":                                 # `argument` wraps the expression
        out = [a.named_children[-1] if a.type == "argument" and a.named_children else a for a in out]
    return out


def _arg_kinds(call, src: bytes, lang: str, types: dict[str, str]) -> list[str]:
    """Each argument's kind, or "" where the source does not state it.

    Stated means a literal, `new X(...)`, or a name whose declared type is already in
    `types` -- the same fields, parameters and locals the receiver resolver reads.
    """
    out = []
    for a in _arg_nodes(call, lang):
        if a.type == "number_literal":                   # C++: one node for every number
            text = _text(a, src).lower()
            out.append("#int" if text.startswith("0x") or not re.search(r"[.e]", text) else "#float")
        elif a.type in _LITERAL_KINDS:
            out.append(_LITERAL_KINDS[a.type])
        elif a.type in ("identifier", "simple_identifier"):
            declared = types.get(_text(a, src), "")
            out.append(_kind_of_type(declared) if declared else "")
        elif a.type == "object_creation_expression":
            declared = _base_type(_field_text(a, "type", src))
            out.append(_kind_of_type(declared) if declared else "")
        else:
            out.append("")
    return out


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
    return doc_text.clean(comments, xml=True)


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


def _param_pairs(params, src: bytes, lang: str):
    """(name, declared type text) for each parameter in a parameter list, in order."""
    if params is None:
        return
    for p in params.named_children:
        if p.type not in SPEC[lang]["param"]:
            continue
        name = _field_text(p, "name", src)
        declared = _field_text(p, "type", src)
        if p.type == "spread_parameter":
            # Java's `String... parts` has no fields: a type, then a declarator.
            kids = p.named_children
            declared = _text(kids[0], src) + "..." if kids else ""
            name = next((_field_text(k, "name", src) for k in kids if k.type == "variable_declarator"), "")
        if lang == "csharp" and not declared:
            # C# writes `Type name` with both as fields; older grammars label the
            # type only positionally, so fall back to the first named child.
            kids = [c for c in p.named_children if c.type != "attribute_list"]
            declared = _text(kids[0], src) if len(kids) > 1 else ""
            name = name or (_text(kids[-1], src) if kids else "")
        yield name, declared


def _params_of(params, src: bytes, lang: str) -> dict[str, str]:
    """The same, given the parameter list itself -- Go's receiver is one of these."""
    out: dict[str, str] = {}
    for name, declared in _param_pairs(params, src, lang):
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
        if call.type == "method_reference":            # this::clear, Store::save, store::put
            parts = call.named_children
            if len(parts) < 2 or parts[-1].type != "identifier":
                return "", ""                          # Store::new -- a constructor, not a node
            return _text(parts[0], src), _text(parts[-1], src)
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


def _type_name(head: str) -> str:
    """A receiver that is a type name is that type: `DateUtil.now()`, `Widget::new`.

    Only a *candidate* -- build_flow still requires that the graph has the class and
    that it defines the method, so `Math.max()` and `Console.WriteLine()` drop as before.
    """
    return head if re.fullmatch(r"[A-Z]\w*", head) else ""


def _receiver_node(call, lang: str):
    """The expression a call is made on, as a node -- what `_receiver_and_name` reads as text."""
    if lang in JAVA_LIKE:
        return _field(call, "object") if call.type != "method_reference" else None
    fn = _field(call, "function")
    if fn is None:
        return None
    if lang == "csharp" and fn.type == "member_access_expression":
        return _field(fn, "expression")
    if fn.type == "selector_expression":                      # go
        return _field(fn, "operand")
    return None


def _typed_call(call, src: bytes, lang: str, types: dict[str, str], recv_name: str = ""):
    """(receiver type, name, via) for one call site, or None to skip it.

    `via` is set when the receiver is itself a call -- `resolveHandler(t).downloadFile()`:
    {"type": the innermost call's receiver type, "names": the calls from there outward}.
    The type is then "?" and build_flow walks the declared return types. Splitting the
    receiver's text could not: `resolve(a.b)` holds a dot inside its parentheses.
    """
    recv, name = _receiver_and_name(call, src, lang)
    if not name or not re.fullmatch(r"[A-Za-z_]\w*", name):
        return None
    inner = _receiver_node(call, lang)
    if (inner is not None and inner.type == "parenthesized_expression" and inner.named_child_count == 1
            and inner.named_children[0].type == "cast_expression"):
        # `((UserSecurity) userDetails).getPlantIds()`: the cast states the receiver's type.
        cast = _base_type(_field_text(inner.named_children[0], "type", src))
        return (cast or "?"), name, None
    if inner is not None and inner.type in SPEC[lang]["call"]:
        got = _typed_call(inner, src, lang, types, recv_name)
        if got is None:
            return "?", name, None
        itype, iname, ivia = got
        via = ({**ivia, "names": ivia["names"] + [iname]} if ivia
               else {"type": itype, "names": [iname]})
        return "?", name, via
    recv = recv.replace(" ", "")
    parts = recv.split(".")
    head = parts[0]
    if not recv or (head in SELF_WORDS and len(parts) == 1):
        return "", name, None                             # bare, or `this.m()`: same class
    resolved = ""
    if len(parts) == 1:
        # Go is left out: a capitalised Go head is an exported package-level
        # value as often as a type, and its packages are lowercase anyway.
        resolved = types.get(head, "") or ("" if lang == "go" else _type_name(head))
    elif len(parts) == 2 and (head in SELF_WORDS or head == recv_name):
        resolved = types.get(parts[1], "")                # this.field.m() / r.field.m()
    elif len(parts) == 2 and head not in types and lang != "go" and _type_name(head):
        # `Registry.STORE.save()`: typed by the static field's declared type, in build_flow
        return "?", name, {"type": head, "fields": [parts[1]], "names": []}
    return resolved or "?", name, None


def _calls(body, src: bytes, lang: str, types: dict[str, str], recv_name: str = "",
           qualifiers: dict[str, str] | None = None) -> list[dict]:
    """Call sites in a body, with the receiver resolved to a declared type.

    `qualifiers` maps a field or parameter to its Spring `@Qualifier`; a call through one
    carries it, so build_flow can tell which bean is injected there.
    """
    out: list[dict] = []
    if body is None:
        return out
    # A method reference hands a method to someone who calls it (`schedule(this::clearBin)`);
    # its receiver is stated as plainly as a call's, so it resolves the same way.
    kinds = SPEC[lang]["call"] | ({"method_reference"} if lang in JAVA_LIKE else set())
    for call in _walk(body, kinds):
        got = _typed_call(call, src, lang, types, recv_name)
        if got is None:
            continue
        typ, name, via = got
        entry = {"type": typ, "name": name, **call_ctx.site(call, body)}
        if via:
            entry["via"] = via
        if qualifiers:
            parts = _receiver_and_name(call, src, lang)[0].replace(" ", "").split(".")
            held = parts[1] if len(parts) == 2 and parts[0] in SELF_WORDS else parts[0] if len(parts) == 1 else ""
            if held in qualifiers:
                entry["qualifier"] = qualifiers[held]
        if lang in OVERLOADING and call.type != "method_reference":
            # A reference has no argument list, so an overloaded target stays ambiguous.
            entry["args"] = [_arg_kinds(call, src, lang, types)]
        out.append(entry)
    return out


MAPSTRUCT_EXPRESSIONS = {"expression", "defaultExpression", "conditionExpression"}
JAVA_EXPRESSION_RE = re.compile(r"\s*java\((.*)\)\s*", re.S)


def _expression_calls(node, src: bytes, types: dict[str, str], recv_name: str = "") -> list[dict]:
    """Calls inside MapStruct's `@Mapping(expression = "java(toDisplayName(item.getName()))")`.

    The generated mapper runs that Java, so a helper used only there looked dead. The string
    is parsed as Java and read exactly like a body, with the method's parameters in scope.
    """
    mods = next((c for c in node.named_children if c.type == "modifiers"), None)
    parser = grammars.parser_for("java") if mods is not None else None
    out: list[dict] = []
    for pair in _walk(mods, {"element_value_pair"}) if parser is not None else []:
        value = _field(pair, "value")
        if _field_text(pair, "key", src) not in MAPSTRUCT_EXPRESSIONS or value is None \
                or value.type != "string_literal":
            continue
        m = JAVA_EXPRESSION_RE.fullmatch(_text(value, src)[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        if m:
            code = f"class M {{ Object m() {{ return {m.group(1)}; }} }}".encode()
            # The snippet's rows are not the file's: the call is written on the annotation's line,
            # and a branch's position inside the snippet names no place in the file.
            out += [{**{k: v for k, v in c.items() if k != "arms"}, "line": _line(value)}
                    for c in _calls(parser.parse(code).root_node, code, "java", types, recv_name)]
    return out


def _dedupe_calls(calls: list[dict]) -> list[dict]:
    """One entry per (receiver type, name); every distinct argument list is kept, and the
    sites are folded by `call_ctx.merge` (first line, loop if any, branch only if all).

    The key is unchanged, so a language without overloads gets exactly the list it
    always did. `args` only matters when the name is an overload set: `f(a)` and
    `f(a, b)` in one body are calls to two different nodes.
    """
    merged: dict[tuple, dict] = {}
    for c in calls:
        # A call on another call's result is keyed by its chain too: `a().run()` and
        # `b().run()` walk different return types.
        via = c.get("via")
        key = (c["type"], c["name"],
               (via["type"], tuple(via.get("fields", ())), tuple(via["names"])) if via else (),
               c.get("qualifier", ""))
        if key in merged:
            entry = call_ctx.merge(merged[key], c)
        else:
            entry = merged[key] = {"type": c["type"], "name": c["name"], **({"via": via} if via else {}),
                                   **({"qualifier": c["qualifier"]} if c.get("qualifier") else {}),
                                   **call_ctx.facts(c)}
        for args in c.get("args", []):
            if args not in entry.setdefault("args", []):
                entry["args"].append(args)
    out = [merged[k] for k in sorted(merged)]
    for entry in out:
        if "args" in entry:
            entry["args"].sort()
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
def _return_type(node, src: bytes, lang: str) -> str:
    """The class a method's declared return type names, or "" -- read so a call on its
    result (`resolveHandler(t).downloadFile()`) can be typed. Java/Groovy say `type`,
    C# `returns`, Kotlin puts it after the parameter list with no field name at all."""
    declared = ""
    if lang in JAVA_LIKE:
        declared = _field_text(node, "type", src)
    elif lang == "csharp":
        declared = _field_text(node, "returns", src) or _field_text(node, "type", src)
    elif lang == "kotlin":
        after = False
        for child in node.named_children:
            if child.type == "function_value_parameters":
                after = True
            elif after and child.type in _KT_TYPES:
                declared = _text(child, src).rstrip("?")
                break
            elif after and child.type == "function_body":
                break
    return _base_type(declared) if declared else ""


LOMBOK_ALL_GETTERS = {"Data", "Getter", "Value"}


def _lombok_getters(container, annos: list[dict], fields: dict[str, str], src: bytes, lang: str) -> dict[str, str]:
    """Getter name -> the field's type, for accessors Lombok generates.

    They have no source, so they are never nodes; they are only a step in a chain like
    `props.getPnoData().validate()`, typed by the field they read.
    """
    everywhere = any(a["name"] in LOMBOK_ALL_GETTERS for a in annos)
    body = _field(container, "body")
    out: dict[str, str] = {}
    for f in _walk(body, SPEC[lang]["field"], stop=SPEC[lang]["method"]) if body is not None else []:
        if not everywhere and not any(a["name"] == "Getter" for a in _annotations(f, src, lang)):
            continue
        for d in f.named_children:
            name = _field_text(d, "name", src) if d.type == "variable_declarator" else ""
            if name in fields:
                out["get" + name[:1].upper() + name[1:]] = fields[name]
    return out


def _override_modifier(node, src: bytes) -> bool:
    """`override` said as a modifier (C#, Kotlin, Swift, Scala) rather than `@Override`."""
    return any(child.type in ("modifier", "modifiers") and re.search(r"\boverride\b", _text(child, src))
               for child in node.children)


def _method(node, src: bytes, lang: str, fields: dict[str, str],
            prefix: str, recv_name: str = "", module: dict[str, str] | None = None,
            qualifiers: dict[str, str] | None = None) -> dict:
    """One method/function record, shaped exactly like the textual extractor's.

    `module` is a Go file's typed package-level vars, hidden by a parameter or local of
    the same name; `qualifiers` a Java class's `@Qualifier`-annotated fields.
    """
    params = _params(node, src, lang)
    body = _field(node, "body")
    hidden = _declared_names(node, body, src, lang) if module else set()
    types = {k: v for k, v in (module or {}).items() if k not in hidden}
    types.update(fields)
    types.update(params)
    if body is not None:
        types.update(_tree_locals(body, src, lang))
        types.update(_locals(_text(body, src), lang))
    annos = _annotations(node, src, lang)
    if lang in JAVA_LIKE:
        qualifiers = {**(qualifiers or {}), **_param_qualifiers(_field(node, "parameters"), src, lang)}
    entry = {
        "name": _field_text(node, "name", src),
        "doc": _doc_above(node, src, lang),
        "line": _decl_line(node),
        "endLine": _end_line(node),
        "params": params,
        "calls": _dedupe_calls(_calls(body, src, lang, types, recv_name, qualifiers)
                               + (_expression_calls(node, src, types, recv_name) if lang in JAVA_LIKE else [])),
        "routes": _method_routes(annos, prefix, lang),
        "http": [],
    }
    returns = _return_type(node, src, lang)
    if returns:
        entry["returns"] = returns
    refs = _type_refs(node, src, lang)              # structure references, never call edges
    if refs:
        entry["refs"] = refs
    if body is None:
        # No `body` field at all: an interface member or an `abstract` method.
        # tree-sitter states this outright -- no pattern, no false positives.
        entry["declaration"] = True
    why = framework_entry([a["name"] for a in annos], entry["name"], _override_modifier(node, src))
    if not why and lang == "go" and entry["name"] == "init" and _field(node, "receiver") is None:
        why = "init"                              # Go runs every package's `func init()` itself
    if why:
        entry["entry"] = why
    bean = _bean_method(annos, body, entry["name"], src) if lang in JAVA_LIKE else None
    if bean:
        entry["bean"] = bean
    if lang in OVERLOADING:
        _overload_keys(entry, [d for _, d in _param_pairs(_field(node, "parameters"), src, lang)])
    return entry


def _declared_names(node, body, src: bytes, lang: str) -> set[str]:
    """Every name a function's parameters or body declare: what hides a package-level var."""
    names = {n for n, _ in _param_pairs(_field(node, "parameters"), src, lang)}
    for d in _walk(body, {"short_var_declaration", "var_spec", "range_clause"}) if body is not None else []:
        target = d if d.type == "var_spec" else _field(d, "left")
        names |= {_text(i, src) for i in (target.named_children if target is not None else [])
                  if i.type == "identifier"}
    return names


GO_VALUE_RE = re.compile(r"^&?(?:\w+\.)?(\w+)\s*\{|^(?:\w+\.)?New(\w+)\s*\(")


def _go_package_vars(root, src: bytes) -> dict[str, str]:
    """A Go file's package-level `var x *Store` / `var x = &Store{}` / `var x = NewStore()`."""
    out: dict[str, str] = {}
    for decl in (c for c in root.named_children if c.type == "var_declaration"):
        for spec in _walk(decl, {"var_spec"}):
            m = GO_VALUE_RE.match(_field_text(spec, "value", src).strip())
            declared = _base_type(_field_text(spec, "type", src)) or (m and (m.group(1) or m.group(2))) or ""
            for ident in (c for c in spec.named_children if c.type == "identifier"):
                if declared:
                    out[_text(ident, src)] = declared
    return out


# --- Spring: what the source says about which bean is injected --------------------
SPRING_STEREOTYPES = {"Component", "Service", "Repository", "Controller", "RestController", "Configuration"}
INIT_BLOCKS = {"static_initializer", "block"}        # Java's `static { }` and `{ }` in a class body


def _qualifier(annos: list[dict]) -> str:
    return next((a["arg"] for a in annos if a["name"] == "Qualifier" and a["arg"]), "")


def _bean_flags(annos: list[dict]) -> dict:
    return {"primary": any(a["name"] == "Primary" for a in annos),
            "conditional": any(a["name"] == "Profile" or a["name"].startswith("Conditional") for a in annos)}


def _spring_bean(annos: list[dict], cls_name: str) -> dict | None:
    """A class Spring creates: its bean names (`@Service("x")`, else the class name with a
    lowercase first letter, plus a class `@Qualifier`), `@Primary`, and whether it is
    conditional (`@Profile`, `@Conditional...`)."""
    stereo = next((a for a in annos if a["name"] in SPRING_STEREOTYPES), None)
    if stereo is None:
        return None
    default = cls_name if cls_name[:2].isupper() else cls_name[:1].lower() + cls_name[1:]
    return {"names": sorted({stereo["arg"] or default} | ({_qualifier(annos)} - {""})), **_bean_flags(annos)}


def _bean_of(annos: list[dict], name: str, built: set[str]) -> dict | None:
    """The bean a `@Bean` method or function registers, when it builds exactly one class."""
    bean = next((a for a in annos if a["name"] == "Bean"), None)
    built = built - {""}
    if bean is None or len(built) != 1:
        return None
    return {"builds": built.pop(), "names": sorted({bean["arg"] or name} | ({_qualifier(annos)} - {""})),
            **_bean_flags(annos)}


def _bean_method(annos: list[dict], body, name: str, src: bytes) -> dict | None:
    """A `@Bean` method that builds exactly one class (`return new SmtpMailer();`)."""
    if body is None or not any(a["name"] == "Bean" for a in annos):
        return None
    return _bean_of(annos, name, {_base_type(_field_text(n, "type", src))
                                  for r in _walk(body, {"return_statement"})
                                  for n in _walk(r, {"object_creation_expression"})})


def _param_qualifiers(params, src: bytes, lang: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in params.named_children if params is not None else []:
        if p.type in SPEC[lang]["param"]:
            q = _qualifier(_annotations(p, src, lang))
            if q:
                out[_field_text(p, "name", src)] = q
    return out


def _field_qualifiers(container, src: bytes, lang: str) -> dict[str, str]:
    """Field or constructor-parameter name -> its `@Qualifier`, for one class."""
    out: dict[str, str] = {}
    body = _field(container, "body")
    for f in _walk(body, SPEC[lang]["field"], stop=SPEC[lang]["method"]) if body is not None else []:
        q = _qualifier(_annotations(f, src, lang))
        for d in f.named_children if q else []:
            if d.type == "variable_declarator":
                out[_field_text(d, "name", src)] = q
    for ctor in _walk(body, {"constructor_declaration"}) if body is not None else []:
        out.update(_param_qualifiers(_field(ctor, "parameters"), src, lang))
    return out


def _overload_keys(entry: dict, declared: list[str]) -> None:
    """`sig` (the id suffix, used only if the name repeats) and `kinds` (to match calls)."""
    entry["sig"] = ",".join(_sig_type(d) for d in declared)
    # A trailing `T...` is kept as `...T`: it takes any number of T (build_flow._pick_overload).
    entry["kinds"] = [("..." + _kind_of_type(d[:-3])) if i == len(declared) - 1 and d.endswith("...")
                      else _kind_of_type(d) for i, d in enumerate(declared)]


_INTERFACE_NODES = {"interface_declaration", "protocol_declaration", "trait_item", "trait_definition"}
_MODIFIER_NODES = {"modifiers", "modifier", "inheritance_modifier", "abstract_modifier", "class_modifier"}


def _class_kind(node) -> str:
    """`interface`, `abstract`, or "" for a plain class -- as the declaration states it: an
    interface/trait/protocol node, Kotlin's `interface` keyword, or an `abstract` modifier
    token (never the word inside an annotation's argument)."""
    if node.type in _INTERFACE_NODES or any(c.type == "interface" for c in node.children):
        return "interface"
    stack = [c for c in node.children if c.type in _MODIFIER_NODES or c.type == "abstract"]
    while stack:
        n = stack.pop()
        if n.type == "abstract":
            return "abstract"
        stack.extend(c for c in n.children if c.type not in ("annotation", "marker_annotation"))
    return ""


_TYPED_LOCALS = {"local_variable_declaration", "enhanced_for_statement",      # Java, Groovy
                 "instanceof_expression", "type_pattern",                     # Java 16+ patterns
                 "local_declaration_statement", "foreach_statement",          # C#
                 "declaration_pattern"}                                       # C# `is T t`


def _tree_locals(body, src: bytes, lang: str) -> dict[str, str]:
    """Locals whose type is written on their declaration: `R3RequestDto request = mapper.read()`,
    `for (Item it : items)`, and a pattern variable -- `x instanceof UserSecurity us`,
    `case UserSecurity us ->`, C#'s `x is Session s`. The text rules only saw `= new X(`, so a
    local assigned from a call had no type and every call on it was dropped. `var` states
    nothing and is skipped."""
    out: dict[str, str] = {}
    if body is None or lang not in JAVA_LIKE | {"csharp"}:
        return out
    for n in _walk(body, _TYPED_LOCALS):
        if n.type == "local_variable_declaration":
            declared = _base_type(_field_text(n, "type", src))
            names = [_field_text(d, "name", src) for d in n.named_children if d.type == "variable_declarator"]
        elif n.type == "local_declaration_statement":
            decl = next((c for c in n.named_children if c.type == "variable_declaration"), None)
            declared = _base_type(_field_text(decl, "type", src)) if decl is not None else ""
            names = [_field_text(d, "name", src) for d in (decl.named_children if decl is not None else [])
                     if d.type == "variable_declarator"]
        elif n.type == "enhanced_for_statement":
            declared, names = _base_type(_field_text(n, "type", src)), [_field_text(n, "name", src)]
        elif n.type == "instanceof_expression":                 # `u instanceof UserSecurity us`
            declared, names = _base_type(_field_text(n, "right", src)), [_field_text(n, "name", src)]
        elif n.type == "type_pattern":                          # `case UserSecurity us ->`
            parts = n.named_children
            declared = _base_type(_text(parts[0], src)) if len(parts) == 2 else ""
            names = [_text(parts[-1], src)] if len(parts) == 2 and parts[-1].type == "identifier" else []
        elif n.type == "declaration_pattern":                   # C# `u is Session s`
            declared, names = _base_type(_field_text(n, "type", src)), [_field_text(n, "name", src)]
        else:                                                   # C# foreach
            declared, names = _base_type(_field_text(n, "type", src)), [_field_text(n, "left", src)]
        for name in names:
            if name and declared and declared != "var":
                out[name] = declared
    return out


# Every type one container or method *names*, for the structure map's references.
# The flow map only ever wants a receiver's class, so every declared type was reduced to
# its head (`_base_type`) and everything else was dropped: a return type was never read at
# all, and `GlobalResponse<PaginationResponse<UserResponse>>` yielded one name of three.
# On a real repository that left 22 classes "referenced by nothing" while their names were
# written in the signatures -- which is exactly what an IDE counts as a usage (r73).
_TYPE_NODES = frozenset({"type_identifier", "scoped_type_identifier", "user_type", "generic_name"})
# The two shapes that name a type outside a type position: `SocketConstant.MAX` reads a
# constant off a class, and C# spells `X.class` this way too.
_QUALIFIED = {"field_access": "object", "member_access_expression": "expression"}


def _type_refs(node, src: bytes, lang: str) -> list[str]:
    """Type names stated anywhere in `node`: fields, parameters, return types, generic
    arguments, locals, `X.class`, and the class a static constant is read from."""
    names: set[str] = set()

    def add(text: str, capitalised: bool = False) -> None:
        base = _base_type(text)
        if base and (not capitalised or re.fullmatch(r"[A-Z]\w*", base)):
            names.add(base)

    def walk(n) -> None:
        if n.type in _TYPE_NODES:
            add(_text(n, src))                       # the head; arguments are nested nodes
        elif n.type == "identifier" and n.parent is not None and n.parent.type == "type_argument_list":
            add(_text(n, src))                       # C# states a generic argument as a plain identifier
        elif n.type in _QUALIFIED and lang != "go":
            # Capitalised only, as `_type_name` requires of a receiver -- and not in Go,
            # where a capitalised head is as often an exported value as a type.
            obj = _field(n, _QUALIFIED[n.type])
            if obj is not None and obj.type == "identifier":
                add(_text(obj, src), capitalised=True)
        for child in n.named_children:
            walk(child)

    walk(node)
    return sorted(names)


def _bases(node, src: bytes, lang: str) -> list[str]:
    out = []
    for child in node.named_children:
        if child.type in SPEC[lang]["bases"]:
            for part in re.split(r"[,\s]+", _text(child, src)):
                part = _base_type(re.sub(r"^(?:implements|extends|:)$", "", part))
                if part and part not in ("implements", "extends"):
                    out.append(part)
    return [b for b in out if b]


def _containers(root, src: bytes, lang: str) -> tuple[list[dict], list[dict], list[dict]]:
    """(classes, functions, calls made outside any class) for one file."""
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
                    **({"kind": "interface"} if shape.type == "interface_type" else {}),
                }
        # A package-level var types its name in every function (finding #27), and the calls
        # in its value run when the package loads (finding #28).
        package_vars = _go_package_vars(root, src)
        inits = [c for decl in root.named_children if decl.type == "var_declaration"
                 for c in _calls(decl, src, lang, package_vars)]
        functions = []
        for fn in _walk(root, {"method_declaration", "function_declaration"}):
            recv = _field(fn, "receiver")
            if recv is None:
                functions.append(_method(fn, src, lang, {}, "", module=package_vars))
                continue
            recv_params = _params_of(recv, src, lang)
            owner = next(iter(recv_params.values()), "")
            recv_name = next(iter(recv_params), "")
            holder = go_types.get(owner)
            fields = holder["fields"] if holder else {}
            entry = _method(fn, src, lang, fields, "", recv_name, module=package_vars)
            if holder:
                holder["methods"].append(entry)
            else:
                functions.append(entry)
        return [go_types[k] for k in sorted(go_types)], functions, _dedupe_calls(inits)

    for node in _walk(root, SPEC[lang]["container"]):
        name = _field_text(node, "name", src)
        if not name:
            continue
        annos = _annotations(node, src, lang)
        prefix = _class_prefix(annos, lang, name)
        fields = _fields(node, src, lang)
        qualifiers = _field_qualifiers(node, src, lang) if lang in JAVA_LIKE else {}
        body = _field(node, "body")
        methods = []
        inits: list[dict] = []
        if body is not None:
            for m in body.named_children:
                if m.type == "constructor_declaration" or m.type in INIT_BLOCKS or m.type in SPEC[lang]["field"]:
                    # Code that runs with no method node of its own: a constructor (not a
                    # graph node -- parity with the extractor this replaced), an initializer
                    # block, a field's initial value. Its calls mark their callees
                    # `entry: init` in build_flow (finding #28).
                    local = {**fields, **_params(m, src, lang), **_tree_locals(m, src, lang),
                             **_locals(_text(m, src), lang)}
                    inits += _calls(m, src, lang, local, "", qualifiers)
                    continue
                if m.type in SPEC[lang]["method"] and _field_text(m, "name", src):
                    methods.append(_method(m, src, lang, fields, prefix, qualifiers=qualifiers))
        cls_refs = _type_refs(node, src, lang)
        getters = _lombok_getters(node, annos, fields, src, lang) if lang in JAVA_LIKE else {}
        bean = _spring_bean(annos, name) if lang in JAVA_LIKE else None
        kind = _class_kind(node)
        classes.append({
            "name": name,
            **({"kind": kind} if kind else {}),
            "bases": _bases(node, src, lang),
            "decorators": [a["name"] for a in annos],
            "doc": _doc_above(node, src, lang),
            "line": _decl_line(node), "endLine": _end_line(node),
            "fields": fields, "methods": methods,
            # One walk of the whole class: its own signatures plus its methods' (each method
            # repeats its own, which costs a traversal and keeps both readable alone).
            **({"refs": cls_refs} if cls_refs else {}),
            **({"getters": getters} if getters else {}),
            **({"init_calls": _dedupe_calls(inits)} if inits else {}),
            **({"bean": bean} if bean else {}),
        })
    return classes, [], []


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


def _gcalls(body, src: bytes, lang: str) -> list[tuple]:
    """(receiver, name, the node the call is written at) for every call site in a body."""
    if body is None:
        return []
    if lang == "ruby":
        return [(*_grecv(call, src, lang), call) for call in _walk(body, _G_CALLS[lang])] + _rb_bare_calls(body, src)
    if lang != "dart":
        return [(*_grecv(call, src, lang), call) for call in _walk(body, _G_CALLS[lang])]
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
                    out.append((recv, _text(ident, src), kid))
            elif prev.type == "identifier" and (i == 1 or kids[i - 2].type != "selector"):
                out.append(("", _text(prev, src), kid))     # a bare call: nothing chained before it
        stack.extend(kids)
    return out


def _rb_bare_calls(body, src: bytes) -> list[tuple]:
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
            out.append(("", _text(ident, src), ident))
    return out


def _gchain(call, src: bytes, lang: str, types: dict[str, str]) -> dict | None:
    """`via` for a Kotlin call made on another call's result (`props.pnoData().validate()`),
    in `_typed_call`'s shape; None for any other call."""
    if lang != "kotlin" or not call.named_child_count:
        return None
    head = call.named_children[0]
    if head.type != "navigation_expression" or not head.named_children:
        return None
    inner = head.named_children[0]
    if inner.type != "call_expression":
        return None
    recv, name = _grecv(inner, src, lang)
    if not name:
        return {"type": "?", "names": []}
    deeper = _gchain(inner, src, lang, types)
    if deeper is not None:
        return {**deeper, "names": deeper["names"] + [name]}
    got = _gresolve([(recv, name)], types)
    if got and got[0].get("via"):                     # `Registry.STORE.find().save()`
        return {**got[0]["via"], "names": got[0]["via"]["names"] + [name]}
    return {"type": got[0]["type"] if got else "?", "names": [name]}


def _gresolve(pairs, types: dict[str, str], qualifiers: dict[str, str] | None = None) -> list[dict]:
    """`_calls`'s three-way answer, plus: a receiver that is a type name is that type. A call
    through a Kotlin property carrying `@Qualifier` names it, as `_calls` does for Java."""
    out = []
    for recv, name, *args in pairs:                  # (receiver, name[, argument kinds[, via]])
        if not name or not re.fullmatch(r"[A-Za-z_]\w*", name):
            continue
        via = args[1] if len(args) > 1 else None
        args = args[:1]
        recv = re.sub(r"\s+", "", recv).replace("?.", ".").replace("->", ".").replace("::", ".")
        recv = recv.replace("$", "").lstrip("@")
        parts = recv.split(".")
        head = parts[0]
        if not recv or (head in _G_SELF and len(parts) == 1):
            typ = ""
        else:
            resolved = ""
            if len(parts) == 1:
                resolved = types.get(head, "") or _type_name(head)
            elif len(parts) == 2 and head in _G_SELF:
                resolved = types.get(parts[1], "")
            elif len(parts) == 2 and head not in types and via is None and _type_name(head):
                via = {"type": head, "fields": [parts[1]], "names": []}   # `Registry.STORE.save()`
            typ = resolved or "?"
        entry = {"type": typ, "name": name}
        if via is not None:
            entry["type"], entry["via"] = "?", via       # typed by build_flow from return types
        if args:
            entry["args"] = [args[0]]
        if qualifiers:
            held = parts[1] if len(parts) == 2 and head in _G_SELF else (head if len(parts) == 1 else "")
            if held in qualifiers:
                entry["qualifier"] = qualifiers[held]
        out.append(entry)
    return out


def _glocals(body_text: str, lang: str) -> dict[str, str]:
    if lang == "cpp":
        return {name: t for t, name in _CPP_LOCAL.findall(body_text)}
    rx = _G_LOCALS.get(lang)
    return dict(rx.findall(body_text)) if rx is not None else {}


def _clean_doc(comments: list[str]) -> str:
    # No `xml`: these grammars write no XML doc, and the tag sweep would eat a
    # generic -- `Vec<String>` in a Rust doc comment is not markup.
    return doc_text.clean(comments)


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


# Decorations that sit *beside* a declaration in some grammars rather than inside it:
# Rust `#[...]`, Kotlin's class annotations (parsed as an expression before `class`),
# Dart's `@override`.
_DECORATION_SIBLINGS = {"attribute_item", "annotated_expression", "annotation", "marker_annotation"}


def _gstart(node) -> int:
    """A declaration's first line, decorations included (finding #6)."""
    first = node
    prev = node.prev_named_sibling
    while prev is not None and prev.type in _DECORATION_SIBLINGS:
        first = prev
        prev = prev.prev_named_sibling
    return _line(first)


def _gcall_entries(node, src: bytes, lang: str, types: dict[str, str],
                   qualifiers: dict[str, str] | None = None) -> list[dict]:
    """Every call under `node`, resolved: `_gresolve`'s entries, each with where it is written."""
    if lang in OVERLOADING and node is not None:
        found = [((*_grecv(c, src, lang), _arg_kinds(c, src, lang, types), _gchain(c, src, lang, types)), c)
                 for c in _walk(node, _G_CALLS[lang])]
    else:
        found = [((recv, name), at) for recv, name, at in _gcalls(node, src, lang)]
    return [{**entry, **call_ctx.site(at, node)}
            for pair, at in found for entry in _gresolve([pair], types, qualifiers)]


def _kt_bean_function(annos: list[dict], body, name: str, src: bytes) -> dict | None:
    """A Kotlin `@Bean` function that builds exactly one class: `= SmtpMailer()` or `return SmtpMailer()`."""
    if body is None or not any(a["name"] == "Bean" for a in annos):
        return None
    built = set()
    for scope in list(_walk(body, {"jump_expression"})) or [body]:
        for call in _walk(scope, _G_CALLS["kotlin"]):
            recv, callee = _grecv(call, src, "kotlin")
            if not recv and _type_name(callee):
                built.add(callee)
    return _bean_of(annos, name, built)


def _kt_qualifiers(node, src: bytes) -> dict[str, str]:
    """Constructor or body property name -> its `@Qualifier`, for one Kotlin class (finding #30)."""
    out: dict[str, str] = {}
    params = _child(_child(node, {"primary_constructor"}), {"class_parameters"})
    for p in params.named_children if params is not None else []:
        q = _qualifier([_kanno(a, a, src) for a in _walk(p, {"annotation"})]) if p.type == "class_parameter" else ""
        if q:
            out[_ktext(p, _KT_NAMES, src)] = q
    body = _gbody(node, "kotlin")
    for prop in _walk(body, {"property_declaration"}, SHAPES["kotlin"]["method"]) if body is not None else []:
        q = _qualifier([_kanno(a, a, src) for a in _walk(prop, {"annotation"})])
        if q:
            out[_kt_property_name(prop, src)] = q
    return out


def _kt_property_name(prop, src: bytes) -> str:
    var = _child(prop, {"variable_declaration"})
    return _ktext(var, _KT_NAMES, src) if var is not None else ""


def _kt_top_level_types(root, src: bytes) -> dict[str, str]:
    """A Kotlin file's top-level `val x: Store = ...` / `val x = Store()`: name -> type."""
    out: dict[str, str] = {}
    for prop in (c for c in root.named_children if c.type == "property_declaration"):
        name = _kt_property_name(prop, src)
        var = _child(prop, {"variable_declaration"})
        declared = _base_type(_ktext(var, _KT_TYPES, src)) if var is not None else ""
        if not declared:
            m = _G_LOCALS["kotlin"].search(_text(prop, src))
            declared = m.group(2) if m and m.group(1) == name else ""
        if name and declared:
            out[name] = declared
    return out


_KT_INITS = {"property_declaration", "anonymous_initializer", "secondary_constructor"}


def _gmethod(node, src: bytes, lang: str, fields: dict[str, str], prefix: str,
             module: dict[str, str] | None = None, qualifiers: dict[str, str] | None = None) -> dict:
    """One method/function record, in `_method`'s shape. `module` is a Kotlin file's typed
    top-level properties, hidden by a parameter or local of the same name; `qualifiers` its
    class's `@Qualifier`-annotated properties."""
    name_node = _gname_node(node, src, lang)
    params = _gparams(node, src, lang)
    body = _gmbody(node, lang)
    hidden = set()
    if module:
        hidden = {n for n, _ in _gparam_pairs(node, src, lang)} | {
            _kt_property_name(p, src) for p in (_walk(body, {"property_declaration"}) if body is not None else [])}
    types = {k: v for k, v in (module or {}).items() if k not in hidden}
    types.update(fields)
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
        "line": _gstart(node),
        "endLine": _end_line(body if lang == "dart" and body is not None else node),
        "params": params,
        "calls": _dedupe_calls(_gcall_entries(body, src, lang, types, qualifiers)),
        "routes": routes,
        "http": [],
    }
    returns = _return_type(node, src, lang)
    if returns:
        entry["returns"] = returns
    refs = _type_refs(node, src, lang)              # structure references, never call edges
    if refs:
        entry["refs"] = refs
    if body is None and lang not in ("ruby", "elixir"):
        entry["declaration"] = True               # an interface / abstract / trait signature
    why = framework_entry([a["name"] for a in annos], entry["name"], _override_modifier(node, src))
    if why:
        entry["entry"] = why
    bean = _kt_bean_function(annos, body, entry["name"], src) if lang == "kotlin" else None
    if bean:
        entry["bean"] = bean
    if lang in OVERLOADING:
        _overload_keys(entry, [d for _, d in _gparam_pairs(node, src, lang)])
    return entry


def _gclass(node, src: bytes, lang: str, is_method, module: dict[str, str] | None = None) -> dict | None:
    name_node = _gname_node(node, src, lang)
    if name_node is None:
        return None
    name = _text(name_node, src)
    annos = _gannos(node, src, lang)
    prefix = _class_prefix(annos, "java", name) if lang == "kotlin" else ""
    fields = _gfields(node, src, lang)
    body = _gbody(node, lang)
    # Spring on Kotlin (finding #30): the same bean / qualifier data the Java branch records.
    qualifiers = _kt_qualifiers(node, src) if lang == "kotlin" else {}
    bean = _spring_bean(annos, name) if lang == "kotlin" else None
    methods = [_gmethod(m, src, lang, fields, prefix, module, qualifiers)
               for m in (body.named_children if body is not None else [])
               if is_method(m) and _gname_node(m, src, lang) is not None]
    # Kotlin code that runs with no method node: a property's initial value, `init { }`,
    # a secondary constructor (finding #28).
    inits = [c for child in (body.named_children if lang == "kotlin" and body is not None else [])
             if child.type in _KT_INITS
             for c in _gcall_entries(child, src, lang, {**(module or {}), **fields}, qualifiers)]
    kind = _class_kind(node)
    return {"name": name, **({"kind": kind} if kind else {}), "bases": _gbases(node, src, lang),
            "decorators": [a["name"] for a in annos if a["name"]],
            "doc": _gdoc(node, src, lang), "line": _gstart(node), "endLine": _end_line(node),
            "fields": fields, "methods": methods,
            **({"init_calls": _dedupe_calls(inits)} if inits else {}),
            **({"bean": bean} if bean else {})}


def _generic(root, src: bytes, lang: str) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """(classes, functions, routes, calls made outside any class) for one file of a SHAPES language."""
    shape = SHAPES[lang]
    module = _kt_top_level_types(root, src) if lang == "kotlin" else {}

    def is_container(n) -> bool:
        return _gkind(n, src, lang) in shape["container"]

    def is_method(n) -> bool:
        return _gkind(n, src, lang) in shape["method"]

    classes: list[dict] = []
    by_name: dict[str, dict] = {}

    def containers(node) -> None:
        for child in node.named_children:
            if is_container(child):
                rec = _gclass(child, src, lang, is_method, module)
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
        entry = _gmethod(m, src, lang, rec["fields"] if rec else {}, "", module)
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
                entry = _gmethod(child, src, lang, {}, "", module)
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
    # A Kotlin top-level property's initial value runs when the file's class loads (#28).
    inits = [c for prop in root.named_children if lang == "kotlin" and prop.type == "property_declaration"
             for c in _gcall_entries(prop, src, lang, module)]
    return classes, functions, routes, _dedupe_calls(inits)


def _imports(root, src: bytes, lang: str) -> list[dict]:
    out = []
    for node in _walk(root, IMPORT_TYPES[lang]):
        dotted = _text(node, src)
        dotted = re.sub(r"^(?:import|using)\s+(?:static\s+)?", "", dotted).strip().rstrip(";").strip()
        if dotted:
            out.append({"from": dotted, "names": [dotted.split(".")[-1]]})
    return out


def _kt_imports(root, src: bytes) -> list[dict]:
    """Kotlin's `import com.shop.Store` / `import com.shop.*`, in `_imports`' shape."""
    out = []
    for node in _walk(root, {"import", "import_header"}, stop=_BODY_TYPES):
        dotted = re.sub(r"^import\s+", "", _text(node, src).strip()).split(" as ")[0].strip()
        if dotted and not dotted.startswith("import"):
            out.append({"from": dotted, "names": [dotted.split(".")[-1]]})
    return out


def _package(root, src: bytes) -> str:
    """The package or namespace a file declares: Java/Groovy `package`, Kotlin's header, C#'s
    (file-scoped or first block) `namespace`. "" when it declares none."""
    for child in root.named_children:
        if child.type in ("package_declaration", "package_header"):
            return re.sub(r"^package\s+|;$", "", _text(child, src).strip()).strip()
        if child.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
            return _field_text(child, "name", src)
    return ""


def class_locator(files):
    """`locate(name, from_rel)`: the one file whose class `name` a reference in `from_rel` means.

    A class name two files define -- the same `ConfigService` in two applications of one
    repository -- used to be resolved only from the caller's own file, so every call to it
    from anywhere else was dropped. The source settles it: the caller's own file, else the only
    file defining it, else the one its `import` names exactly, else one a wildcard `import` or
    C# `using` covers, else the one in the caller's own package. Two survivors is None, never a guess.
    `files` is (rel, extract_lang_files result) pairs.
    """
    defs: dict[str, list[tuple[str, str]]] = {}
    scope: dict[str, tuple[str, set[str]]] = {}
    for rel, res in files:
        pkg = res.get("package", "")
        scope[rel] = (pkg, {i["from"] for i in res.get("imports", [])})
        for cls in res.get("classes", []):
            defs.setdefault(cls["name"], []).append((rel, pkg))

    def locate(name: str, from_rel: str) -> str | None:
        cands = defs.get(name, [])
        rels = sorted({r for r, _ in cands})
        if from_rel in rels:
            return from_rel
        if len(rels) <= 1:
            return rels[0] if rels else None
        pkg, imports = scope.get(from_rel, ("", set()))
        for rule in (lambda p: f"{p}.{name}" in imports,
                     lambda p: f"{p}.*" in imports or p in imports,
                     lambda p: p == pkg):
            hits = sorted({r for r, p in cands if p and rule(p)})
            if hits:
                return hits[0] if len(hits) == 1 else None
        return None
    return locate


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
        classes, functions, routes, inits = _generic(root, src, lang)
        # Calls resolve through declared types; imports only settle which of two files'
        # classes of one name is meant (`class_locator`), which Kotlin needs as Java does.
        imports: list[dict] = _kt_imports(root, src) if lang == "kotlin" else []
    else:
        classes, functions, inits = _containers(root, src, lang)
        routes = _go_routes(root, src) if lang == "go" else []
        imports = _imports(root, src, lang)
    package = _package(root, src)
    return {"file": path, "lang": lang, "imports": imports, **({"package": package} if package else {}),
            "classes": classes, "functions": functions, "routes": routes,
            **({"init_calls": inits} if inits else {})}


def find_lang_files(root: str) -> list[str]:
    """Every file under `root` in one of this module's languages, in a fixed order (constraint 2)."""
    out: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(source_dirs(dirpath, dirs))
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
        description="Java/Go/C# and the phase-7 languages, extracted via tree-sitter "
                    "(debugging aid; the graph builders call this as a library).")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    args = parser.parse_args(argv)
    records = []
    for root in args.src:
        records += extract_lang_files(find_lang_files(os.path.abspath(root)))
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
