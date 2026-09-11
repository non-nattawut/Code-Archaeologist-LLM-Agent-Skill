#!/usr/bin/env python3
"""route_tables.py — routes declared in a *table*, away from their handlers.

Every route the extractors read is written on or beside its handler: a decorator,
an annotation, an attribute, or a router call next to the function (Express, Go).
A route table puts them somewhere else and names the handler by reference --
Django's `urlpatterns`, Rails' `config/routes.rb`, Laravel's `routes/*.php`,
Phoenix's router module. Until phase 8 none of those apps' views had a route, so
none of them linked across the stack.

This module only *reads* tables, into (method, path, handler reference). Attaching
is `build_flow`'s job, done exactly as for a decorator route; a reference that
names no single node is dropped and counted there, never guessed -- a wrong edge
is worse than a missing one.

What each framework's reader understands:

  Django   path / re_path / url, include() (with its prefix), function views, and
           class-based views (`View.as_view()` -> one route per HTTP method the
           class defines). Django paths name no verb, so they are `ANY`.
  Rails    get/post/put/patch/delete/match, resources / resource (with only: /
           except:, nested resources, member / collection), namespace, scope, root
  Laravel  Route::get/post/..., 'Controller@action' and [Controller::class, 'm'],
           prefix()->group(), Route::group(['prefix' => ...]), resource / apiResource
           (with ->only / ->except)
  Phoenix  scope (path and module alias, nested), get/post/..., resources (only: /
           except:, nested)

A grammar that is not installed skips its tables silently: the extractor for that
language has already named it, once.

Python 3.10+.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402,F401  (puts sibling script dirs on sys.path)

import grammars  # noqa: E402
from ts_extract import SKIP_DIRS  # noqa: E402  (one definition of "not source")

HTTP_METHOD_NAMES = ("get", "post", "put", "patch", "delete", "head", "options")


# --- tree helpers ---------------------------------------------------------------
def _t(node) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _f(node, name):
    return node.child_by_field_name(name) if node is not None else None


def _kids(node) -> list:
    return list(node.named_children) if node is not None else []


def _walk(node, types):
    for c in _kids(node):
        if c.type in types:
            yield c
        yield from _walk(c, types)


def _content(node, part: str) -> str | None:
    """A string literal's value: the text of its `part` children, or None if not a string."""
    if node is None or node.type not in ("string", "encapsed_string"):
        return None
    return "".join(_t(c) for c in _kids(node) if c.type == part)


def _parse(full: str, lang: str):
    parser = grammars.parser_for(lang)
    if parser is None:
        return None
    try:
        with open(full, "rb") as fh:
            return parser.parse(fh.read()).root_node
    except OSError:
        return None


