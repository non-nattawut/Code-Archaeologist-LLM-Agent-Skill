#!/usr/bin/env python3
"""lang_extract.py — approximate structure/flow extraction for Java, Go and C#.

Python has `ast` and JS/TS has `@babel/parser`; these three have neither on a
stdlib-only budget (hard constraint 1). So this reads declarations textually and
says so: **every node and edge it produces is marked `approx: true`**, and the
report and the brief repeat that wherever a grade rests on them.

It is not a parser, and it is not a naive grep either. Three things keep the false
positives low enough to be worth shipping:

  1. Comments and string bodies are blanked to spaces first, preserving length and
     line breaks. Most "regex ate a URL in a comment" failures die here. The string
     *contents* are kept in a side table, because a route path lives inside one --
     and `"/orders/{id}"` would otherwise break step 2.
  2. Bodies are found by brace matching, not by regex. All three languages are
     brace languages, which is exactly why these three and not Ruby or Elixir.
  3. Call receivers are resolved through declared types the way build_flow.py
     resolves Python: field type, parameter type, local `new Foo()`. These
     languages declare parameter types mandatorily, so constructor injection
     (Spring, ASP.NET DI, a Go struct literal) resolves for free.

**Unresolved calls are dropped, never guessed** -- the same rule the Python
resolver follows. An interface with two implementations, an overload set and a
lambda handler all produce no edge rather than a wrong one.

Output is one record per file, in the same shape `js_extract.js` emits so
`build_wiki.py` and `build_flow.py` gain a producer rather than a code path:

    {file, lang, approx, imports: [{from, names}],
     classes:   [{name, bases, decorators, doc, line, endLine, fields,
                  methods: [{name, doc, line, endLine, params, calls, routes}]}],
     functions: [{name, doc, line, endLine, params, calls, routes}],
     routes:    [{method, path, handler, line}]}

`calls` entries are `{type, name}`: `type` is the resolved receiver type, `""` for
a bare call (same class, then module function), and `"?"` for a receiver this pass
could not type -- which the caller counts as external and never links.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import bisect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402,F401  (also puts sibling script dirs on sys.path)

from manifest import SKIP_DIRS  # noqa: E402  (one definition of "a directory to skip")
from taxonomy import lang_of    # noqa: E402  (one definition of "what language is this file")

LANG_EXTS = {".java": "java", ".go": "go", ".cs": "csharp"}

HTTP_VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

# Words that look like a call but are not one. A superset across the three
# languages: a `switch (x)` or a `len(v)` must not become a graph edge.
CALL_KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case", "default", "catch",
    "return", "throw", "throws", "try", "finally", "using", "lock", "foreach",
    "sizeof", "typeof", "nameof", "await", "yield", "assert", "synchronized",
    "this", "super", "base", "fixed", "checked", "unchecked", "select", "go",
    "defer", "range", "func", "make", "new", "len", "cap", "append", "copy",
    "delete", "panic", "recover", "print", "println", "var", "const", "type",
    "struct", "interface", "map", "chan", "class", "record", "enum", "in", "is",
    # Go conversions read exactly like calls: `[]byte(event)`, `string(b)`.
    "byte", "rune", "string", "int", "int32", "int64", "uint", "uint64",
    "float32", "float64", "bool", "error",
}

# Modifier keywords. `mods` in MEMBER_RE can match none of them, so without this
# `public Foo(Bar b) {` parses as return type `public`, name `Foo` -- turning
# every constructor into a method.
MODIFIERS = {
    "public", "protected", "private", "internal", "static", "final", "abstract",
    "synchronized", "native", "default", "strictfp", "readonly", "virtual",
    "override", "sealed", "async", "extern", "partial", "volatile", "transient",
    "unsafe", "new",
}

# Words that can stand where MEMBER_RE expects a return type, in constructs that
# are not declarations: `} else if (x) {`, `= new Runnable() {`. Deliberately not
# CALL_KEYWORDS -- that set holds `int` and `string` for Go's conversions, and
# `public int price(...)` is a perfectly ordinary method.
NOT_A_TYPE = {"new", "else", "return", "throw", "case", "do", "try", "await",
              "yield", "in", "is", "go", "defer", "switch", "while", "catch"}


# ---------------------------------------------------------------------------
# Step 1: blank out comments and string bodies
# ---------------------------------------------------------------------------
def blank(text: str, lang: str) -> tuple[str, dict[int, str]]:
    """Comments and string bodies -> spaces, same length, same line breaks.

    Returns `(blanked, literals)`, where `literals` maps each opening quote's
    offset to the original string contents. Blanking is what makes brace matching
    and the declaration regexes safe; the side table is what keeps route paths
    readable afterwards.
    """
    out = list(text)
    lits: dict[int, str] = {}
    i, n = 0, len(text)

    def wipe(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        two = text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            wipe(i, j)
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            wipe(i, j)
            i = j
        elif lang == "csharp" and (two == '@"' or text[i:i + 3] == '$@"'):
            # Verbatim string: no backslash escapes, and "" is one quote.
            q = text.index('"', i)
            j = q + 1
            while j < n:
                if text[j] == '"':
                    if text[j + 1:j + 2] == '"':
                        j += 2
                        continue
                    break
                j += 1
            lits[q] = text[q + 1:j].replace('""', '"')
            wipe(q + 1, j)
            i = j + 1
        elif lang == "java" and text[i:i + 3] == '"""':
            j = text.find('"""', i + 3)
            j = n if j < 0 else j
            lits[i] = text[i + 3:j]
            wipe(i + 3, j)
            i = min(j + 3, n)
        elif lang == "go" and text[i] == "`":
            j = text.find("`", i + 1)
            j = n if j < 0 else j
            lits[i] = text[i + 1:j]
            wipe(i + 1, j)
            i = min(j + 1, n)
        elif text[i] in "\"'":
            quote = text[i]
            j = i + 1
            while j < n and text[j] != quote and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            lits[i] = text[i + 1:j]
            wipe(i + 1, j)
            i = j + 1
        else:
            i += 1
    return "".join(out), lits


