#!/usr/bin/env python3
"""build_wiki.py — Deterministic extraction -> Markdown vault.

Scans source under --src and emits one `<Entity>.md` per class, per React
component and per module function-group into data/structure/vault/. Every
reference to another discovered entity is written using strict Obsidian wikilink
syntax: [[EntityName]].

Two producers feed the same entity shape: Python via the stdlib `ast` module, and
JS/TS via the same tree-sitter extractor the flow map uses (`js_ts_extract`).
Renderers below care only about that shape, so a third producer is a new
`extract_*_entities` and nothing else.

Zero external Python dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

# ---------------------------------------------------------------------------
# Path resolution (relative to the skill root, not the CWD)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import long_path  # noqa: E402  (a page named after a long id can pass MAX_PATH)
from paths import DATA_DIR, TEMPLATES_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_VAULT = os.path.join(DATA_DIR, "structure", "vault")
TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "wiki_page_template.md")

from taxonomy import container_entry, decoration_term, infer_layer, is_test_path  # noqa: E402
import console  # noqa: E402  (stdout must survive a non-UTF-8 console)
from js_ts_extract import alias_targets, find_js_files, extract_js_files, frontend_degraded  # noqa: E402  (frontend, degrades to a no-op)
import py_extract as px  # noqa: E402  (Python, via tree-sitter)
from ids import SharedNames  # noqa: E402  (one id rule for both maps)
from langs_extract import class_locator, find_lang_files, extract_lang_files  # noqa: E402  (14 languages, via tree-sitter)

from taxonomy import source_dirs  # noqa: E402  (one definition of "not source")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def _name_of(node) -> str:
    """Best-effort dotted name for a decorator/base expression."""
    if node is None:
        return ""
    if node.type == "identifier":
        return px.text(node)
    if node.type == "attribute":
        return px.text(px.field(node, "attribute"))
    if node.type == "call":
        return _name_of(px.field(node, "function"))
    if node.type == "subscript":
        return _name_of(px.field(node, "value"))
    if node.type == "decorator":
        return _name_of(node.named_children[0]) if node.named_children else ""
    return px.text(node)


def iter_py_files(src: str):
    for root, dirs, files in os.walk(src):
        dirs[:] = source_dirs(root, dirs)
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def _rel_source(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace("\\", "/")
    return f"{os.path.basename(os.path.normpath(root))}/{rel}"


def extract_entities(roots: list[str]) -> list[dict]:
    """Every entity across one or more source roots, exact tiers first.

    Ordering is the collision rule: if two producers want the same name, the
    earlier one keeps it (see `build`). Python and JS/TS come from real parsers,
    so they win over the Java/Go/C# extractor. Within that, the order is
    arbitrary but fixed, which is what constraint 2 actually needs.
    """
    return extract_py_entities(roots) + extract_js_entities(roots) + extract_lang_entities(roots)


def extract_py_entities(roots: list[str]) -> list[dict]:
    """Python classes and module function-groups."""
    entities: list[dict] = []
    for root in roots:
        for path in iter_py_files(root):
            try:
                raw = px.read_source(path)
            except OSError as exc:
                print(f"  ! skipped {path}: {exc}", file=sys.stderr)
                continue
            tree = px.parse(raw)
            if tree is None:
                px.warn_missing()
                continue

            rel = _rel_source(path, root)
            _extract_from_tree(tree.root_node, raw, rel, entities)
    return entities


def _imported_names(root) -> set[str]:
    """Every name an `import` / `from ... import` binds in this module.

    `ast` gave `Import` and `ImportFrom` with a tidy `names` list. tree-sitter
    gives `import_statement` and `import_from_statement` whose children are the
    dotted names and aliases themselves, so the alias-wins rule is applied here
    instead of being read off an attribute.
    """
    names: set[str] = set()
    for node in px.walk(root):
        plain = node.type == "import_statement"
        if not plain and node.type != "import_from_statement":
            continue
        for child in node.named_children:
            if child.type == "dotted_name" and child == px.field(node, "module_name"):
                continue                      # the module in `from X import y`
            if child.type == "aliased_import":
                alias = px.field(child, "alias")
                if alias is not None:
                    names.add(px.text(alias))
            elif child.type == "dotted_name":
                # `import a.b.c` binds `a`; `from m import a.b` cannot occur.
                names.add(px.text(child).split(".")[0] if plain else px.text(child))
            elif child.type == "identifier":
                names.add(px.text(child))
    return names


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
    return "".join(px.text(c) for c in literal.children if c.type == "string_content")


def _extract_from_tree(root, source, rel, entities):
    # Module-level imported names (for reference resolution).
    imports = _imported_names(root)

    here: list[dict] = []
    # (entity, one node whose calls belong to it) -- a module group is its functions, so it
    # gets one pair per function.
    owners: list[tuple[dict, object]] = []
    module_funcs: list[dict] = []
    for decorators, node in px.defs_in(root, ("class_definition", "function_definition")):
        if node.type == "class_definition":
            ent = _class_entity(node, decorators, rel, imports, source)
            here.append(ent)
            owners.append((ent, node))
        else:
            module_funcs.append({
                "name": px.def_name(node),
                "doc": px.docstring_of(node).strip().splitlines()[0:1],
                "node": node,
            })

    if module_funcs:
        mod_name = os.path.splitext(os.path.basename(rel))[0]
        mod = {
            "name": _module_entity_name(mod_name),
            "kind": "module",
            "source": rel,
            "bases": [],
            "decorators": [],
            "doc": _module_docstring(root).strip(),
            "methods": [{"name": f["name"], "doc": (f["doc"][0] if f["doc"] else "")}
                        for f in module_funcs],
            "imports": sorted(imports),
            "lang": "py",
        }
        here.append(mod)
        owners += [(mod, f["node"]) for f in module_funcs]

    _add_same_file_refs(here, owners)
    entities.extend(here)


def _called_names(node) -> set[str]:
    """Bare names this subtree calls -- `helper()`, `Page()`. A method call states its
    receiver, which is the flow map's question, not this one's."""
    names: set[str] = set()
    for n in px.walk(node):
        if n.type != "call":
            continue
        fn = px.field(n, "function")
        if fn is not None and fn.type == "identifier":
            names.add(px.text(fn))
    return names


def _add_same_file_refs(ents: list[dict], owners: list[tuple[dict, object]]) -> None:
    """A name this file defines is a reference too: a class calling a function of its own
    module group, or a module function building a class beside it. Python resolved references
    from the import list alone, so nothing in a file ever pointed at anything else in it
    (r77). A node never references itself."""
    provides = _provided_names(ents)
    for ent, node in owners:
        found = {owner for name in _called_names(node)
                 for owner in [provides.get(name)] if owner and owner != ent["name"]}
        if found:
            ent["imports"] = sorted(set(ent["imports"]) | found)


def _base_nodes(cls):
    """Base-class expressions of a class definition (`ast`'s `cls.bases`)."""
    args = px.field(cls, "superclasses")
    if args is None:
        return []
    return [c for c in args.named_children if c.type != "keyword_argument"]


def _module_entity_name(mod: str) -> str:
    # snake_case module -> CamelCase-ish entity id, kept stable and readable.
    # Only the first letter is forced, so an already-CamelCase stem (OrderCard.tsx)
    # does not come back as "OrdercardModule".
    return "".join(part[:1].upper() + part[1:] for part in mod.split("_")) + "Module"


def _class_entity(node, decorator_nodes, rel: str, imports: set[str], source: str) -> dict:
    bases = [_name_of(b) for b in _base_nodes(node) if _name_of(b)]
    decorators = [_name_of(d) for d in decorator_nodes if _name_of(d)]
    methods = []
    abstract = False
    for _decs, item in px.defs_in(px.body_of(node)):
        doc = px.docstring_of(item)
        first = doc.strip().splitlines()[0] if doc.strip() else ""
        methods.append({"name": px.def_name(item), "doc": first})
        abstract = abstract or any(_name_of(d).split(".")[-1] == "abstractmethod" for d in _decs)
    base_names = {b.split(".")[-1] for b in bases}
    # Python states it by convention: a `Protocol` is an interface, an `ABC` or a class with
    # an `@abstractmethod` is abstract.
    kind = "interface" if "Protocol" in base_names else "abstract" if abstract or "ABC" in base_names else "class"
    return {
        "name": px.def_name(node),
        "kind": kind,
        "source": rel,
        # From the first decorator, like every node in both maps (finding #6).
        "line": px.line(node.parent if decorator_nodes else node), "end": px.end_line(node),
        "bases": bases,
        "decorators": decorators,
        "doc": px.docstring_of(node).strip(),
        "methods": methods,
        "imports": sorted(imports),
        "lang": "py",
    }


# ---------------------------------------------------------------------------
# Extraction: JS/TS (same extractor the flow map uses)
# ---------------------------------------------------------------------------
# Specifiers are written without an extension, so a resolved import has to be
# guessed back into a file the way a bundler would. Order is fixed, so the guess
# is deterministic.
JS_RESOLVE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _names_used(funcs: list[dict]) -> set[str]:
    """Every name a set of functions calls or renders."""
    used: set[str] = set()
    for fn in funcs:
        used.update(c["name"] for c in fn.get("calls", []))
        used.update(c["obj"] for c in fn.get("calls", [])
                    if c.get("obj") and c["type"] == "?")             # `errors.x()`: import * as errors
        used.update(fn.get("constructs", []))                                 # `new ApiError(...)`
        used.update(fn.get("components", []))
    return used


def _js_file_entities(res: dict, rel: str) -> list[dict]:
    """Entities defined by one JS/TS file, in the shape the renderer expects."""
    stem = os.path.splitext(os.path.basename(res["file"]))[0]
    ents: list[dict] = []

    for cls in res.get("classes", []):
        ents.append({
            "name": cls["name"], "kind": cls.get("kind") or "class", "source": rel, "lang": "js",
            "line": cls.get("line", 0), "end": cls.get("endLine", 0),
            "bases": cls.get("bases", []), "decorators": [],
            "doc": cls.get("doc", ""),
            "methods": [{"name": m["name"], "doc": m.get("doc", "")}
                        for m in cls.get("methods", [])],
            "uses": _names_used(cls.get("methods", [])),
            "renders": [],
        })

    module_funcs = []
    for fn in res.get("functions", []):
        if fn.get("jsx"):
            # A function that returns JSX is a React component, and a component is
            # a unit a reader navigates to -- so it gets its own page rather than
            # one more bullet on the module page.
            ents.append({
                "name": fn["name"], "kind": "component", "source": rel, "lang": "js",
                "line": fn.get("line", 0), "end": fn.get("endLine", 0),
                "bases": [], "decorators": [], "doc": fn.get("doc", ""), "methods": [],
                "uses": _names_used([fn]),
                "renders": fn.get("components", []),
            })
        else:
            module_funcs.append(fn)

    if module_funcs:
        ents.append({
            "name": _module_entity_name(stem), "kind": "module", "source": rel, "lang": "js",
            "bases": [], "decorators": [], "doc": "",
            "methods": [{"name": f["name"], "doc": f.get("doc", "")} for f in module_funcs],
            "uses": _names_used(module_funcs),
            "renders": [],
            # Next.js calls a page/layout/route export itself, as it does in the flow map.
            **({"entry": next((f["entry"] for f in module_funcs if f.get("entry")), "")}
               if any(f.get("entry") for f in module_funcs) else {}),
        })
    types = _type_names(res)
    if types:
        # A file's type declarations belong to its module -- or, when the file defines none,
        # to the entities it does define. A type position is a use: `type Api = typeof
        # setdatService` is why an IDE does not grey that import out (r76).
        for ent in [e for e in ents if e["kind"] == "module"] or ents:
            ent["uses"] |= types
    return ents


def _type_names(res: dict) -> set[str]:
    """The names a file's type declarations state: the object behind `typeof setdatService`,
    a property's type, and the type a `createContext<T>` carries."""
    names: set[str] = set()
    for entry in res.get("types", {}).values():
        refs = [entry["is"]] if entry.get("is") else list(entry.get("props", {}).values())
        names.update(r[len("typeof "):] if r.startswith("typeof ") else r for r in refs)
    names.update(res.get("contexts", {}).values())
    return {n for n in names if n}


def _provided_names(ents: list[dict]) -> dict[str, str]:
    """Name -> the entity of this file a reader reaches by writing it: an entity's own name,
    and every function a module group holds (a module group *is* its functions)."""
    provides: dict[str, str] = {}
    for ent in ents:
        provides[ent["name"]] = ent["name"]
        if ent["kind"] == "module":
            for m in ent["methods"]:
                provides.setdefault(m["name"], ent["name"])
    return provides


def _resolve_specifier(spec: str, from_file: str,
                       defs: dict[str, list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """(entity name, its file) for each entity the file a relative or tsconfig-aliased
    import points at defines."""
    if spec.startswith("."):
        bases = [os.path.normpath(os.path.join(os.path.dirname(from_file), spec))]
    else:
        # `@/utils/x` through the nearest tsconfig/jsconfig `paths`; a bare package
        # matches none and falls back to name matching.
        bases = [os.path.normpath(t) for t in alias_targets(spec, from_file)]
    for base in bases:
        candidates = [base]
        candidates += [base + ext for ext in JS_RESOLVE_EXTS]
        candidates += [os.path.join(base, "index" + ext) for ext in JS_RESOLVE_EXTS]
        for cand in candidates:
            names = defs.get(os.path.normcase(cand))
            if names is not None:
                return names
    return []


def extract_js_entities(roots: list[str]) -> list[dict]:
    """JS/TS classes, React components and module function-groups.

    Two passes, because import resolution needs to know what every file defines
    before it can resolve anything. That extra pass buys real precision: Python
    can only match import *names* against entity names, but a JS specifier names a
    *file*, so `import ... from "./api_client"` becomes an edge to that file's
    entities even when no name matches.

    With no JS/TS grammar installed this returns [] and `js_ts_extract` prints
    the one warning -- the Python vault still builds (hard constraint 1).
    """
    files: list[tuple[str, list[dict], dict]] = []
    defs: dict[str, list[tuple[str, str]]] = {}
    for root in roots:
        for res in extract_js_files(find_js_files(root)):
            ents = _js_file_entities(res, _rel_source(res["file"], root))
            files.append((res["file"], ents, res))
            defs[os.path.normcase(os.path.abspath(res["file"]))] = [(e["name"], e["source"]) for e in ents]

    entities: list[dict] = []
    for path, ents, res in files:
        # Imports are declared once per file but belong to whichever entity in it
        # actually uses the imported name. Attributing the whole file's imports to
        # every entity would give a component that renders one badge an edge to
        # every API the file touches -- an edge the reader then has to disprove.
        resolved = [(set(imp.get("names", [])),
                     _resolve_specifier(imp.get("from", ""), path, defs)
                     or [(n, "") for n in imp.get("names", [])])
                    for imp in res.get("imports", [])]
        provides = _provided_names(ents)
        for ent in ents:
            used = ent.pop("uses")
            refs = set(ent.pop("renders"))
            # A name this file defines itself is a reference too: `AdminLayout` calls
            # `getMainContentMargin`, which lives in its own file's module group. Only
            # imports were followed, so no module node ever had a same-file referrer (r77).
            refs |= {owner for name in used
                     for owner in [provides.get(name)] if owner and owner != ent["name"]}
            sources: dict[str, str] = {}
            for names, targets in resolved:
                if names & used:
                    for name, rel in targets:
                        refs.add(name)
                        if rel:
                            sources[name] = rel
            # Only names that turn out to be entities become edges (`render_entity`).
            ent["imports"] = sorted(refs)
            if sources:
                # The file each import named: the exact definition, even when another
                # file defines the same name (the normal/AAS copies of a real frontend).
                ent["import_sources"] = sources
            entities.append(ent)
    return entities


# ---------------------------------------------------------------------------
# Extraction: Java / Go / C#
# ---------------------------------------------------------------------------
def extract_lang_entities(roots: list[str]) -> list[dict]:
    """Classes, structs and modules -- plus a module function-group per file -- for every
    `langs_extract` language (Java, Go, C# and, since phase 7, eleven more).

    References come from what the source *states* -- bases, field types, parameter types,
    resolved call receivers, and `refs`: every other type a signature or body names (return
    types, generic arguments, locals, `X.class`, a static constant's class; `langs_extract.
    _type_refs`, r73). Never from the import list: that is a better source than Python's name
    matching and the only one available for Go, where files in the same package import each
    other not at all. `class_locator` settles which file a name means, including this one, so
    a reference between two classes of the same file resolves here without a special case.
    """
    files = [(_rel_source(res["file"], root), res)
             for root in roots for res in extract_lang_files(find_lang_files(root))]
    locate = class_locator(files)       # a class name two files define: which one this file means
    entities: list[dict] = []
    for rel, res in files:
        if True:
            stem = os.path.splitext(os.path.basename(res["file"]))[0]

            for cls in res.get("classes", []):
                # `refs` is every type the class's own source names -- return types, generic
                # arguments, locals, `X.class`, a static constant's class -- which is what an
                # IDE counts as a usage and what the declared-type list below missed (r73).
                refs = set(cls.get("bases", [])) | set(cls.get("fields", {}).values()) \
                    | set(cls.get("refs", []))
                for m in cls.get("methods", []):
                    refs.update(m.get("params", {}).values())
                    refs.update(m.get("refs", []))
                    refs.update(c["type"] for c in m.get("calls", []) if c["type"] not in ("", "?"))
                # A framework builds this class and calls into it: `@Configuration`, or a method
                # of its own that a framework calls (`@Scheduled`). `find_orphans` reads `entry`
                # on flow nodes already; structure nodes carried none at all (r75).
                entry = container_entry(cls.get("decorators", []),
                                        [m.get("entry") for m in cls.get("methods", [])])
                entities.append({
                    **({"entry": entry} if entry else {}),
                    "name": cls["name"], "kind": cls.get("kind") or "class", "source": rel,
                    "lang": res["lang"],
                    "line": cls.get("line", 0), "end": cls.get("endLine", 0),
                    "bases": cls.get("bases", []), "decorators": cls.get("decorators", []),
                    "doc": cls.get("doc", ""),
                    "methods": [{"name": m["name"], "doc": m.get("doc", "")}
                                for m in cls.get("methods", [])],
                    "imports": sorted(refs),
                    "import_sources": {r: f for r in sorted(refs) for f in [locate(r, rel)] if f},
                })

            funcs = res.get("functions", [])
            if funcs:
                refs = set()
                for fn in funcs:
                    refs.update(fn.get("params", {}).values())
                    refs.update(fn.get("refs", []))
                    refs.update(c["type"] for c in fn.get("calls", []) if c["type"] not in ("", "?"))
                entities.append({
                    "name": _module_entity_name(stem), "kind": "module", "source": rel,
                    "lang": res["lang"],
                    "bases": [], "decorators": [], "doc": "",
                    "methods": [{"name": f["name"], "doc": f.get("doc", "")} for f in funcs],
                    "imports": sorted(refs),
                })
    return entities


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def load_template() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def wikilink(name: str, known: set[str]) -> str:
    return f"[[{name}]]" if name in known else f"`{name}`"


def render_entity(ent: dict, known: set[str], template: str, names=None) -> str:
    references: set[str] = set()

    def resolve(name: str) -> str | None:
        """The entity a bare name here refers to, or None -- see core/ids.py."""
        target = names.target(name, ent["source"]) if names is not None else name
        return target if target in known else None

    def link(name: str) -> str:
        target = resolve(name)
        return f"[[{target}]]" if target else f"`{name}`"

    def resolve_ref(name: str) -> str | None:
        """Like `resolve`, but a name whose file the source settled (an import specifier, a
        Java package or import) links to that file's definition even when two files share it."""
        src = ent.get("import_sources", {}).get(name)
        if src and names is not None:
            target = names.id(name, src)
            return target if target in known else None
        return resolve(name)

    bases_md = []
    for b in ent["bases"]:
        target = resolve_ref(b)
        bases_md.append(f"- [[{target}]]" if target else f"- `{b}`")
        if target:
            references.add(target)
    decorators_md = []
    for d in ent["decorators"]:
        decorators_md.append(f"- {link(d)}")
        if resolve(d):
            references.add(resolve(d))

    # Imports that match known entities become references too.
    for imp in ent.get("imports", []):
        target = resolve_ref(imp)   # the specifier named the file: a shared name is not ambiguous here
        if target and target != ent["name"]:
            references.add(target)

    methods_md = []
    for m in ent["methods"]:
        doc = f" — {m['doc']}" if m["doc"] else ""
        methods_md.append(f"- `{m['name']}()`{doc}")

    refs_md = [f"- {wikilink(r, known)}" for r in sorted(references) if r != ent["name"]]

    summary = ent["doc"] if ent["doc"] else "_No docstring provided._"

    out = template
    out = out.replace("{{name}}", ent["name"])
    # An entity defined in a test file is test code whatever its name suggests, and
    # a React component is UI whatever it is called -- neither is a guess worth
    # letting the name rules override.
    layer = ("test" if is_test_path(ent["source"])
             else "ui" if ent["kind"] == "component"
             else infer_layer(ent.get("bare", ent["name"]), ent["decorators"], ent["bases"],
                              ent["source"]))
    out = out.replace("{{layer}}", layer)
    # A class or component has a range, so its page says `file:line` and `end`, like
    # a flow node (phase 6a): metrics, security attribution and clones can then find
    # it by range. `ent["source"]` itself stays the bare file -- it is what
    # SharedNames and the test-path rule are asked about. A module group is a whole
    # file and keeps no range.
    out = out.replace("{{source}}", f"{ent['source']}:{ent['line']}" if ent.get("line") else ent["source"])
    out = out.replace("{{end}}", str(ent["end"]) if ent.get("end") else "")
    out = out.replace("{{kind}}", ent["kind"])
    out = out.replace("{{lang}}", ent.get("lang", "py"))
    out = out.replace("{{entry}}", ent.get("entry", ""))
    out = out.replace("{{summary}}", summary)
    out = out.replace("{{bases}}", "\n".join(bases_md) if bases_md else "_None._")
    # The heading is the word this language actually uses -- Java's annotations are
    # not decorators, and C#'s attributes are neither (taxonomy.decoration_term).
    out = out.replace("{{decorators_label}}", decoration_term(ent.get("lang", "py")))
    out = out.replace("{{decorators}}", "\n".join(decorators_md) if decorators_md else "_None._")
    out = out.replace("{{methods}}", "\n".join(methods_md) if methods_md else "_None._")
    out = out.replace("{{references}}", "\n".join(refs_md) if refs_md else "_None._")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build(src, vault: str) -> int:
    roots = [os.path.abspath(s) for s in ([src] if isinstance(src, str) else src)]
    missing = [r for r in roots if not os.path.isdir(r)]
    if missing:
        print(f"error: source root(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    os.makedirs(vault, exist_ok=True)
    template = load_template()

    print(f"Scanning {', '.join(roots)} ...")
    entities = extract_entities(roots)
    if not entities:
        print("No entities found. Nothing to write.")
        return 0

    # One page per name, and one name per page. A name two *files* define used to
    # keep the first entity and skip the rest, so the second class was simply absent
    # from the structure map. Now each definition is qualified by its file -- the
    # same rule, and the same code, as the flow map (core/ids.py) -- and a name
    # defined once keeps its spelling.
    names = SharedNames((e["name"], e["source"]) for e in entities)
    for ent in entities:
        ent["bare"] = ent["name"]
        ent["name"] = names.id(ent["name"], ent["source"])
    names.report("structure entity")

    # Two entities of one name in ONE file cannot be told apart by any file
    # qualifier, so that case stays first-wins, and says so.
    seen: dict[str, str] = {}
    unique: list[dict] = []
    for ent in entities:
        prior = seen.get(ent["name"].lower())
        if prior is not None:
            print(f"  ! skipped duplicate entity {ent['name']} in {ent['source']} "
                  f"(already defined in {prior})")
            continue
        seen[ent["name"].lower()] = ent["source"]
        unique.append(ent)
    entities = unique

    # First pass: registry of all known entity names for wikilink resolution.
    known = {e["name"] for e in entities}

    # Clean stale generated pages so re-runs are idempotent.
    for fn in os.listdir(vault):
        if fn.endswith(".md"):
            os.remove(long_path(os.path.join(vault, fn)))

    written = 0
    for ent in entities:
        page = render_entity(ent, known, template, names)
        # Sanitize filename (entity names are identifiers, but be safe).
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", ent["name"])
        with open(long_path(os.path.join(vault, f"{safe}.md")), "w", encoding="utf-8") as fh:
            fh.write(page)
        written += 1

    scope = " (BACKEND ONLY - frontend skipped)" if frontend_degraded() else ""
    print(f"Wrote {written} vault page(s) to {vault}{scope}")
    if frontend_degraded():
        print("  WARNING: this vault is incomplete -- JS/TS files were not parsed, so frontend")
        print("           entities are missing. Do not commit it as the project's map; install")
        print("           the parser and rebuild (see the warning above).")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Scan Python source into a Markdown wiki vault.")
    parser.add_argument("--src", nargs="+", default=["./src"],
                        help="One or more source roots (e.g. --src ./backend ./frontend)")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Output vault directory")
    args = parser.parse_args(argv)
    console.safe_stdout()
    return build(args.src, args.vault)


if __name__ == "__main__":
    raise SystemExit(main())