def _join(*parts: str) -> str:
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _camel(word: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[_\-]", word) if p)


def _filter(actions, only, except_):
    return [a for a in actions if (not only or a[0] in only) and a[0] not in except_]


# --- finding the tables ------------------------------------------------------------
def _files(roots, exts):
    for root in roots:
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for fn in sorted(names):
                if os.path.splitext(fn)[1].lower() in exts:
                    yield root, os.path.join(dirpath, fn)


def _contains(full: str, needle: str) -> bool:
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            return needle in fh.read()
    except OSError:
        return False


# --- Django ------------------------------------------------------------------------
def _py_module(dots: int, dotted: str, from_file: str, root: str) -> str | None:
    """The file a (relative or absolute) Python module name refers to, or None."""
    parts = [p for p in dotted.split(".") if p]
    bases = []
    if dots:
        base = os.path.dirname(from_file)
        for _ in range(dots - 1):
            base = os.path.dirname(base)
        bases = [base]
    else:                         # absolute: try every ancestor up to the root
        base = os.path.dirname(from_file)
        stop = os.path.dirname(os.path.abspath(root))
        while base and os.path.abspath(base) != stop:
            bases.append(base)
            parent = os.path.dirname(base)
            if parent == base:
                break
            base = parent
    for b in bases:
        for cand in (os.path.join(b, *parts) + ".py", os.path.join(b, *parts, "__init__.py")):
            if parts and os.path.isfile(cand):
                return os.path.normpath(cand)
    return None


def _py_imports(root_node, full: str, root: str) -> dict[str, tuple[str | None, str | None]]:
    """Local name -> (module file, imported name); imported name None means a module."""
    out: dict[str, tuple[str | None, str | None]] = {}
    for imp in _walk(root_node, {"import_from_statement"}):
        mod = _f(imp, "module_name")
        dots, dotted = 0, _t(mod)
        if mod is not None and mod.type == "relative_import":
            prefix = next((c for c in _kids(mod) if c.type == "import_prefix"), None)
            dots = len(_t(prefix))
            dotted = _t(next((c for c in _kids(mod) if c.type == "dotted_name"), None))
        for name in imp.children_by_field_name("name"):
            local = _t(_f(name, "alias")) if name.type == "aliased_import" else _t(name)
            imported = _t(_f(name, "name")) if name.type == "aliased_import" else _t(name)
            as_module = _py_module(dots, f"{dotted}.{imported}" if dotted else imported, full, root)
            if as_module:                       # `from . import views` -- a module
                out[local] = (as_module, None)
            else:                               # `from .views import OrderView`
                out[local] = (_py_module(dots, dotted, full, root) if dotted or dots else None, imported)
    return out


def _django_ref(expr: str, imports) -> tuple[str | None, str]:
    """(module file, name) a dotted reference in a urls module means."""
    head, _, rest = expr.partition(".")
    module, imported = imports.get(head, (None, None))
    if rest and imported is None:
        return module, rest.split(".")[-1]      # views.order_list
    return module, imported or expr.split(".")[-1]


def _regex_path(pattern: str) -> str:
    """`^legacy/(?P<slug>[-\\w]+)/$` -> `legacy/<slug>/`, readable and matchable."""
    pattern = re.sub(r"\(\?P<(\w+)>[^)]*\)", r"<\1>", pattern)
    return pattern.lstrip("^").rstrip("$")


def _django_table(root: str, full: str) -> list[dict]:
    node = _parse(full, "python")
    if node is None:
        return []
    imports = _py_imports(node, full, root)
    entries: list[dict] = []
    for assign in _walk(node, {"assignment", "augmented_assignment"}):
        right = _f(assign, "right")
        if _t(_f(assign, "left")) != "urlpatterns" or right is None or right.type != "list":
            continue
        for call in _kids(right):
            fn = _t(_f(call, "function")).split(".")[-1] if call.type == "call" else ""
            if fn not in ("path", "re_path", "url"):
                continue
            args = [a for a in _kids(_f(call, "arguments")) if a.type != "keyword_argument"]
            pattern = _content(args[0], "string_content") if args else None
            if pattern is None or len(args) < 2:
                continue
            entry = {"pattern": pattern if fn == "path" else _regex_path(pattern),
                     "line": call.start_point[0] + 1}
            target = args[1]
            if target.type == "call":
                callee = _t(_f(target, "function"))
                if callee.split(".")[-1] == "include":
                    inc = _kids(_f(target, "arguments"))
                    mod = _content(inc[0], "string_content") if inc else None
                    entry["include"] = _py_module(0, mod, full, root) if mod else None
                elif callee.endswith(".as_view"):
                    entry["module"], entry["cls"] = _django_ref(callee[: -len(".as_view")], imports)
                    entry["verbs"] = True
                else:
                    continue
            elif target.type in ("attribute", "identifier"):
                entry["module"], entry["name"] = _django_ref(_t(target), imports)
            else:
                continue
            entries.append(entry)
    return entries


def _django(roots) -> list[dict]:
    tables = {full: (root, _django_table(root, full))
              for root, full in _files(roots, {".py"}) if _contains(full, "urlpatterns")}
    included = {e["include"] for _root, entries in tables.values() for e in entries if e.get("include")}
    out: list[dict] = []

    def expand(full: str, prefix: str, seen: frozenset) -> None:
        root, entries = tables[full]
        for e in entries:
            raw = prefix + e["pattern"]
            if "include" in e:
                target = e["include"]
                if target in tables and target not in seen:
                    expand(target, raw, seen | {target})
                continue
            route = {"framework": "django", "method": "ANY", "path": "/" + raw.lstrip("/"),
                     "cls": e.get("cls"), "name": e.get("name"), "verbs": e.get("verbs", False),
                     "module": e.get("module"), "root": root, "table": full, "line": e["line"]}
            out.append(route)

    for full in sorted(tables):
        if full not in included:
            expand(full, "", frozenset({full}))
    return out


# --- Rails ---------------------------------------------------------------------------
RAILS_RESOURCES = [("index", "GET", ""), ("new", "GET", "/new"), ("create", "POST", ""),
                   ("show", "GET", "/:id"), ("edit", "GET", "/:id/edit"),
                   ("update", "PATCH", "/:id"), ("update", "PUT", "/:id"),
                   ("destroy", "DELETE", "/:id")]
RAILS_RESOURCE = [(a, m, p.replace("/:id", "")) for a, m, p in RAILS_RESOURCES if a != "index"]


def _rb_value(node) -> str:
    if node is None:
        return ""
    if node.type == "simple_symbol":
        return _t(node).lstrip(":")
    s = _content(node, "string_content")
    return s if s is not None else _t(node)


def _rb_args(call):
    """(positional values, {key: value node}) of a Ruby call."""
    pos, kw = [], {}
    for a in _kids(_f(call, "arguments")):
        if a.type == "pair":
            kw[_t(_f(a, "key")).rstrip(":").lstrip(":").strip("\"'")] = _f(a, "value")
        else:
            pos.append(a)
    return pos, kw


def _rb_list(node) -> set[str]:
    return {_rb_value(c) for c in _kids(node)} if node is not None else set()


def _rails(roots) -> list[dict]:
    out: list[dict] = []
    for root, full in _files(roots, {".rb"}):
        if os.path.basename(full) != "routes.rb" and os.path.basename(os.path.dirname(full)) != "routes":
            continue
        node = _parse(full, "ruby")
        if node is None:
            continue

        def add(method, path, ctrl, action, call):
            cls = _camel(ctrl.split("/")[-1]) + "Controller"
            out.append({"framework": "rails", "method": method, "path": path, "cls": cls,
                        "name": action, "root": root, "table": full, "line": call.start_point[0] + 1})

        def visit(body, prefix: str, ctrl_ctx: str = "", member: str = "") -> None:
            for call in _kids(body):
                if call.type != "call" or _f(call, "receiver") is not None:
                    continue
                verb = _t(_f(call, "method"))
                pos, kw = _rb_args(call)
                block = _f(_f(call, "block"), "body")
                if verb in ("get", "post", "put", "patch", "delete", "match", "root"):
                    path = _rb_value(pos[0]) if pos and verb != "root" else ""
                    to = _rb_value(kw.get("to")) if "to" in kw else ""
                    if not to and verb == "root" and pos:
                        to = _rb_value(pos[0])
                    ctrl, _, action = to.partition("#")
                    if not action and ctrl_ctx and path:       # member/collection: get :preview
                        ctrl, action = ctrl_ctx, path
                    if not (ctrl and action):
                        continue
                    methods = ([v.upper() for v in _rb_list(kw.get("via"))] if verb == "match"
                               else ["GET" if verb == "root" else verb.upper()])
                    for m in methods:
                        add(m, _join(prefix, member, path if not ctrl_ctx or "#" in to else path),
                            ctrl, action, call)
                elif verb in ("resources", "resource"):
                    only, except_ = _rb_list(kw.get("only")), _rb_list(kw.get("except"))
                    for sym in pos:
                        name = _rb_value(sym)
                        ctrl = _rb_value(kw["controller"]) if "controller" in kw else \
                            (name if verb == "resources" else name + "s")
                        base = _join(prefix, _rb_value(kw["path"]) if "path" in kw else name)
                        actions = RAILS_RESOURCES if verb == "resources" else RAILS_RESOURCE
                        for action, method, suffix in _filter(actions, only, except_):
                            add(method, base + suffix, ctrl, action, call)
                        if block is not None:
                            nested = base + (f"/:{_singular(name)}_id" if verb == "resources" else "")
                            visit(block, nested, ctrl)
                elif verb in ("member", "collection") and block is not None:
                    visit(block, prefix.rsplit("/:", 1)[0] if verb == "collection" else prefix,
                          ctrl_ctx, "/:id" if verb == "member" else "")
                elif verb == "namespace" and block is not None and pos:
                    visit(block, _join(prefix, _rb_value(pos[0])))
                elif verb == "scope" and block is not None:
                    path = _rb_value(pos[0]) if pos else _rb_value(kw.get("path"))
                    visit(block, _join(prefix, path))

        for draw in _walk(node, {"call"}):
            if _t(_f(draw, "method")) == "draw" and _f(draw, "block") is not None:
                visit(_f(_f(draw, "block"), "body"), "")
    return out


# --- Laravel -------------------------------------------------------------------------
LARAVEL_RESOURCES = [("index", "GET", ""), ("create", "GET", "/create"), ("store", "POST", ""),
                     ("show", "GET", "/{p}"), ("edit", "GET", "/{p}/edit"),
                     ("update", "PUT", "/{p}"), ("update", "PATCH", "/{p}"),
                     ("destroy", "DELETE", "/{p}")]


def _php_args(call) -> list:
    return [next(iter(_kids(a)), None) for a in _kids(_f(call, "arguments")) if a.type == "argument"]


def _php_str(node) -> str | None:
    return _content(node, "string_content") if node is not None else None


def _php_class(node) -> str:
    """`OrderController::class` -> OrderController (last segment of a namespaced name)."""
    if node is not None and node.type == "class_constant_access_expression":
        names = [c for c in _kids(node) if c.type in ("name", "qualified_name")]
        return _t(names[0]).split("\\")[-1] if names else ""
    return ""


def _php_chain(node):
    """[(name, args)] innermost first for `Route::a(...)->b(...)->c(...)`, or None."""
    items = []
    while node is not None and node.type == "member_call_expression":
        items.append((_t(_f(node, "name")), _php_args(node)))
        node = _f(node, "object")
    if node is None or node.type != "scoped_call_expression" or _t(_f(node, "scope")).split("\\")[-1] != "Route":
        return None
    items.append((_t(_f(node, "name")), _php_args(node)))
    return list(reversed(items))


def _laravel(roots) -> list[dict]:
    out: list[dict] = []
    for root, full in _files(roots, {".php"}):
        if not _contains(full, "Route::"):
            continue
        node = _parse(full, "php")
        if node is None:
            continue

        def add(method, path, cls, action, at):
            out.append({"framework": "laravel", "method": method, "path": path, "cls": cls,
                        "name": action, "root": root, "table": full, "line": at.start_point[0] + 1})

        def visit(block, prefix: str) -> None:
            for stmt in _kids(block):
                expr = next(iter(_kids(stmt)), None) if stmt.type == "expression_statement" else None
                chain = _php_chain(expr)
                if not chain:
                    continue
                head, args = chain[0]
                names = [n for n, _ in chain]
                if head in ("get", "post", "put", "patch", "delete", "options", "any"):
                    path = _php_str(args[0]) if args else None
                    handler = args[1] if len(args) > 1 else None
                    cls = action = ""
                    if handler is not None and handler.type == "array_creation_expression":
                        items = [next(iter(_kids(i)), None) for i in _kids(handler)]
                        if len(items) == 2:
                            cls, action = _php_class(items[0]), _php_str(items[1]) or ""
                    elif _php_str(handler) and "@" in _php_str(handler):
                        cls, _, action = _php_str(handler).partition("@")
                        cls = cls.split("\\")[-1]
                    if path is not None and cls and action:
                        add("ANY" if head == "any" else head.upper(), _join(prefix, path), cls, action, stmt)
                elif head in ("resource", "apiResource"):
                    name = (_php_str(args[0]) or "").split(".")[-1] if args else ""
                    cls = _php_class(args[1]) if len(args) > 1 else ""
                    only = {_php_str(next(iter(_kids(i)), None)) for n, a in chain if n == "only"
                            for i in _kids(a[0] if a else None)}
                    except_ = {_php_str(next(iter(_kids(i)), None)) for n, a in chain if n == "except"
                               for i in _kids(a[0] if a else None)}
                    actions = [a for a in LARAVEL_RESOURCES
                               if head == "resource" or a[0] not in ("create", "edit")]
                    for action, method, suffix in _filter(actions, only, except_):
                        add(method, _join(prefix, name) + suffix.replace("{p}", "{%s}" % _singular(name)),
                            cls, action, stmt)
                elif "group" in names:
                    pfx = prefix
                    for n, a in chain:
                        if n == "prefix" and a:
                            pfx = _join(pfx, _php_str(a[0]) or "")
                        elif n == "group" and a and a[0] is not None and a[0].type == "array_creation_expression":
                            for pair in _kids(a[0]):          # Route::group(['prefix' => 'x'], ...)
                                k, v = (_kids(pair) + [None, None])[:2]
                                if _php_str(k) == "prefix":
                                    pfx = _join(pfx, _php_str(v) or "")
                    closure = next((a for n, args_ in chain if n == "group" for a in args_
                                    if a is not None and a.type in ("anonymous_function", "arrow_function")), None)
                    if closure is not None:
                        visit(_f(closure, "body"), pfx)

        visit(node, "")
    return out


# --- Phoenix -------------------------------------------------------------------------
PHOENIX_RESOURCES = [("index", "GET", ""), ("edit", "GET", "/:id/edit"), ("new", "GET", "/new"),
                     ("show", "GET", "/:id"), ("create", "POST", ""), ("update", "PATCH", "/:id"),
                     ("update", "PUT", "/:id"), ("delete", "DELETE", "/:id")]


def _ex_target(call) -> str:
    target = _f(call, "target")
    return _t(target) if target is not None and target.type == "identifier" else ""


def _ex_args(call):
    """(strings, aliases, atoms, {keyword: value node}) of an Elixir call."""
    strings, aliases, atoms, kw = [], [], [], {}
    for a in _kids(next((c for c in _kids(call) if c.type == "arguments"), None)):
        if a.type == "string":
            strings.append(_content(a, "quoted_content") or "")
        elif a.type == "alias":
            aliases.append(_t(a))
        elif a.type == "atom":
            atoms.append(_t(a).lstrip(":"))
        elif a.type == "keywords":
            for pair in _kids(a):
                kw[_t(_f(pair, "key")).strip().rstrip(":")] = _f(pair, "value")
    return strings, aliases, atoms, kw


def _phoenix(roots) -> list[dict]:
    out: list[dict] = []
    for root, full in _files(roots, {".ex", ".exs"}):
        if not (_contains(full, ":router") or _contains(full, "Phoenix.Router")):
            continue
        node = _parse(full, "elixir")
        if node is None:
            continue

        def add(method, path, cls, action, call):
            out.append({"framework": "phoenix", "method": method, "path": path, "cls": cls,
                        "name": action, "root": root, "table": full, "line": call.start_point[0] + 1})

        def visit(block, prefix: str, aliases: list[str]) -> None:
            for call in _kids(block):
                if call.type != "call":
                    continue
                name = _ex_target(call)
                strings, mods, atoms, kw = _ex_args(call)
                body = next((c for c in _kids(call) if c.type == "do_block"), None)
                if name == "scope" and body is not None:
                    visit(body, _join(prefix, strings[0] if strings else ""), aliases + mods[:1])
                elif name in HTTP_METHOD_NAMES and strings and mods and atoms:
                    add(name.upper(), _join(prefix, strings[0]), ".".join(aliases + mods[:1]),
                        atoms[0], call)
                elif name == "resources" and strings and mods:
                    only = {_t(a).lstrip(":") for a in _kids(kw.get("only"))}
                    except_ = {_t(a).lstrip(":") for a in _kids(kw.get("except"))}
                    base = _join(prefix, strings[0])
                    for action, method, suffix in _filter(PHOENIX_RESOURCES, only, except_):
                        add(method, base + suffix, ".".join(aliases + mods[:1]), action, call)
                    if body is not None:
                        segment = strings[0].strip("/").split("/")[-1]
                        visit(body, f"{base}/:{_singular(segment)}_id", aliases)

        for mod in _walk(node, {"call"}):
            if _ex_target(mod) == "defmodule":
                body = next((c for c in _kids(mod) if c.type == "do_block"), None)
                if body is not None and any(_ex_target(c) == "use" and ":router" in _t(c)
                                            or "Phoenix.Router" in _t(c) for c in _kids(body)):
                    visit(body, "", [])
    return out


def read(roots) -> list[dict]:
    """Every route every table under `roots` declares, in a fixed order (constraint 2)."""
    roots = [roots] if isinstance(roots, str) else list(roots)
    routes = _django(roots) + _rails(roots) + _laravel(roots) + _phoenix(roots)
    return sorted(routes, key=lambda r: (r["table"], r["line"], r["method"], r["path"]))


if __name__ == "__main__":
    import json
    for r in read(sys.argv[1:] or ["."]):
        print(json.dumps({k: v for k, v in r.items() if k not in ("root",)}, sort_keys=True))