def _literal_in(lits: dict[int, str], start: int, end: int) -> str:
    """The first string literal opening inside [start, end)."""
    for off in sorted(k for k in lits if start <= k < end):
        return lits[off]
    return ""


# ---------------------------------------------------------------------------
# Step 2: brace matching and line numbers
# ---------------------------------------------------------------------------
def _body_range(text: str, brace: int) -> tuple[int, int]:
    """(start, end) of the block whose opening `{` is at `brace`; end excludes `}`."""
    depth = 0
    for k in range(brace, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return brace + 1, k
    return brace + 1, len(text)


def _line_index(text: str) -> list[int]:
    starts = [0]
    for m in re.finditer("\n", text):
        starts.append(m.end())
    return starts


def _mask(text: str, spans) -> str:
    """Blank out whole spans, so an outer scope does not claim an inner one's members."""
    out = list(text)
    for a, b in spans:
        for k in range(a, min(b, len(out))):
            if out[k] != "\n":
                out[k] = " "
    return "".join(out)


# ---------------------------------------------------------------------------
# Docs: read from the original text, since blanking removed the words
# ---------------------------------------------------------------------------
ANNO_LINE_RE = re.compile(r"^\s*[@\[]")


def _doc_above(orig: list[str], line_no: int) -> str:
    """First line of the comment documenting the declaration at `line_no` (1-based).

    Java and C# put annotations between the doc comment and the declaration, so
    unlike the JS rule this walks up over annotation and blank lines first. It
    still stops at the first line that is none of those -- a comment two
    declarations up documents that one, not this one.

    Deliberately reads the *original* lines: in the blanked text a comment is
    indistinguishable from a blank line, so walking there would step straight
    over the doc it is looking for.
    """
    i = line_no - 2                       # the line above, 0-based
    while i >= 0 and (not orig[i].strip() or ANNO_LINE_RE.match(orig[i])):
        i -= 1
    if i < 0:
        return ""
    line = orig[i].strip()
    if line.startswith("//"):
        # A run of `//` lines is one comment, and its *first* line is the summary
        # -- the same rule js_extract.js applies to a `/** */` block.
        j = i
        while j > 0 and orig[j - 1].strip().startswith("//"):
            j -= 1
        for raw in orig[j:i + 1]:
            cleaned = _strip_xml(raw.strip().lstrip("/").strip())
            if cleaned:
                return cleaned
        return ""
    if not line.endswith("*/"):
        return ""
    block = []
    while i >= 0:
        block.insert(0, orig[i])
        if "/*" in orig[i]:
            break
        i -= 1
    for raw in block:
        cleaned = raw.strip().lstrip("/").lstrip("*").rstrip("/").rstrip("*").strip()
        if cleaned:
            return _strip_xml(cleaned)
    return ""


def _strip_xml(text: str) -> str:
    """`<summary>Issue an invoice.</summary>` -> `Issue an invoice.` (C# doc comments)."""
    return re.sub(r"\s+", " ", re.sub(r"</?\w+[^>]*>", " ", text)).strip()


# ---------------------------------------------------------------------------
# Annotations / attributes
# ---------------------------------------------------------------------------
ANNO_RE = {"java": re.compile(r"@(\w+)"), "csharp": re.compile(r"\[(\w+)")}


def _annotations(blanked: str, lits: dict[int, str], start: int, end: int,
                 lang: str) -> list[dict]:
    """Annotations (`@Foo("x")`) or attributes (`[Foo("x")]`) in a span of text."""
    pattern = ANNO_RE.get(lang)
    if pattern is None:
        return []
    found = []
    for m in pattern.finditer(blanked, start, end):
        arg_end = m.end()
        arg = ""
        rest = blanked[m.end():end]
        lead = len(rest) - len(rest.lstrip())
        if rest[lead:lead + 1] == "(":
            open_at = m.end() + lead
            depth = 0
            for k in range(open_at, end):
                if blanked[k] == "(":
                    depth += 1
                elif blanked[k] == ")":
                    depth -= 1
                    if depth == 0:
                        arg_end = k + 1
                        break
            arg = _literal_in(lits, open_at, arg_end)
        found.append({"name": m.group(1), "arg": arg,
                      "text": blanked[m.start():arg_end]})
    return found


def _anno_span(blank_lines: list[str], line_starts: list[int], line_no: int) -> tuple[int, int]:
    """Text span holding the annotations attached to the declaration at `line_no`."""
    end = line_starts[line_no - 1] if line_no - 1 < len(line_starts) else 0
    i = line_no - 2
    while i >= 0 and (not blank_lines[i].strip() or ANNO_LINE_RE.match(blank_lines[i])):
        i -= 1
    return (line_starts[i + 1] if i + 1 < len(line_starts) else 0), end


# ---------------------------------------------------------------------------
# Types, params, calls  (shared by all three dialects)
# ---------------------------------------------------------------------------
def _base_type(text: str) -> str:
    """`*pkg.Foo[]` / `List<Foo>` / `Foo?` -> `Foo`, or "" when it is not a name."""
    t = re.sub(r"<.*", "", text.strip().lstrip("*&"))
    t = t.replace("[]", "").replace("?", "").strip().split(".")[-1]
    return t if re.fullmatch(r"[A-Za-z_]\w*", t or "") else ""


def _split_params(text: str) -> list[str]:
    """Comma-split at depth 0, so `Map<String, Foo> m` stays one parameter."""
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in text:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [p.strip() for p in out if p.strip()]


def _params(text: str, lang: str) -> dict[str, str]:
    """Parameter name -> declared type. Go writes `name Type`, the others `Type name`."""
    types: dict[str, str] = {}
    for part in _split_params(text):
        part = re.sub(r"[@\[][\w.]+(\([^)]*\))?\]?", " ", part).strip()   # drop annotations
        tokens = part.split()
        if len(tokens) < 2:
            continue
        name, declared = (tokens[0], tokens[-1]) if lang == "go" else (tokens[-1], tokens[-2])
        base = _base_type(declared)
        if base and re.fullmatch(r"[A-Za-z_]\w*", name):
            types[name] = base
    return types


NEW_LOCAL_RE = re.compile(r"(?:^|[^\w.])(?:var|[\w.<>\[\]]+)\s+(\w+)\s*=\s*new\s+([\w.]+)\s*[(<{]")
GO_LOCAL_RE = re.compile(r"(\w+)\s*:=\s*&?(?:\w+\.)?(\w+)\{")
GO_CTOR_RE = re.compile(r"(\w+)\s*:=\s*(?:\w+\.)?New(\w+)\s*\(")
GO_VAR_RE = re.compile(r"\bvar\s+(\w+)\s+\*?(?:\w+\.)?(\w+)\b")


def _locals(body: str, lang: str) -> dict[str, str]:
    """Local variable -> type, from the constructions that state it outright."""
    types: dict[str, str] = {}
    if lang == "go":
        for name, cls in GO_LOCAL_RE.findall(body):
            types[name] = cls
        for name, cls in GO_CTOR_RE.findall(body):     # `s := NewOrderService()`
            types[name] = cls
        for name, cls in GO_VAR_RE.findall(body):
            types.setdefault(name, cls)
    else:
        for name, cls in NEW_LOCAL_RE.findall(body):
            types[name] = _base_type(cls)
    return {k: v for k, v in types.items() if v}


CALL_RE = re.compile(r"(?:(?P<recv>[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*)\s*\.\s*)?"
                     r"(?P<name>[A-Za-z_]\w*)\s*\(")
SELF_WORDS = {"this", "self", "base", "super"}


def _prev_word(text: str, idx: int) -> str:
    j = idx - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    end = j + 1
    while j >= 0 and (text[j].isalnum() or text[j] == "_"):
        j -= 1
    return text[j + 1:end]


def _calls(body: str, types: dict[str, str], recv_name: str = "") -> list[dict]:
    """Call sites in a body, with the receiver resolved to a declared type.

    `type` is "" for a bare call (the caller tries same-class, then a module
    function), the resolved class name when the receiver was typed, and "?" when
    it was not -- which the caller counts as external rather than guessing.
    """
    out: list[dict] = []
    for m in CALL_RE.finditer(body):
        name = m.group("name")
        if name in CALL_KEYWORDS or _prev_word(body, m.start()) in ("new", "func"):
            continue
        recv = (m.group("recv") or "").replace(" ", "")
        if not recv:
            out.append({"type": "", "name": name})
            continue
        parts = recv.split(".")
        head = parts[0]
        resolved = ""
        if head in SELF_WORDS and len(parts) == 1:
            out.append({"type": "", "name": name})  # `this.m()` is a same-class call
            continue
        if len(parts) == 1:
            resolved = types.get(head, "")
        elif len(parts) == 2 and (head in SELF_WORDS or head == recv_name):
            resolved = types.get(parts[1], "")      # this.field.m() / (r *X) r.field.m()
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
# Routes
# ---------------------------------------------------------------------------
JAVA_VERBS = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
              "PatchMapping": "PATCH", "DeleteMapping": "DELETE"}
CS_VERBS = {"HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT",
            "HttpPatch": "PATCH", "HttpDelete": "DELETE"}
REQUEST_METHOD_RE = re.compile(r"RequestMethod\.(\w+)")


def _join_path(prefix: str, suffix: str) -> str:
    parts = [p.strip("/") for p in (prefix, suffix) if p and p.strip("/")]
    return "/" + "/".join(parts)


def _class_prefix(annos: list[dict], lang: str, cls_name: str) -> str:
    """The path prefix a class-level annotation declares, if any."""
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
            found = REQUEST_METHOD_RE.findall(a["text"])
            for verb in (found or ["ANY"]):
                routes.append({"method": verb.upper(), "path": _join_path(prefix, a["arg"])})
    return routes


# `mux.HandleFunc("GET /orders/{id}", h)`, chi `r.Get("/x", h)`, gin `g.GET("/x", h)`.
GO_ROUTE_RE = re.compile(r"\b\w+\s*\.\s*(HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE|"
                         r"Get|Post|Put|Patch|Delete)\s*\(")


def _go_routes(blanked: str, lits: dict[int, str], line_of, orig_lines) -> list[dict]:
    """Router registrations anywhere in the file (they live inside main/NewRouter)."""
    routes = []
    for m in GO_ROUTE_RE.finditer(blanked):
        depth = 0
        close = -1
        for k in range(m.end() - 1, len(blanked)):
            if blanked[k] == "(":
                depth += 1
            elif blanked[k] == ")":
                depth -= 1
                if depth == 0:
                    close = k
                    break
        if close < 0:
            continue
        path = _literal_in(lits, m.end() - 1, close)
        if not path.strip():
            continue
        verb = m.group(1).upper()
        if verb in ("HANDLEFUNC", "HANDLE"):
            # Go 1.22 puts the method in the pattern; without one it serves any.
            head, _, rest = path.partition(" ")
            verb, path = (head.upper(), rest) if head.upper() in HTTP_VERBS else ("ANY", path)
        if not path.startswith("/"):
            continue
        args = _split_params(blanked[m.end():close])
        handler = ""
        if len(args) > 1:
            tail = args[-1].strip().split(".")[-1]
            handler = tail if re.fullmatch(r"[A-Za-z_]\w*", tail) else ""
        line = line_of(m.start())
        routes.append({"method": verb, "path": path, "handler": handler,
                       "line": line, "doc": _doc_above(orig_lines, line)})
    return routes


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------
JAVA_CLASS_RE = re.compile(r"\b(?:class|interface|enum|record)\s+(\w+)\b([^{;]*)\{")
CS_CLASS_RE = re.compile(r"\b(?:class|interface|struct|record)\s+(\w+)\b([^{;=]*)\{")
GO_TYPE_RE = re.compile(r"^type\s+(\w+)\s+(?:struct|interface)\s*\{", re.M)

# Modifiers, optional generic, return type, name, params -- everything up to the
# point where a method either opens a body or ends. The two forms are built from
# one string so they cannot drift apart.
_MEMBER_HEAD = (
    r"^[ \t]*(?P<mods>(?:(?:public|protected|private|internal|static|final|abstract|"
    r"synchronized|native|default|strictfp|readonly|virtual|override|sealed|async|"
    r"extern|partial|volatile|transient|unsafe|new)\s+)*)"
    r"(?:<[^>]+>\s+)?"
    r"(?P<type>[\w.$]+(?:\s*<[^<>()]*>)?(?:\[\])*)\s+(?P<name>\w+)\s*"
    r"\((?P<params>[^)]*)\)[^;{=]*")

MEMBER_RE = re.compile(_MEMBER_HEAD + r"\{", re.M)

# The same declaration terminated by `;` instead of a body: a Java interface
# method, an `abstract` method, a C# interface member. They declare a name that
# calls resolve against, so without them a call through an interface type has
# nothing to point at and the edge is dropped.
MEMBER_DECL_RE = re.compile(_MEMBER_HEAD + r";", re.M)

# Words that can stand where MEMBER_DECL_RE expects a return type in a construct
# that declares a type rather than a method: `record Point(int x, int y);`,
# `delegate int Cmp(T a, T b);`. Not added to NOT_A_TYPE, because MEMBER_RE's
# closing brace already keeps them out of the body form.
DECLARES_A_TYPE = {"record", "class", "interface", "enum", "struct", "delegate"}

FIELD_RE = re.compile(
    r"^[ \t]*(?:(?:public|protected|private|internal|static|final|readonly|volatile|"
    r"transient|const)\s+)+"
    r"(?P<type>[\w.$]+(?:\s*<[^<>()]*>)?(?:\[\])*)\s+(?P<name>\w+)\s*(?:=[^;{]*)?[;{]", re.M)

GO_METHOD_RE = re.compile(r"^func\s*\(\s*(\w+)\s+\*?(\w+)\s*\)\s*(\w+)\s*\((?P<params>[^)]*)\)"
                          r"[^{]*\{", re.M)
GO_FUNC_RE = re.compile(r"^func\s+(\w+)\s*\((?P<params>[^)]*)\)[^{]*\{", re.M)
GO_FIELD_RE = re.compile(r"^\s*(\w+)\s+\*?(?:\w+\.)?(\w+)\s*(?:`[^`]*`)?\s*$", re.M)

JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)
CS_IMPORT_RE = re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.M)


def _member_decls(blanked: str, span: tuple[int, int]):
    """(match, body_start, body_end, declared_only) for every method in a class body.

    A method with no body -- an interface member, an `abstract` method -- gets an
    empty body range. There is nothing to read calls from, but the name still has
    to exist, because that is what a call through the declared type resolves to.
    """
    start, end = span
    out = []
    for m in MEMBER_RE.finditer(blanked, start, end):
        if m.group("type") in NOT_A_TYPE or m.group("type") in MODIFIERS:
            continue        # `new Runnable() {`, `else if (x) {`, and constructors
        b_start, b_end = _body_range(blanked, m.end() - 1)
        out.append((m, b_start, b_end, False))

    bodies = [(a, b) for _, a, b, _ in out]
    for m in MEMBER_DECL_RE.finditer(blanked, start, end):
        if (m.group("type") in NOT_A_TYPE or m.group("type") in MODIFIERS
                or m.group("type") in DECLARES_A_TYPE):
            continue
        if any(a <= m.start() < b for a, b in bodies):
            continue        # a statement inside a method, not a member declaration
        out.append((m, m.end(), m.end(), True))
    return sorted(out, key=lambda d: d[0].start())


def _members(blanked, lits, orig_lines, blank_lines, line_starts, line_of,
             decls, lang: str, prefix: str, fields: dict[str, str]) -> list[dict]:
    """Methods declared directly in a class body, with their calls resolved."""
    methods = []
    for m, b_start, b_end, declared_only in decls:
        line = line_of(m.start())
        params = _params(m.group("params"), lang)
        types = dict(fields)
        types.update(params)
        types.update(_locals(blanked[b_start:b_end], lang))
        annos = _annotations(blanked, lits, *_anno_span(blank_lines, line_starts, line), lang)
        entry = {
            "name": m.group("name"),
            "doc": _doc_above(orig_lines, line),
            "line": line, "endLine": line_of(b_end),
            "params": params,
            "calls": _dedupe_calls(_calls(blanked[b_start:b_end], types)),
            "routes": _method_routes(annos, prefix, lang),
            "http": [],
        }
        if declared_only:
            entry["declaration"] = True   # a signature, not code that runs
        methods.append(entry)
    return methods


def _class_fields(region: str) -> dict[str, str]:
    fields = {}
    for m in FIELD_RE.finditer(region):
        base = _base_type(m.group("type"))
        if base and base not in NOT_A_TYPE:
            fields[m.group("name")] = base
    return fields


def _parse_braced(text: str, blanked: str, lits: dict[int, str], lang: str, line_of):
    """Java and C#: classes with members, no module-level functions."""
    orig_lines = text.split("\n")
    blank_lines = blanked.split("\n")
    line_starts = _line_index(blanked)
    class_re = JAVA_CLASS_RE if lang == "java" else CS_CLASS_RE

    spans = []
    for m in class_re.finditer(blanked):
        brace = blanked.index("{", m.end() - 1)
        spans.append((m, *_body_range(blanked, brace)))

    classes = []
    for m, b_start, b_end in spans:
        # An inner class owns its own members; blank it out of the outer body.
        inner = [(a, b) for other, a, b in spans
                 if other is not m and b_start <= a < b_end]
        body = _mask(blanked, inner)
        line = line_of(m.start())
        annos = _annotations(blanked, lits, *_anno_span(blank_lines, line_starts, line), lang)
        prefix = _class_prefix(annos, lang, m.group(1))

        # Methods first, so their bodies can be masked out before fields are read:
        # a local `Foo bar = ...` inside a method is not a field of the class.
        decls = _member_decls(body, (b_start, b_end))
        fields = _class_fields(_mask(body, [(a, b) for _, a, b, _ in decls])[b_start:b_end])
        methods = _members(body, lits, orig_lines, blank_lines, line_starts, line_of,
                           decls, lang, prefix, fields)

        bases = []
        tail = m.group(2)
        if lang == "java":
            for kw in ("extends", "implements"):
                found = re.search(kw + r"\s+([\w.,<>\s$]+?)(?=\bimplements\b|$)", tail)
                if found:
                    bases += [_base_type(p) for p in _split_params(found.group(1))]
        else:
            _, _, after = tail.partition(":")
            bases += [_base_type(p) for p in _split_params(after)]
        classes.append({
            "name": m.group(1), "bases": [b for b in bases if b],
            "decorators": [a["name"] for a in annos],
            "doc": _doc_above(orig_lines, line),
            "line": line, "endLine": line_of(b_end),
            "fields": fields, "methods": methods,
        })
    return classes, []


def _parse_go(text: str, blanked: str, lits: dict[int, str], line_of):
    """Go: a struct is the entity, its receiver methods are its methods."""
    orig_lines = text.split("\n")
    blank_lines = blanked.split("\n")

    structs: dict[str, dict] = {}
    for m in GO_TYPE_RE.finditer(blanked):
        brace = blanked.index("{", m.end() - 1)
        b_start, b_end = _body_range(blanked, brace)
        fields = {}
        for fname, ftype in GO_FIELD_RE.findall(blanked[b_start:b_end]):
            if fname not in NOT_A_TYPE:
                fields[fname] = ftype
        line = line_of(m.start())
        structs[m.group(1)] = {
            "name": m.group(1), "bases": [], "decorators": [],
            "doc": _doc_above(orig_lines, line),
            "line": line, "endLine": line_of(b_end),
            "fields": fields, "methods": [],
        }

    method_spans = []
    for m in GO_METHOD_RE.finditer(blanked):
        recv_name, recv_type, name = m.group(1), m.group(2), m.group(3)
        brace = blanked.index("{", m.end() - 1)
        b_start, b_end = _body_range(blanked, brace)
        method_spans.append((m.start(), b_end))
        owner = structs.get(recv_type)
        if owner is None:
            continue
        params = _params(m.group("params"), "go")
        types = dict(owner["fields"])
        types.update(params)
        types.update(_locals(blanked[b_start:b_end], "go"))
        line = line_of(m.start())
        owner["methods"].append({
            "name": name, "doc": _doc_above(orig_lines, line),
            "line": line, "endLine": line_of(b_end), "params": params,
            "calls": _dedupe_calls(_calls(blanked[b_start:b_end], types, recv_name)),
            "routes": [], "http": [],
        })

    functions = []
    for m in GO_FUNC_RE.finditer(blanked):
        if any(a <= m.start() < b for a, b in method_spans):
            continue                                   # already claimed as a method
        brace = blanked.index("{", m.end() - 1)
        b_start, b_end = _body_range(blanked, brace)
        params = _params(m.group("params"), "go")
        types = dict(params)
        types.update(_locals(blanked[b_start:b_end], "go"))
        line = line_of(m.start())
        functions.append({
            "name": m.group(1), "doc": _doc_above(orig_lines, line),
            "line": line, "endLine": line_of(b_end), "params": params,
            "calls": _dedupe_calls(_calls(blanked[b_start:b_end], types)),
            "routes": [], "http": [],
        })
    return list(structs.values()), functions


# ---------------------------------------------------------------------------
# One file
# ---------------------------------------------------------------------------
def extract_file(path: str) -> dict | None:
    lang = LANG_EXTS.get(os.path.splitext(path)[1].lower())
    if lang is None:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"  ! skipped {path}: {exc}", file=sys.stderr)
        return None

    blanked, lits = blank(text, lang)
    starts = _line_index(blanked)

    def line_of(offset: int) -> int:
        return bisect.bisect_right(starts, offset)

    if lang == "go":
        classes, functions = _parse_go(text, blanked, lits, line_of)
        routes = _go_routes(blanked, lits, line_of, text.splitlines())
        imports = []
    else:
        classes, functions = _parse_braced(text, blanked, lits, lang, line_of)
        routes = []
        pattern = JAVA_IMPORT_RE if lang == "java" else CS_IMPORT_RE
        imports = [{"from": dotted, "names": [dotted.split(".")[-1]]}
                   for dotted in pattern.findall(blanked)]

    return {"file": path, "lang": lang, "approx": True, "imports": imports,
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
    """One record per file, mirroring `js_bridge.extract_js_files`."""
    return [rec for rec in (extract_file(p) for p in sorted(paths)) if rec]


def main(argv=None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(
        description="Approximate Java/Go/C# extraction (debugging aid; the graph builders call this as a library).")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    args = parser.parse_args(argv)
    records = []
    for root in args.src:
        records += extract_lang_files(find_lang_files(os.path.abspath(root)))
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
