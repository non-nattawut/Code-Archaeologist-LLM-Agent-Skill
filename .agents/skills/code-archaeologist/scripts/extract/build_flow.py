#!/usr/bin/env python3
"""build_flow.py — Method-level call / request-flow analyzer.

Where build_wiki.py maps *structure* (which classes reference which), this maps
*behavior*: it resolves method-to-method calls into a call graph so you can trace
an actual request flow, e.g.

    OrderController.create_order -> OrderService.place_order -> OrderRepository.save

Each node is a method/function and carries a description of what it does, its
signature, and its callers/callees. Controller methods are marked as `endpoint`
roots so request flows have a clear entry point.

Outputs (deterministic; tree-sitter is the only dependency; Python 3.10+):
  data/flow_graph.json   nodes (methods) + edges (calls)
  data/flow/<Node>.md    one note per method/function, with [[wikilinks]]

Call resolution is heuristic (no type inference engine):
  - self.<attr>.m()  -> attr type from __init__ annotations / assignments
  - <param>.m()      -> param type from the method's own annotations
  - <local>.m()      -> local assigned via `x = SomeClass()`
  - self.m() / m()   -> same class / known module function
Unresolved (external/stdlib) calls are dropped to keep the graph readable.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import long_path  # noqa: E402  (a note named after a long id can pass MAX_PATH)
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_FLOW_DIR = os.path.join(DATA_DIR, "flow", "notes")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
# Persistent cache of AI-written summaries, keyed by node id -> {hash, summary}.
DESCRIPTIONS_PATH = os.path.join(CACHE_DIR, "descriptions.json")
# Transient list of nodes that still need an AI summary (agent fills these in).
PENDING_PATH = os.path.join(CACHE_DIR, "pending_descriptions.json")

def _hash(code: str) -> str:
    return hashlib.sha1((code or "").encode("utf-8")).hexdigest()[:12]

def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return default

def _save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")

import call_ctx  # noqa: E402  (where a call is written: line, loop, branch)
from taxonomy import INHERITANCE_LINKS, infer_layer, is_test_path, precision_of, ROUTE_DECORATOR_RE  # noqa: E402
from py_extract import find_py_files, extract_py_files  # noqa: E402  (Python, via tree-sitter)
from ids import SharedNames as FlowIds, bare  # noqa: E402  (one id rule for both maps)
from js_ts_extract import find_js_files, extract_js_files, frontend_degraded   # noqa: E402
from langs_extract import class_locator, find_lang_files, extract_lang_files  # noqa: E402  (14 languages, via tree-sitter)
import route_tables  # noqa: E402  (Django / Rails / Laravel / Phoenix route tables)


def _dedupe_routes(routes: list[dict]) -> list[dict]:
    """Unique routes in a fixed order (constraint 2: same source, same bytes)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for r in sorted(routes, key=lambda r: (r["path"], r["method"])):
        key = (r["method"], r["path"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out

def _norm_path(path: str) -> str:
    """Normalize a URL/route path so every framework's param syntax compares equal.

    Handles `:id` (Express/Nest), `{id}` (FastAPI), `<id>` and `<int:id>` (Flask),
    and Nest's optional `:id?`. A query string is not part of the route.
    """
    path = path.split("?", 1)[0]        # a query string is not part of the route
    segs = []
    for seg in path.strip("/").split("/"):
        if not seg:
            continue
        if seg.startswith(":") or (seg.startswith("{") and seg.endswith("}")) \
                or (seg.startswith("<") and seg.endswith(">")) or seg.startswith("*"):
            segs.append("*")
        else:
            segs.append(seg)
    return "/" + "/".join(segs)

def _api_edges(methods: dict) -> set[tuple[str, str]]:
    """Link frontend HTTP calls to backend route handlers (method + path match).

    Exact `(METHOD, path)` first. Failing that, two documented fallbacks, each only
    when exactly one route matches: a route whose path is a *suffix* of the call's
    -- a frontend `/api/orders` reaching a handler registered as `/orders` under an
    `/api` mount -- and its mirror, a call whose path is a suffix of the route's --
    `/orders/list` sent through an axios `baseURL` ending in `/api`, reaching
    `/api/orders/list`. Neither guesses when two routes could both be meant.
    """
    routes: dict[tuple[str, str], list[str]] = {}
    for nid, info in methods.items():
        for r in info.get("routes") or []:
            routes.setdefault((r["method"].upper(), _norm_path(r["path"])), []).append(nid)

    edges: set[tuple[str, str]] = set()
    for nid, info in methods.items():
        for h in info.get("http") or []:
            method, url = h["method"].upper(), _norm_path(h["url"])
            # A URL with no literal segment -- "" from `get(ENDPOINT[s])`, `/*` from
            # `${base}` -- says nothing about where it goes. Normalized, "" is "/", and
            # it linked to whichever handler serves `GET /` (found on a real repository).
            segs = [s for s in url.split("/") if s]
            if not h["url"] or (segs and all(s == "*" for s in segs)):
                continue
            owners = (_owners(routes, method, url) or _suffix_match(routes, method, url)
                      or _within_route(routes, method, url))
            if owners and len(owners) == 1 and owners[0] != nid:
                edges.add((nid, owners[0]))
    return edges

def _owners(routes: dict, method: str, path: str) -> list[str]:
    """Handlers registered for `path`, counting the ones registered for every verb.

    A framework can register a path without naming a verb -- Go's
    `mux.HandleFunc("/orders", h)` serves all of them -- which `_route_of` records
    as the verb `ANY`. Such a route really does answer this call, so it is a match,
    not a near miss.
    """
    return (routes.get((method, path)) or []) + (routes.get(("ANY", path)) or [])

def _suffix_match(routes: dict, method: str, url: str) -> list[str] | None:
    """Routes whose path is a trailing run of *whole segments* of `url`, same verb.

    Segment-aligned on purpose: `/api/orders` matches a route `/orders`, but
    `/myorders` must not.
    """
    parts = url.strip("/").split("/")
    candidates = {"/" + "/".join(parts[i:]) for i in range(1, len(parts))}
    hits: list[str] = []
    for suffix in candidates:
        hits.extend(_owners(routes, method, suffix))
    return sorted(set(hits)) or None

def _within_route(routes: dict, method: str, url: str) -> list[str] | None:
    """Routes whose path *ends with* `url` in whole segments, same verb.

    The mirror of `_suffix_match`: the prefix lives in the client (an axios
    `baseURL` ending in `/api`) instead of in the server's mount. Only for a call
    whose first segment is a literal -- `/*/login`, with its base unknown, says too
    little to be placed inside a longer route.
    """
    parts = url.strip("/").split("/")
    if not parts[0] or parts[0] == "*":
        return None
    tail = "/" + "/".join(parts)
    hits = [nid for (m, path), owners in routes.items() if m in (method, "ANY")
            and path != tail and path.endswith(tail) for nid in owners]
    return sorted(set(hits)) or None

def _rel_source(path: str, root: str) -> str:
    """Path relative to its root, prefixed with the root's name so monorepo
    areas (backend/… vs frontend/…) are distinguishable in the graph."""
    rel = os.path.relpath(path, root).replace("\\", "/")
    return f"{os.path.basename(os.path.normpath(root))}/{rel}"


# Flow ids: bare where a name is defined in one file, file-qualified where it is not.
#
# A module function's id is its name and a method's is `Class.method`, so every
# `main()` in every script used to be ONE node -- and it inherited every
# definition's call edges, because each definition's calls were resolved under the
# shared id. On the skill's own code that was 25 shared ids and 72 false edges.
# Now only the ids that actually collide are qualified by their file
# (`tests_map.build`, `report.build`), so an id that is unique today keeps its
# spelling -- `sample_src` has no collisions and its graph did not move a byte.
#
# `_claim` stays as a guard: after qualification two definitions in different
# files can no longer share a final id, so if it ever fires, an extractor emitted an
# id the pre-scan did not see.
_COLLISIONS: list[tuple[str, str, str]] = []
_COLLIDED: set[str] = set()

def _file_of(node: dict) -> str:
    return (node.get("source") or "").rpartition(":")[0]

def _claim(methods: dict, nid: str, node: dict) -> None:
    """`methods[nid] = node`, noting when `nid` already names another file's code.

    Only a clash *across files* is noted: within one file a shared id is the
    deliberate overload fold (`signatures`), not an accident.
    """
    prev = methods.get(nid)
    if prev is not None and _file_of(prev) != _file_of(node) and nid not in _COLLIDED:
        _COLLIDED.add(nid)
        _COLLISIONS.append((nid, _file_of(prev), _file_of(node)))
    methods[nid] = node

def _report_collisions(limit: int = 8) -> None:
    """The guard's voice: a final id still shared across files is an extractor bug."""
    for nid, first, second in _COLLISIONS[:limit]:
        print(f"  ! id collision after qualification (a bug): {nid} is defined in {first}"
              f" and in {second}", file=sys.stderr)

def _local_names(members: list[dict]) -> list[str]:
    """Each member's name within its scope: bare, or `name(T1,T2)` when the scope overloads it.

    Every method is its own node, overloads included. Ids used to carry no parameter
    types, so an overload set was ONE node carrying every overload's calls but only
    one overload's range (finding #8). Only a name the scope defines twice changes;
    `sig` exists only for the languages with overloading (`langs_extract.OVERLOADING`).
    """
    counts: dict[str, int] = {}
    for m in members:
        counts[m["name"]] = counts.get(m["name"], 0) + 1
    return [f'{m["name"]}({m["sig"]})' if counts[m["name"]] > 1 and "sig" in m else m["name"]
            for m in members]

def _pick_overload(cands: list, args: list[str], rel: str) -> str | None:
    """The one overload a call with these argument kinds can mean, or None.

    Argument count first, then every argument whose type the source states; an
    unstated argument, or a parameter whose type is not a plain name, rules nothing
    out. Two survivors is an ambiguous call, and it is dropped rather than guessed.
    A varargs overload (`...T` last) is considered only when no fixed-arity one fits,
    which is Java's own order.
    """
    if len({r for _, _, r in cands}) > 1:
        cands = [c for c in cands if c[2] == rel]    # as with a shared name: the caller's file

    def fit(kinds: list[str]) -> bool:
        if kinds and kinds[-1].startswith("..."):
            fixed = kinds[:-1]
            if len(args) < len(fixed):
                return False
            kinds = fixed + [kinds[-1][3:]] * (len(args) - len(fixed))
        return len(kinds) == len(args) and all(
            p == "*" or not a or a == p or (a == "#int" and p == "#float") for a, p in zip(args, kinds))

    for varargs in (False, True):
        fits = {pid for pid, kinds, _ in cands
                if bool(kinds and kinds[-1].startswith("...")) == varargs and fit(kinds)}
        if fits:
            return fits.pop() if len(fits) == 1 else None
    return None

def _extracted_defs(files):
    """Provisional ids from JS/TS or Java/Go/C# extraction results: (rel, res) pairs."""
    for rel, res in files:
        functions = res.get("functions", [])
        for local in _local_names(functions):
            yield local, rel
        for cls in res.get("classes", []):
            for local in _local_names(cls.get("methods", [])):
                yield f'{cls["name"]}.{local}', rel
        for obj in res.get("objects", []):               # JS/TS: `api.approve` in an object literal
            for m in obj["members"]:
                yield f'{obj["name"]}.{m["name"]}', rel
        for r in res.get("routes", []):
            if not r.get("handler"):                     # an inline handler is its own node
                yield f'{r["method"]} {r["path"]}', rel

def analyze(roots: list[str]):
    """Two-pass analysis across one or more source roots (Python + JS/TS)."""
    _COLLISIONS.clear()
    _COLLIDED.clear()
    methods: dict[str, dict] = {}          # node_id -> info
    class_methods: dict[str, set[str]] = {}  # ClassName -> {method names}
    func_nodes: dict[str, str] = {}         # module function name -> its name (ids via `ids`)
    # Deferred call sites, resolved in pass 2:  (caller_id, class_ctx, ctx, node)
    pending: list[tuple[str, str | None, dict, object]] = []
    classes: list[tuple[str, str, str, list[str]]] = []   # (producer, class, file, bases): `implements`
    abstract_py: set[str] = set()      # Python `@abstractmethod`s: a body that is a declaration

    # Read every source once, then decide every id before building any node.
    py_files = [(_rel_source(res["file"], root), res)
                for root in roots for res in extract_py_files(find_py_files(root))]
    js_files = [(_rel_source(res["file"], root), res)
                for root in roots for res in extract_js_files(find_js_files(root))]
    lang_files = [(_rel_source(res["file"], root), res)
                  for root in roots for res in extract_lang_files(find_lang_files(root))]
    ids = FlowIds(itertools.chain(_extracted_defs(py_files), _extracted_defs(js_files),
                                  _extracted_defs(lang_files)))

    py_methods, py_edges, abstract_py = _analyze_py(py_files, ids)
    for nid, node in py_methods.items():
        _claim(methods, nid, node)
    edges: set[tuple[str, str, str]] = set()
    # Where each call link is written (`call_ctx`): kept beside `edges`, never in it, so the
    # edge tuples every tool reads stay exactly what they were.
    sites: dict[tuple[str, str], dict] = {}
    for (s, t), site in py_edges.items():
        edges.add((s, t, "calls"))
        call_ctx.merge(sites.setdefault((s, t), {}), site)

    # --- Frontend (JS/TS): merge nodes + call edges into the same graph ---
    js_methods, js_edges, js_renders, js_passes = _analyze_js(js_files, ids)
    for nid, node in js_methods.items():
        _claim(methods, nid, node)
    for (s, t), site in js_edges.items():
        if s in methods and t in methods and s != t:
            edges.add((s, t, "calls"))
            call_ctx.merge(sites.setdefault((s, t), {}), site)
    for s, t in js_renders:                    # `<Dashboard />`: the component tree, not a call
        if s in methods and t in methods and s != t:
            edges.add((s, t, "renders"))
    for s, t in js_passes:                     # `onClick={run}`: handed over, not called here
        if s in methods and t in methods and s != t:
            edges.add((s, t, "passes"))

    # --- Java / Go / C#: same graph, same shape ---
    lang_methods, lang_edges = _analyze_lang(lang_files, ids)
    for nid, node in lang_methods.items():
        _claim(methods, nid, node)
    for (s, t), site in lang_edges.items():
        if s in methods and t in methods and s != t:
            edges.add((s, t, "calls"))
            call_ctx.merge(sites.setdefault((s, t), {}), site)

    # --- Implementations: a method joined to the one its class's base defines ---
    for producer, files in (("py", py_files), ("js", js_files), ("lang", lang_files)):
        for rel, res in files:
            classes.extend((producer, c["name"], rel, c.get("bases") or []) for c in res.get("classes", []))
    locate = class_locator(lang_files)
    for s, t in _implements_links(methods, classes, locate):
        # Filling in a declaration -- no body of its own to run -- is `implements`; replacing
        # a method that has a body is `overrides`. Both are walked the same way.
        edges.add((s, t, "implements" if methods[t].get("declaration") or t in abstract_py else "overrides"))
    for nid in _overridden_everywhere(methods, classes, locate) - abstract_py:
        methods[nid]["overridden"] = True

    # --- Route tables (Django, Rails, Laravel, Phoenix): a route declared away from
    # its handler, attached exactly as a decorator route is -- before the cross-stack
    # pass below, which is what reads routes.
    _attach_table_routes(route_tables.read(roots), methods)

    # Test code gets its own layer, in one pass so both extractors agree. It is not
    # application code, and analyze.py must not count it as dead: a runner calls it.
    for info in methods.values():
        if is_test_path(info.get("source") or ""):
            info["layer"] = "test"

    # --- Cross-stack: link frontend HTTP calls to backend route handlers ---
    for s, t in _api_edges(methods):
        edges.add((s, t, "http"))

    # `precision` needs the edges, so it is computed here rather than at extraction:
    # two of its three reasons are properties of what a node *calls*, not of the
    # node itself.
    ids.report("flow id")
    _report_collisions()
    for src_id, dst_id, _type in edges:
        if _type in ("renders", "passes") or _type in INHERITANCE_LINKS:
            continue        # none is a call: never "Delegates to", never precision
        methods[src_id]["calls"].append(dst_id)
        methods[dst_id]["callers"].append(src_id)
        if _type == "calls" and sites.get((src_id, dst_id)):
            methods[src_id].setdefault("call_sites", {})[dst_id] = sites[(src_id, dst_id)]
    for info in methods.values():
        info["calls"] = sorted(set(info["calls"]))
        info["callers"] = sorted(set(info["callers"]))
    _split_dropped(methods)
    for info in methods.values():
        reasons = precision_of(info, [methods[c] for c in info["calls"] if c in methods])
        if reasons:
            info["precision"] = reasons

    return methods, sorted(edges)

def _base_name(text: str) -> str:
    """`com.shop.PricingRule<T>`, `abc.ABC`, `Generic[T]` -> the bare class name."""
    for bracket in "<[(":
        text = text.split(bracket)[0]
    return text.split(".")[-1].split("::")[-1].strip()

def _base_resolver(classes: list, locate=None):
    """(resolve, bases_of) for a list of (producer, class, file, bases).

    `resolve(producer, base, file)` is the (class, file) a base names -- found by name
    within one producer, in the naming class's own file first, else only when exactly
    one file defines it, else (Java-family languages) the file the naming file's package
    and imports settle (`langs_extract.class_locator`) -- or None.
    `bases_of[(class, file)]` is (producer, bases).
    """
    files_of: dict[tuple[str, str], list[str]] = {}
    bases_of: dict[tuple[str, str], tuple[str, list[str]]] = {}
    for producer, name, rel, bases in classes:
        files_of.setdefault((producer, name), []).append(rel)
        bases_of[(name, rel)] = (producer, bases)

    def resolve(producer: str, base: str, rel: str):
        name = _base_name(base)
        rels = files_of.get((producer, name), [])
        pick = rel if rel in rels else (rels[0] if len(rels) == 1 else None)
        if pick is None and locate is not None and producer == "lang":
            found = locate(name, rel)
            pick = found if found in rels else None
        return (name, pick) if pick else None
    return resolve, bases_of

def _implements_links(methods: dict, classes: list, locate=None) -> set[tuple[str, str]]:
    """(implementation, declaration) for every method a base of its class also defines.

    A call through an interface stops at its declaration (`PricingRule.price`), and
    which class runs is decided outside the source -- a constructor argument, a
    Spring bean. What the source *does* state is `class FlatRate implements
    PricingRule`, so each method a class defines is linked to the same-named method
    of its nearest base, walking past a base that defines none (an abstract class in
    between). A base is found by name within one producer: the class's own file
    first, else only when exactly one file defines it. Overloads pair by parameter
    types. Nothing here says which implementation runs.
    """
    members: dict[tuple[str, str], dict[str, list[str]]] = {}
    for nid, info in methods.items():
        if info.get("cls"):
            members.setdefault((info["cls"], _file_of(info)), {}).setdefault(info["name"], []).append(nid)
    resolve, bases_of = _base_resolver(classes, locate)

    links: set[tuple[str, str]] = set()
    for key, (producer, _bases) in sorted(bases_of.items()):
        for name, impls in sorted(members.get(key, {}).items()):
            seen, queue = {key}, [key]
            while queue:
                cur = queue.pop(0)
                for base in bases_of.get(cur, (producer, []))[1]:
                    ancestor = resolve(producer, base, cur[1])
                    if ancestor is None or ancestor in seen:
                        continue
                    seen.add(ancestor)
                    declared = members.get(ancestor, {}).get(name)
                    if declared:
                        links |= _pair_overloads(impls, declared)
                    else:
                        queue.append(ancestor)
    return links

def _overridden_everywhere(methods: dict, classes: list, locate=None) -> set[str]:
    """Methods with a body that every subclass in the graph replaces.

    An abstract class's default `saveDetails()` whose only subclass overrides it never runs,
    yet it is not dead code in the usual sense: a new subclass would inherit it. So it is
    named `overridden` and listed apart from orphans. A class with no subclass in the graph
    replaces nothing, and one subclass that keeps the body is enough for it to run.
    """
    members: dict[tuple[str, str], set[str]] = {}
    for info in methods.values():
        if info.get("cls"):
            members.setdefault((info["cls"], _file_of(info)), set()).add(info["name"])
    resolve, bases_of = _base_resolver(classes, locate)
    children: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for key, (producer, bases) in bases_of.items():
        for base in bases:
            parent = resolve(producer, base, key[1])
            if parent is not None and parent != key:
                children.setdefault(parent, set()).add(key)

    def replaced(key: tuple[str, str], name: str, seen: frozenset) -> bool:
        kids = children.get(key)
        return bool(kids) and all(name in members.get(k, ()) or (k not in seen and replaced(k, name, seen | {k}))
                                  for k in kids)

    out = set()
    for nid, info in methods.items():
        key = (info.get("cls"), _file_of(info))
        if info.get("cls") and not info.get("declaration") and replaced(key, info["name"], frozenset({key})):
            out.add(nid)
    return out

def _pair_overloads(impls: list[str], declared: list[str]) -> set[tuple[str, str]]:
    """One of each: that pair. Several: only the ids whose parameter types agree."""
    if len(impls) == 1 and len(declared) == 1:
        return {(impls[0], declared[0])}
    params = {nid[nid.index("("):]: nid for nid in declared if "(" in nid}
    return {(nid, params[nid[nid.index("("):]]) for nid in impls
            if "(" in nid and nid[nid.index("("):] in params}

def _js_node(nid: str, name: str, cls, layer: str, kind: str, data: dict, rel: str) -> dict:
    doc = (data.get("doc") or "").strip()
    http = data.get("http", [])
    calls = data.get("calls", [])
    # Names only, deduped in source order -- the key the description cache has always
    # used. Adding the newly-kept receiver type here would re-key every JS node that
    # calls a method and throw away every user's cached summaries for no gain: what a
    # node delegates to is read from the resolved edges, not from this.
    named = list(dict.fromkeys(c["name"] for c in calls))
    content = json.dumps({"n": name, "c": sorted(named), "h": http, "d": doc}, sort_keys=True)
    code = (f"// {rel}\n{name}(...) calls {', '.join(named) or 'nothing'}"
            + (f"; http {http}" if http else ""))
    return {
        "id": nid, "name": name, "cls": cls, "layer": layer, "kind": kind,
        "signature": f"{name}()",
        "doc": doc.splitlines()[0] if doc else "",
        "source": f"{rel}:{data.get('line', 0)}", "end": data.get("endLine", 0),
        "calls": [], "callers": [],
        "hash": _hash(content), "code": code, "http": http, "lang": "js",
        "routes": _dedupe_routes(data.get("routes") or []),
        **({"entry": data["entry"]} if data.get("entry") else {}),   # next:page, next:route
    }

def _attach_routes(routes: list[dict], methods: dict, raw_calls: list, make_node,
                   rel: str, ids: "FlowIds") -> None:
    """Router registrations -> the handler's node, or an endpoint node of their own.

    Express (`router.post("/x", h)`) and Go (`mux.HandleFunc("POST /x", h)`) register
    routes the same way and so are read the same way: a named handler attaches its
    route to that function's own node; an inline literal has no node to attach to,
    so the registration itself becomes the endpoint ("POST /orders").
    """
    for r in routes:
        handler = r.get("handler")
        route = {"method": r["method"], "path": r["path"]}
        target = ids.target(handler, rel) if handler else None
        if handler and target in methods:
            methods[target]["routes"] = _dedupe_routes(methods[target]["routes"] + [route])
            methods[target]["kind"] = "endpoint"
            methods[target]["layer"] = "controller"
        elif not handler:
            label = f'{r["method"]} {r["path"]}'
            nid = ids.id(label, rel)
            node = make_node(nid, dict(r, routes=[route]))
            node["signature"] = label  # the route is the signature; `nid()` reads as nonsense
            _claim(methods, nid, node)
            raw_calls.append((nid, r.get("calls", []), rel))

def _attach_table_routes(table_routes: list[dict], methods: dict) -> None:
    """Each route-table route -> the one node its handler reference names, or nothing.

    A reference is a (class, method) pair -- `orders#index`, `[OrderController::class,
    'index']`, `OrderController, :index` -- or, for a Django function view, a name
    pinned to the file its import points at. It must name exactly one node: none
    means the handler is not in the graph (a typo, a generated controller, code
    outside --src), and more than one means two files define it and the table cannot
    say which. Both are dropped and counted -- never guessed.
    """
    by_member: dict[tuple, list[str]] = {}
    for nid, info in methods.items():
        by_member.setdefault((info.get("cls"), info.get("name")), []).append(nid)
    dropped: list[str] = []
    for r in table_routes:
        if r.get("verbs"):              # a Django class-based view: one route per method it defines
            hits = [(nid, name.upper()) for name in route_tables.HTTP_METHOD_NAMES
                    for nid in by_member.get((r["cls"], name), [])]
        else:
            hits = [(nid, r["method"]) for nid in by_member.get((r.get("cls"), r.get("name")), [])]
        if r.get("module"):
            rel = _rel_source(r["module"], r["root"])
            hits = [(nid, m) for nid, m in hits if _file_of(methods[nid]) == rel]
        per_verb: dict[str, set[str]] = {}
        for nid, m in hits:
            per_verb.setdefault(m, set()).add(nid)
        if not hits or any(len(v) > 1 for v in per_verb.values()):
            dropped.append(f'{r["method"]} {r["path"]}')
            continue
        for nid, m in hits:
            node = methods[nid]
            node["routes"] = _dedupe_routes((node.get("routes") or []) + [{"method": m, "path": r["path"]}])
            node["kind"] = "endpoint"
            node["layer"] = "controller"
    if dropped:
        shown = ", ".join(dropped[:5]) + (f" (+{len(dropped) - 5} more)" if len(dropped) > 5 else "")
        print(f"  ! {len(dropped)} route-table route(s) name no single handler in the graph, so they"
              f" are not attached: {shown}.", file=sys.stderr)

def _analyze_py(py_files, ids: "FlowIds"):
    """Python nodes and call links, from `py_extract`'s dicts.

    The same two passes every producer gets: build every node first, because a call
    can only be resolved once the graph knows which classes and module functions
    exist, then walk the `{name, type}` call list each node carries. What the source
    states about a receiver was decided in `py_extract._calls`; what the *graph* knows
    is decided here, and the two were one function inside this file until phase 10.

    Returns (nodes, call links, the ids of `@abstractmethod`s -- a body that is really
    a declaration, which decides `implements` against `overrides`).
    """
    methods: dict[str, dict] = {}
    class_methods: dict[str, set[str]] = {}
    func_nodes: dict[str, str] = {}
    pending: list[tuple[str, str | None, str, list[dict]]] = []
    abstract: set[str] = set()

    for rel, res in py_files:
        for cls in res["classes"]:
            cls_name = cls["name"]
            layer = infer_layer(cls_name, cls["decorators"], cls["bases"], rel)
            class_methods.setdefault(cls_name, set())
            for m in cls["methods"]:
                node_id = ids.id(f'{cls_name}.{m["name"]}', rel)
                class_methods[cls_name].add(m["name"])
                if m["abstract"]:
                    abstract.add(node_id)
                is_endpoint = bool(m["routes"]) or layer == "controller" \
                    or any(ROUTE_DECORATOR_RE.search(d) for d in m["decorators"])
                _claim(methods, node_id, {
                    "id": node_id, "name": m["name"], "cls": cls_name, "layer": layer,
                    "kind": "endpoint" if is_endpoint else "method",
                    "signature": m["signature"],
                    "doc": m["doc"],
                    # A range opens at the first decorator (finding #6): what a node owns
                    # includes the decorators that route it, guard it or cache it.
                    "source": f'{rel}:{m["line"]}', "end": m["endLine"],
                    "calls": [], "callers": [],
                    "hash": _hash(m["code"]), "code": m["code"], "routes": m["routes"],
                })
                pending.append((node_id, cls_name, rel, m["calls"]))

        for fn in res["functions"]:
            fn_name = fn["name"]
            node_id = ids.id(fn_name, rel)
            func_nodes[fn_name] = fn_name
            # Flask's normal shape is @app.route on a module-level def, not on a class
            # method -- so a whole framework was invisible until this loop asked the same
            # question the class loop already asked.
            routes = fn["routes"]
            _claim(methods, node_id, {
                "id": node_id, "name": fn_name, "cls": None,
                "layer": "controller" if routes else "function",
                "kind": "endpoint" if routes else "function", "signature": fn["signature"],
                "doc": fn["doc"],
                "source": f'{rel}:{fn["line"]}', "end": fn["endLine"],
                "calls": [], "callers": [],
                "hash": _hash(fn["code"]), "code": fn["code"], "routes": routes,
            })
            pending.append((node_id, None, rel, fn["calls"]))

    # --- Pass 2: what the graph knows ---
    edges: dict[tuple[str, str], dict] = {}       # (caller, callee) -> where it is written
    for caller_id, cls_ctx, rel, calls in pending:
        targets, dropped, untyped = _py_targets(calls, cls_ctx, rel, class_methods, func_nodes, ids)
        _record_dropped(methods[caller_id], dropped, untyped)
        for target, site in targets.items():
            if target != caller_id:
                call_ctx.merge(edges.setdefault((caller_id, target), {}), site)

    # A module's top-level code runs when it is imported -- `app = create_app()`, the
    # `if __name__ == "__main__": raise SystemExit(main())` guard -- and has no node to
    # draw a link from, so what it calls looked dead. Named instead, as in JS/TS.
    for rel, res in py_files:
        for called in res["module_calls"]:
            if called not in func_nodes:
                continue
            target = ids.target(func_nodes[called], rel)    # a shared `main`: this file's
            if target in methods and not methods[target].get("entry"):
                methods[target]["entry"] = "module"
    return methods, edges, abstract

def _py_targets(calls: list[dict], cls_ctx: str | None, rel: str,
                class_methods: dict[str, set[str]], func_nodes: dict[str, str],
                ids: "FlowIds") -> tuple[dict[str, dict], list[str], list[str]]:
    """(in-graph call targets, each with where it is written, the names that did not
    resolve, and of those the ones made through a receiver whose type the source never
    stated).

    `type` is what `py_extract._calls` read from the source; the question here is only
    whether the graph has such a member. A call whose receiver *is* typed and whose
    target is simply not in the graph is dropped but **not** untyped -- it is the
    boundary of the codebase, not of the resolver, and only the second earns
    `precision: name-matched`.
    """
    found: dict[str, dict] = {}
    dropped: list[str] = []
    untyped: list[str] = []

    def exists(cls_name, method):
        return cls_name in class_methods and method in class_methods[cls_name]

    for call in calls:
        name, kind = call["name"], call["type"]
        target = None
        typed = True
        if kind == "":                                   # helper()
            if name in func_nodes:
                target = func_nodes[name]
        elif kind == "self":                             # self.method()
            if cls_ctx and exists(cls_ctx, name):
                target = f"{cls_ctx}.{name}"
        elif kind == "?":
            # A bare receiver of unknown type may still be a class the graph knows:
            # `OrderRepository.get(...)`, a static or class method named through its
            # class. Anything else is a receiver the source never typed.
            recv = call.get("recv")
            if recv and recv in class_methods:
                if exists(recv, name):
                    target = f"{recv}.{name}"
            else:
                typed = False
        elif exists(kind, name):                         # a receiver the source typed
            target = f"{kind}.{name}"
        if target:
            target = ids.target(target, rel)             # a shared name: the caller's own file only
        if target:
            call_ctx.merge(found.setdefault(target, {}), call)
        else:
            dropped.append(name)     # library / stdlib / unresolvable: named, not a link
            if not typed:
                untyped.append(name)
    return found, dropped, untyped

def _analyze_js(js_files: list, ids: "FlowIds"):
    """JS/TS functions/methods as flow nodes, and their calls resolved.

    A bare call resolves to a module function by name; a method call resolves
    through the receiver's class where the source states it -- a `new X()`, a typed
    parameter, field or local, or `this`. Until the receiver was kept
    (`js_ts_extract._collect_calls`) and class methods were made candidates, no call
    could land on a JS/TS class method at all: the TypeScript fixture resolved 0 of
    its 3 edges where the typed languages resolved 3 of 3.
    """
    methods: dict[str, dict] = {}
    func_nodes: set[str] = set()
    class_methods: dict[str, set[str]] = {}
    raw_calls: list[tuple[str, list[dict], str]] = []
    raw_renders: list[tuple[str, list[str], str]] = []
    raw_constructs: list[tuple[str, list[str], str]] = []   # `new ApiError(...)`: the classes built
    raw_passes: list[tuple[str, list[str], str]] = []       # `rows.map(formatDate)`: handed over
    returns_by_id: dict[str, str] = {}                  # node -> the class its `(): X` names
    members_by_id: dict[str, set[str]] = {}             # node -> the functions its returned object names
    typed_by_id: dict[str, tuple[str, str]] = {}        # node -> (its result's type, or the context it returns)

    for rel, res in js_files:
        if True:
            stem = os.path.splitext(os.path.basename(res["file"]))[0]
            for fn in res.get("functions", []):
                nid = ids.id(fn["name"], rel)
                # A function that returns JSX is a React component in both maps --
                # one meaning, one kind, whichever map you are reading.
                component = bool(fn.get("jsx"))
                _claim(methods, nid, _js_node(nid, fn["name"], None,
                                              "ui" if component else infer_layer(f'{fn["name"]} {stem}',
                                                                                 path=rel),
                                              "component" if component else "function", fn, rel))
                func_nodes.add(fn["name"])
                raw_calls.append((nid, fn.get("calls", []), rel))
                raw_renders.append((nid, fn.get("components", []), rel))
                raw_constructs.append((nid, fn.get("constructs", []), rel))
                raw_passes.append((nid, fn.get("passes", []), rel))
                if fn.get("returns"):
                    returns_by_id[nid] = fn["returns"]
                if fn.get("returns_members"):
                    members_by_id[nid] = set(fn["returns_members"])
                if fn.get("returns_type") or fn.get("returns_context"):
                    typed_by_id[nid] = (fn.get("returns_type", ""), fn.get("returns_context", ""))
            for cls in res.get("classes", []):
                # Nest hands us real decorator names (@Controller, @Injectable), which
                # is better evidence of a layer than the class name and file stem that
                # were all a JS class used to offer.
                layer = infer_layer(f'{cls["name"]} {stem}', cls.get("decorators", []), path=rel)
                class_methods.setdefault(cls["name"], set())
                for m in cls.get("methods", []):
                    nid = ids.id(f'{cls["name"]}.{m["name"]}', rel)
                    class_methods[cls["name"]].add(m["name"])
                    routed = bool(m.get("routes"))
                    _claim(methods, nid, _js_node(nid, m["name"], cls["name"],
                                                  "controller" if routed else layer,
                                                  "endpoint" if routed else "method", m, rel))
                    raw_calls.append((nid, m.get("calls", []), rel))
                    raw_constructs.append((nid, m.get("constructs", []), rel))
                    raw_passes.append((nid, m.get("passes", []), rel))
                    if m.get("returns"):
                        returns_by_id[nid] = m["returns"]
            for obj in res.get("objects", []):
                # `export const api = { approve: async () => ... }`: each inline member is
                # a method of `api`, so `api.approve()` from any importer has a node to reach.
                layer = infer_layer(f'{obj["name"]} {stem}', path=rel)
                for m in obj["members"]:
                    nid = ids.id(f'{obj["name"]}.{m["name"]}', rel)
                    _claim(methods, nid, _js_node(nid, m["name"], obj["name"], layer, "method", m, rel))
                    raw_calls.append((nid, m.get("calls", []), rel))
                    raw_constructs.append((nid, m.get("constructs", []), rel))
                    raw_passes.append((nid, m.get("passes", []), rel))
                    if m.get("returns"):
                        returns_by_id[nid] = m["returns"]

            _attach_routes(res.get("routes", []), methods, raw_calls,
                           lambda nid, data, rel=rel: _js_node(nid, nid, None, "controller",
                                                               "endpoint", data, rel),
                           rel, ids)

    # What each file's imports bind, followed to the file they name: `label()` imported
    # from `@/lib/labels` is that file's `label` even when another file defines one too
    # (name matching drops it), and `errors.toMessage()` through `import * as errors` is
    # the imported file's `toMessage` (its receiver has no type, so it was dropped).
    # Only a binding under the exported name itself: `import { label as tag }` would make
    # an edge to a name the caller never spells, which is what check_graph's c07 forbids.
    rel_of = {res["file"]: rel for rel, res in js_files}
    defaults = {rel: res.get("default", "") for rel, res in js_files}
    reexports = {rel: [(rel_of[e["path"]], e) for e in res.get("reexports", []) if e.get("path") in rel_of]
                 for rel, res in js_files}
    objects = {rel: {o["name"]: o["aliases"] for o in res.get("objects", [])} for rel, res in js_files}
    type_decls = {rel: res.get("types", {}) for rel, res in js_files}
    contexts = {rel: res.get("contexts", {}) for rel, res in js_files}
    # local name -> (file, the exported name it binds, or "*" for a namespace)
    bound: dict[str, dict[str, tuple[str, str]]] = {}
    # `import api from "./setdatService"` / `import { ngApi as api }`: the local name differs from
    # the exported one, so a bare `api()` would be an edge to a name never spelled -- but in
    # `api.fetchList()` the caller spells the member, which is all an edge to it needs.
    renamed: dict[str, dict[str, tuple[str, str]]] = {}
    for rel, res in js_files:
        for imp in res.get("imports", []):
            src_rel = rel_of.get(imp.get("path"))
            for local, imported in (imp.get("bindings") or []) if src_rel else ():
                name = defaults[src_rel] if imported == "default" else imported
                if name == local or imported == "*":
                    bound.setdefault(rel, {})[local] = (src_rel, "*" if imported == "*" else name)
                elif name:
                    renamed.setdefault(rel, {})[local] = (src_rel, name)

    def exported_node(rel: str, name: str, depth: int = 0) -> str | None:
        """The function file `rel` exports as `name`: its own, or the one a re-export
        (`export * from "./project"`, `export { name } from ...`) reaches -- only when
        exactly one file does, and never through a rename."""
        nid = ids.id(name, rel)
        node = methods.get(nid)
        if node and node["cls"] is None and node["source"].startswith(f"{rel}:"):
            return nid
        if depth >= 5:
            return None
        hits = {hit for src, e in reexports.get(rel, ())
                if e["names"].get(name) == name or e.get("star")
                for hit in [exported_node(src, name, depth + 1)] if hit}
        return hits.pop() if len(hits) == 1 else None

    def exported_member(rel: str, obj: str, member: str, depth: int = 0) -> str | None:
        """`obj.member` as file `rel` exports it: an object literal's inline member, a
        member naming the function of the same name, or a namespace re-export."""
        nid = ids.id(f"{obj}.{member}", rel)
        node = methods.get(nid)
        if node and node["cls"] == obj and node["source"].startswith(f"{rel}:"):
            return nid
        if objects.get(rel, {}).get(obj, {}).get(member) == member:
            return exported_node(rel, member)
        if depth >= 5:
            return None
        hits = set()
        for src, e in reexports.get(rel, ()):
            if e.get("namespace") == obj:
                hit = exported_node(src, member, depth + 1)
            elif e["names"].get(obj) == obj or e.get("star"):
                hit = exported_member(src, obj, member, depth + 1)
            else:
                continue
            if hit:
                hits.add(hit)
        return hits.pop() if len(hits) == 1 else None

    def through_import(rel: str, local: str, member: str | None = None) -> str | None:
        src_rel, name = bound.get(rel, {}).get(local, (None, None))
        if src_rel is None and member is not None:
            src_rel, name = renamed.get(rel, {}).get(local, (None, None))
        if src_rel is None:
            return None
        if name == "*":
            return exported_node(src_rel, member) if member is not None else None
        return exported_node(src_rel, name) if member is None else exported_member(src_rel, name, member)

    def declared_in(table: dict, rel: str, name: str, depth: int = 0) -> tuple:
        """(file, entry) for a type or context `name` as file `rel` sees it -- declared there, or
        where its import or a single re-export leads -- else (None, None)."""
        if name in table.get(rel, {}):
            return rel, table[rel][name]
        if depth >= 5:
            return None, None
        src_rel, bound_name = bound.get(rel, {}).get(name, (None, None))
        if src_rel and bound_name != "*":
            return declared_in(table, src_rel, bound_name, depth + 1)
        hits = {hit[0]: hit for src, e in reexports.get(rel, ())
                if e["names"].get(name) == name or e.get("star")
                for hit in [declared_in(table, src, name, depth + 1)] if hit[0]}
        return next(iter(hits.values())) if len(hits) == 1 else (None, None)

    def field_of(rel: str, ref: str, field: str, depth: int = 0) -> tuple:
        """(file, type) of `field` on type `ref` as file `rel` names it: `interface V { api: SetdatApi }`."""
        drel, entry = declared_in(type_decls, rel, ref)
        if not entry or depth >= 5:
            return None, None
        if "props" in entry:
            return (drel, entry["props"][field]) if field in entry["props"] else (None, None)
        return (None, None) if entry["is"].startswith("typeof ") else field_of(drel, entry["is"], field, depth + 1)

    def typed_member(rel: str, ref: str, name: str, depth: int = 0) -> str | None:
        """`name` on a value of type `ref` as file `rel` writes it: on `typeof setdatService` it is
        that object's or namespace's member; a type alias is followed; a class is its method."""
        if ref.startswith("typeof "):
            obj = ref[len("typeof "):]
            return (through_import(rel, obj, name)
                    or (exported_member(rel, obj, name) if obj in objects.get(rel, {}) else None))
        drel, entry = declared_in(type_decls, rel, ref)
        if entry and entry.get("is") and depth < 5:
            return typed_member(drel, entry["is"], name, depth + 1)
        if entry is None and name in class_methods.get(ref, ()):
            return resolve({"name": name, "type": ref}, rel)
        return None

    def resolve(call: dict, rel: str) -> str | None:
        name, declared = call["name"], call["type"]
        if call.get("via", {}).get("field"):
            # `const { api } = useSetdatVariant(); api.fetchX()`: the hook's return type -- or the
            # `createContext<T>` it returns -- then that type's `api` field, then `fetchX` on it.
            hop_id = resolve({"name": call["via"]["names"][0], "type": ""}, rel)
            ref, ctx = typed_by_id.get(hop_id, ("", ""))
            hop_rel = methods[hop_id]["source"].rpartition(":")[0] if hop_id in methods else None
            if hop_rel and ctx:
                hop_rel, ref = declared_in(contexts, hop_rel, ctx)
            frel, fref = field_of(hop_rel, ref, call["via"]["field"]) if hop_rel and ref else (None, None)
            return typed_member(frel, fref, name) if frel else None
        if call.get("via"):
            # `getApi().approve()`: each call's node, then the class its `(): X` names.
            declared = call["via"]["type"]
            hops = call["via"]["names"]
            for i, hop in enumerate(hops):
                if declared == "?":
                    break
                hop_id = resolve({"name": hop, "type": declared}, rel)
                if i == len(hops) - 1 and name in members_by_id.get(hop_id, ()):
                    # `const api = useSetdatApi(); api.fetchList()`: the function returns an object
                    # naming `fetchList`, so it is that function as the returning file sees it.
                    hop_rel = methods[hop_id]["source"].rpartition(":")[0]
                    return through_import(hop_rel, name) or exported_node(hop_rel, name)
                declared = returns_by_id.get(hop_id, "") or "?"
            if declared == "?":
                return None
        if declared == "?":                      # receiver present, type unreadable
            obj = call.get("obj", "")
            return (through_import(rel, obj, name)
                    or (exported_member(rel, obj, name) if obj in objects.get(rel, {}) else None))
        if declared:
            if name not in class_methods.get(declared, ()):
                return None
            nid = ids.target(f"{declared}.{name}", rel)
            if nid in methods:
                return nid
            # A class two files define: the file the caller imports the class -- or the
            # instance it calls through -- from, under its own name.
            for local in (declared, call.get("obj", "")):
                src_rel, bound_name = bound.get(rel, {}).get(local, (None, None))
                if src_rel and bound_name != "*":
                    nid = ids.id(f"{declared}.{name}", src_rel)
                    if nid in methods and methods[nid]["source"].startswith(f"{src_rel}:"):
                        return nid
            return None
        # A bare call is a module function -- never the enclosing class, which is what
        # `this.` is for, and unlike Java a bare name inside a JS class body does not
        # reach its own methods.
        return through_import(rel, name) or (ids.target(name, rel) if name in func_nodes else None)

    def passed_node(rel: str, name: str) -> str | None:
        """The function a passed name is: imported, or a module function of the passing file.
        Never a name any other file defines -- a local `row` is not someone else's `row()`."""
        return through_import(rel, name) or exported_node(rel, name)

    # Top-level code runs when its module loads (`const api = createApiInstance()`) and has
    # no node to draw an edge from, so what it calls looked dead. It is named instead.
    for rel, res in js_files:
        for call in res.get("module_calls", []):
            target = resolve(call, rel)
            if target in methods and not methods[target].get("entry"):
                methods[target]["entry"] = "module"
        # `export const api = createApiInstance(getUserApiBaseUrl)`: handed to a call as the
        # module loads -- used from outside any node, exactly as a module-load call is.
        for name in res.get("module_passes", []):
            target = passed_node(rel, name)
            if target in methods and not methods[target].get("entry"):
                methods[target]["entry"] = "module"

    edges: dict[tuple[str, str], dict] = {}       # (caller, callee) -> where it is written
    for owner, calls, rel in raw_calls:
        dropped: list[str] = []
        untyped: list[str] = []
        for call in calls:
            name = call["name"]
            target = resolve(call, rel)
            if target is None or target not in methods:
                dropped.append(name)        # library, or a name several files define
                if call["type"] == "?":
                    untyped.append(name)    # through a receiver whose type is not stated
            elif target != owner:
                call_ctx.merge(edges.setdefault((owner, target), {}), call)
        _record_dropped(methods[owner], dropped, untyped)

    # `new ApiError(...)` runs `ApiError`'s constructor: a call the source states as plainly
    # as `ApiError.create(...)`, so a class used only by `throw new ApiError()` is not dead.
    # It carries no site, and a link it shares with a call cannot then say every site is
    # inside a branch, or on one side of one.
    for owner, built, rel in raw_constructs:
        for cls_name in built:
            target = resolve({"name": "constructor", "type": cls_name}, rel)
            if target in methods and target != owner:
                site = edges.setdefault((owner, target), {})
                site.pop("cond", None)
                site.pop("arms", None)

    # `<Dashboard />` names a component exactly as `Dashboard()` would name a function,
    # so it resolves the same way -- imports first, then a name one file defines.
    renders: set[tuple[str, str]] = set()
    for owner, names, rel in raw_renders:
        for name in names:
            target = resolve({"name": name, "type": ""}, rel)
            if target in methods and target != owner:
                renders.add((owner, target))

    # `rows.map(formatDate)`, `onClick={run}`, `t.rich(key, { b: tag })`: the function is handed
    # to code that calls it -- a use, not a call from here. Its own link, `passes`.
    passes: set[tuple[str, str]] = set()
    for owner, names, rel in raw_passes:
        for name in names:
            target = passed_node(rel, name)
            if target in methods and target != owner and (owner, target) not in edges and (owner, target) not in renders:
                passes.add((owner, target))
    return methods, edges, renders, passes

def _lang_node(nid: str, name: str, cls, layer: str, kind: str, data: dict,
               rel: str, lang: str) -> dict:
    """A flow node from `langs_extract` (Java/Go/C# and the phase-7 languages). Same shape as `_js_node`.

    It used to carry `approx: True`, which was honest while these three were read
    textually and became arbitrary once every language moved to tree-sitter --
    Python and JS/TS resolve no more completely. The caveat is now stated once for
    every language (`taxonomy.PRECISION_CAVEAT`) and what survives per node is
    `precision`, a list of losses that can actually be named.
    """
    doc = (data.get("doc") or "").strip()
    calls = data.get("calls") or []
    content = json.dumps({"n": name, "c": sorted(f'{c["type"]}.{c["name"]}' for c in calls),
                          "d": doc}, sort_keys=True)
    params = data.get("params") or {}
    node = {
        "id": nid, "name": name, "cls": cls, "layer": layer, "kind": kind,
        "signature": f'{name}({", ".join(sorted(params))})',
        "doc": doc.splitlines()[0] if doc else "",
        "source": f'{rel}:{data.get("line", 0)}', "end": data.get("endLine", 0),
        "calls": [], "callers": [],
        "hash": _hash(content), "code": f"// {rel}\n{name}(...)", "lang": lang,
        "routes": _dedupe_routes(data.get("routes") or []),
    }
    if data.get("declaration"):
        # A signature with no body: it exists so calls through the declared type
        # resolve, but there is no code in it to measure, clone or call dead.
        node["declaration"] = True
    if data.get("entry"):
        node["entry"] = data["entry"]    # a framework calls it: never dead code
    return node

def _analyze_lang(lang_files: list, ids: "FlowIds"):
    """Nodes and call edges for every `langs_extract` language.

    Two passes for the same reason the Python analyzer needs two: a call can only
    be resolved once every class and its method names are known. `langs_extract`
    has already turned each receiver into a declared type; this decides whether
    that type is actually in the graph, and drops the call when it is not.
    """
    methods: dict[str, dict] = {}
    class_methods: dict[str, set[str]] = {}
    func_nodes: dict[str, str] = {}
    raw_calls: list[tuple[str, list[dict], str]] = []
    # "Class.name" / "name" -> its overloads: (provisional id, parameter kinds, file)
    overloads: dict[str, list[tuple[str, list[str], str]]] = {}
    # Declared return types, to type a call made on another call's result: every
    # definition of a name must agree, else the return type is unknown and the call drops.
    class_returns: dict[str, dict[str, set[str]]] = {}
    class_getters: dict[str, dict[str, str]] = {}        # Lombok: generated, typed by a field
    func_returns: dict[str, set[str]] = {}
    class_fields: dict[str, dict[str, str]] = {}         # `Registry.STORE.save()`: the field's type
    raw_inits: list[tuple[str | None, list[dict], str]] = []   # calls made outside any method
    classes: list[tuple[str, str, str, list[str]]] = []
    beans: list[dict] = []                               # Spring: the beans the source declares
    managed: set[str] = set()                            # classes Spring creates and injects into

    for rel, res in lang_files:
        if True:
            stem = os.path.splitext(os.path.basename(res["file"]))[0]
            lang = res["lang"]

            for cls in res.get("classes", []):
                layer = infer_layer(f'{cls["name"]} {stem}', cls.get("decorators", []),
                                    cls.get("bases", []), rel)
                class_methods.setdefault(cls["name"], set())
                class_getters.setdefault(cls["name"], {}).update(cls.get("getters") or {})
                class_fields.setdefault(cls["name"], {}).update(cls.get("fields") or {})
                classes.append(("lang", cls["name"], rel, cls.get("bases") or []))
                raw_inits.append((cls["name"], cls.get("init_calls") or [], rel))
                if cls.get("bean"):
                    managed.add(cls["name"])
                    beans.append({**cls["bean"], "cls": cls["name"], "rel": rel})
                members = cls.get("methods", [])
                for m, local in zip(members, _local_names(members)):
                    nid = ids.id(f'{cls["name"]}.{local}', rel)
                    class_methods[cls["name"]].add(m["name"])
                    if m.get("bean"):            # `@Bean Mailer mailer() { return new SmtpMailer(); }`
                        beans.append({**m["bean"], "cls": m["bean"]["builds"], "rel": None,
                                      "returns": m.get("returns", "")})
                    class_returns.setdefault(cls["name"], {}).setdefault(m["name"], set()).add(
                        m.get("returns", ""))
                    if local != m["name"]:
                        overloads.setdefault(f'{cls["name"]}.{m["name"]}', []).append(
                            (f'{cls["name"]}.{local}', m.get("kinds") or [], rel))
                    routed = bool(m.get("routes"))
                    node = _lang_node(nid, m["name"], cls["name"],
                                      "controller" if routed else layer,
                                      "endpoint" if routed else "method",
                                      m, rel, lang)
                    prev = methods.get(nid)
                    if prev is not None:
                        # Still one id for two definitions: overloads whose parameter
                        # types could not be read apart, or a language with no
                        # overloading at all (Rust's two `impl`s). Keep one node, and
                        # record every signature that folded into it.
                        node["signatures"] = ((prev.get("signatures") or [prev["signature"]])
                                              + [node["signature"]])
                    _claim(methods, nid, node)
                    raw_calls.append((nid, m.get("calls", []), rel))

            functions = res.get("functions", [])
            for fn, local in zip(functions, _local_names(functions)):
                nid = ids.id(local, rel)
                func_nodes[fn["name"]] = fn["name"]
                func_returns.setdefault(fn["name"], set()).add(fn.get("returns", ""))
                if local != fn["name"]:
                    overloads.setdefault(fn["name"], []).append((local, fn.get("kinds") or [], rel))
                _claim(methods, nid, _lang_node(nid, fn["name"], None,
                                                infer_layer(f'{fn["name"]} {stem}', path=rel),
                                                "function", fn, rel, lang))
                raw_calls.append((nid, fn.get("calls", []), rel))
            raw_inits.append((None, res.get("init_calls") or [], rel))

            _attach_routes(res.get("routes", []), methods, raw_calls,
                           lambda nid, data, rel=rel, lang=lang:
                               _lang_node(nid, nid, None, "controller", "endpoint",
                                          data, rel, lang),
                           rel, ids)

    def returns_of(cls_ctx: str | None, typ: str, name: str) -> str:
        """The one class `typ.name(...)` returns ("" = the enclosing class, then a module
        function), or "" when it is unknown or its definitions disagree."""
        if typ:
            found = class_returns.get(typ, {}).get(name) or (
                {class_getters[typ][name]} if name in class_getters.get(typ, {}) else set())
        elif cls_ctx and name in class_returns.get(cls_ctx, {}):
            found = class_returns[cls_ctx][name]
        else:
            found = func_returns.get(name, set())
        return next(iter(found)) if len(found) == 1 else ""

    # Spring: which bean each type is satisfied by -- a class Spring creates satisfies itself
    # and every base it names; a `@Bean` method's built class satisfies its return type too.
    locate = class_locator(lang_files)       # a class name two files define: which one a file means
    resolve_base, bases_of = _base_resolver(classes, locate)
    candidates: dict[str, list[dict]] = {}
    for bean in beans:
        rels = [r for name, r in bases_of if name == bean["cls"]]
        rel = bean["rel"] or (rels[0] if len(rels) == 1 else None)
        if rel is None:
            continue
        bean = {**bean, "rel": rel}
        seen, queue, types = {(bean["cls"], rel)}, [(bean["cls"], rel)], {bean["cls"], bean.get("returns", "")}
        while queue:
            cur = queue.pop(0)
            for base in bases_of.get(cur, ("lang", []))[1]:
                ancestor = resolve_base("lang", base, cur[1])
                if ancestor is not None and ancestor not in seen:
                    seen.add(ancestor)
                    queue.append(ancestor)
                    types.add(ancestor[0])
        for typ in sorted(types - {""}):
            candidates.setdefault(typ, []).append(bean)

    def injected(declared: str, target: str, call: dict, cls_ctx) -> str:
        """The method the injected bean runs, when the source settles which bean Spring
        injects into a class it manages: the one a `@Qualifier` names, the one `@Primary`
        bean, or the only bean -- never a conditional one alone. Otherwise `target`."""
        found = candidates.get(declared) if cls_ctx in managed else None
        if not found:
            return target
        if call.get("qualifier"):
            pick = [b for b in found if call["qualifier"] in b["names"]]
        else:
            primary = [b for b in found if b["primary"]]
            pick = primary if len(primary) == 1 else (
                [b for b in found if not b["conditional"]] if len(found) == 1 else [])
        if len(pick) != 1 or pick[0]["cls"] == declared:
            return target
        local = target.rpartition(f"{declared}.")[2]
        nid = ids.target(f'{pick[0]["cls"]}.{local}', pick[0]["rel"])
        return nid if nid in methods else target

    def defines(cls: str, name: str, crel: str) -> bool:
        """Does class `cls` in file `crel` define `name` (one method, or an overload set)?"""
        return (ids.id(f"{cls}.{name}", crel) in methods
                or any(r == crel for _, _, r in overloads.get(f"{cls}.{name}", ())))

    def ancestor_defining(cls: str, crel: str | None, name: str):
        """(class, file) of the nearest base of `cls` that defines `name`, or None: a helper
        a subclass calls with no receiver, `this.` or its own type -- `nz(...)` in an upload
        handler, defined once in the base class every handler extends."""
        if crel is None:
            return None
        seen, queue = {(cls, crel)}, [(cls, crel)]
        while queue:
            cur = queue.pop(0)
            for base in bases_of.get(cur, ("lang", []))[1]:
                anc = resolve_base("lang", base, cur[1])
                if anc is None or anc in seen:
                    continue
                if defines(anc[0], name, anc[1]):
                    return anc
                seen.add(anc)
                queue.append(anc)
        return None

    def node_id(provisional: str, trel: str, rel: str) -> str | None:
        """The node a provisional `Class.name` means in file `trel`, else the old rule: the
        caller's own file's definition of a shared name."""
        nid = ids.id(provisional, trel)
        if nid not in methods:
            nid = ids.target(provisional, rel)
        return nid if nid in methods else None

    def targets_of(call: dict, cls_ctx, rel: str):
        """(nodes the call reaches, the overload set it could not pick from, untyped receiver?)."""
        name, declared = call["name"], call["type"]
        via = call.get("via")
        if via:
            # `resolveHandler(t).downloadFile()`: walk the declared return types from the
            # innermost call outward, after any static field (`Registry.STORE.save()`);
            # any unknown step leaves the receiver "?".
            declared = via["type"]
            for field in via.get("fields", ()):
                declared = class_fields.get(declared, {}).get(field) or "?"
            for hop in via["names"]:
                if declared == "?":
                    break
                declared = returns_of(cls_ctx, declared, hop) or "?"
        if declared == "?":                      # receiver could not be typed
            return [], None, True
        # `trel`: the file of the class the call lands in. A class name two applications
        # both define is settled by the caller's package and imports, not by its own file.
        trel, inherited = rel, False
        if declared:
            crel = locate(declared, rel)
            if name in class_methods.get(declared, ()) and defines(declared, name, crel or rel):
                target, trel = f"{declared}.{name}", crel or rel
            else:
                found = ancestor_defining(declared, crel, name)
                target, trel, inherited = (f"{found[0]}.{name}", found[1], True) if found else (None, rel, False)
        elif cls_ctx and defines(cls_ctx, name, rel):
            target = f"{cls_ctx}.{name}"         # bare call: same class first,
        elif cls_ctx and (found := ancestor_defining(cls_ctx, rel, name)):
            target, trel, inherited = f"{found[0]}.{name}", found[1], True   # then what it inherits,
        else:
            target = func_nodes.get(name)        # then a module function

        def settle(nid: str) -> str:
            return nid if inherited else injected(declared, nid, call, cls_ctx)

        if target in overloads:
            # One call name, possibly several call sites: each argument list picks its
            # own overload, or is dropped as ambiguous.
            picks, missed = [], False
            for args in call.get("args") or [None]:
                picked = _pick_overload(overloads[target], args, trel) if args is not None else None
                picked = node_id(picked, trel, rel) if picked else None
                if picked is None:
                    missed = True
                else:
                    picks.append(settle(picked))
            return picks, (target if missed else None), False
        nid = node_id(target, trel, rel) if target else None
        return ([settle(nid)] if nid else []), None, False

    edges: dict[tuple[str, str], dict] = {}       # (caller, callee) -> where it is written
    for owner, calls, rel in raw_calls:
        dropped: list[str] = []
        untyped: list[str] = []
        ambiguous: set[str] = set()
        cls_ctx = methods[owner]["cls"]
        for call in calls:
            hits, unpicked, untyped_call = targets_of(call, cls_ctx, rel)
            if unpicked:
                ambiguous.add(unpicked)
            for t in hits:
                if t != owner:
                    call_ctx.merge(edges.setdefault((owner, t), {}), call)
            if not hits and not unpicked:
                dropped.append(call["name"])
                if untyped_call:
                    untyped.append(call["name"])
        _record_dropped(methods[owner], dropped, untyped)
        if ambiguous:
            methods[owner]["ambiguous"] = sorted(ambiguous)

    # A call made outside any method -- a field initializer, a static or init block, a
    # constructor, a Go package `var` -- has no node to draw a link from, so its callee
    # looked dead with no trace of why (finding #28). Named instead, as module-load code is.
    for cls_ctx, calls, rel in raw_inits:
        for call in calls:
            for target in targets_of(call, cls_ctx, rel)[0]:
                if not methods[target].get("entry"):
                    methods[target]["entry"] = "init"
    return methods, edges

def _record_dropped(node: dict, dropped: list[str], untyped=()) -> None:
    """Keep the names of the calls that did not become edges, not only how many.

    `ext` alone cannot tell two very different things apart: `print(...)` -- nothing
    in this graph is called that, so dropping it is right -- and a call to a name the
    graph *does* define, which is a missing edge. One is the boundary of the codebase,
    the other is the boundary of the resolver, and a reader could not see which was
    which. `_split_dropped` separates them once every node exists.
    """
    node["ext"] = len(dropped)
    node["_dropped"] = dropped
    node["_untyped"] = list(untyped)      # of those, the calls through a receiver of unknown type

def _split_dropped(methods: dict) -> None:
    """Turn each node's dropped names into `unresolved`: the ones this graph defines.

    Name-based on purpose, and an over-count on purpose: `save` here may well be a
    library's `save`. It answers "where might an edge be missing", which is the
    question `ext` silently refused to answer, and never invents an edge for it.
    `untyped` is the part of it dropped because the receiver's type was not stated --
    what earns `precision: name-matched` (finding #25).
    """
    known = {bare(nid) for nid in methods}
    for info in methods.values():
        names = info.pop("_dropped", [])
        hits = sorted({n for n in names if n in known})
        if hits:
            info["unresolved"] = hits
        untyped = sorted({n for n in info.pop("_untyped", []) if n in known})
        if untyped:
            info["untyped"] = untyped

def _auto_summary(info: dict) -> str:
    """Deterministic fallback used until an AI summary is available."""
    if info["calls"]:
        return "Delegates to " + ", ".join(f"[[{c}]]" for c in info["calls"]) + "."
    return "_No description available._"

def resolve_descriptions(methods: dict, cache: dict) -> dict:
    """Hybrid description resolution, cheapest source first:
      1. docstring (free, authoritative)
      2. cached AI summary whose hash still matches the current source (free)
      3. deterministic auto-summary  + flag the node as needing an AI summary
    Sets info['summary'] and info['desc_source'] in place; returns the pending map.
    """
    pending: dict[str, dict] = {}
    for node_id, info in methods.items():
        if info["doc"]:
            info["summary"], info["desc_source"] = info["doc"], "docstring"
        elif node_id in cache and cache[node_id].get("hash") == info["hash"]:
            info["summary"], info["desc_source"] = cache[node_id]["summary"], "ai"
            cache[node_id]["file"] = info["source"].split(":")[0]   # scopes future pruning
        else:
            info["summary"], info["desc_source"] = _auto_summary(info), "auto"
            pending[node_id] = {
                "hash": info["hash"], "signature": info["signature"],
                "source": info["source"], "code": info["code"],
            }
    return pending

def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)

def write_vault(methods: dict, flow_dir: str) -> None:
    os.makedirs(flow_dir, exist_ok=True)
    for fn in os.listdir(flow_dir):
        if fn.endswith(".md"):
            os.remove(long_path(os.path.join(flow_dir, fn)))

    for info in methods.values():
        calls_md = "\n".join(f"- [[{c}]]" for c in info["calls"]) or "_None._"
        callers_md = "\n".join(f"- [[{c}]]" for c in info["callers"]) or "_None (entry point)._"
        http = info.get("http") or []
        http_md = "".join(f"\n## HTTP calls\n" + "\n".join(f"- `{h['method']} {h['url']}`" for h in http) + "\n"
                          if http else "")
        prec = info.get("precision") or []
        prec_md = f"precision: {', '.join(prec)}\n" if prec else ""
        decl_md = "declaration: true\n" if info.get("declaration") else ""
        # An overload pair shares one id, so the note lists what folded into it --
        # otherwise the single signature shown looks like the only one there is.
        sigs = info.get("signatures") or []
        sig_md = "\n".join(f"`{s}`" for s in sigs) if sigs else f"`{info['signature']}`"
        page = (
            f"---\n"
            f"entity: {info['id']}\n"
            f"kind: {info['kind']}\n"
            f"layer: {info['layer']}\n"
            f"class: {info['cls'] or ''}\n"
            f"source: {info['source']}\n"
            f"lang: {info.get('lang', 'py')}\n"
            f"{prec_md}"
            f"{decl_md}"
            f"desc_source: {info.get('desc_source', 'auto')}\n"
            f"---\n"
            f"# {info['id']}\n\n"
            f"## What it does\n{info.get('summary', '')}\n\n"
            f"## Signature\n{sig_md}\n\n"
            f"## Calls\n{calls_md}\n\n"
            f"## Called by\n{callers_md}\n"
            f"{http_md}"
        )
        with open(long_path(os.path.join(flow_dir, f"{_safe(info['id'])}.md")), "w", encoding="utf-8") as fh:
            fh.write(page)

def write_graph(methods: dict, edges, graph_path: str) -> None:
    nodes = []
    for i in sorted(methods.values(), key=lambda x: x["id"]):
        node = {"id": i["id"], "layer": i["layer"], "kind": i["kind"],
                "cls": i["cls"], "signature": i["signature"], "doc": i.get("summary", ""),
                "source": i["source"], "end": i.get("end", 0),
                "lang": i.get("lang", "py"),
                "ext": i.get("ext", 0)}  # call sites that leave the graph (libs/stdlib)
        if i.get("unresolved"):
            # Of those `ext` sites, the names this graph defines somewhere: where an
            # edge may be missing because the receiver's class was not readable.
            node["unresolved"] = i["unresolved"]
        if i.get("untyped"):
            # Of those, the ones dropped because the receiver's type was not stated:
            # what earns `precision: name-matched`.
            node["untyped"] = i["untyped"]
        if i.get("http"):
            node["http"] = i["http"]
        if i.get("routes"):
            node["routes"] = i["routes"]
        if i.get("precision"):
            # Named precision losses. Absent means nothing *nameable* was lost --
            # never that the edges are complete, which PRECISION_CAVEAT says.
            node["precision"] = i["precision"]
        if i.get("declaration"):
            node["declaration"] = True   # signature only; no body to measure or run
        if i.get("entry"):
            node["entry"] = i["entry"]   # a framework (or module load) calls it: never dead code
        if i.get("overridden"):
            node["overridden"] = True    # every subclass replaces this body: it never runs
        if i.get("signatures"):
            node["signatures"] = i["signatures"]   # overloads folded into one id
        if i.get("ambiguous"):
            node["ambiguous"] = i["ambiguous"]     # overload sets a call here could not pick from
        nodes.append(node)
    # A call link says where it is written: `line`, and `loop` / `cond` where earned
    # (`call_ctx`). Only `calls` -- renders, passes, http and inheritance are not calls.
    graph = {"nodes": nodes,
             "edges": [{"source": s, "target": t, "type": ty,
                        **(call_ctx.facts(methods[s].get("call_sites", {}).get(t, {})) if ty == "calls" else {})}
                       for s, t, ty in edges]}
    os.makedirs(os.path.dirname(graph_path), exist_ok=True)
    with open(graph_path, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)
        fh.write("\n")

def build(src, flow_dir: str, graph_path: str) -> int:
    roots = [os.path.abspath(s) for s in ([src] if isinstance(src, str) else src)]
    missing = [r for r in roots if not os.path.isdir(r)]
    if missing:
        print(f"error: source root(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    print(f"Analyzing call flow in {', '.join(roots)} ...")
    methods, edges = analyze(roots)
    if not methods:
        print("No methods/functions found.")
        return 0

    # Hybrid descriptions: docstring -> cached AI summary -> auto fallback.
    cache = _load_json(DESCRIPTIONS_PATH, {})
    pending = resolve_descriptions(methods, cache)
    # Prune cache entries for nodes that no longer exist (handles deletes) -- but
    # only the ones this build could actually have seen. The cache belongs to the
    # skill install, not to a project, so a build of another codebase (or one that
    # skipped the frontend) must not throw away summaries for files it never read.
    if frontend_degraded():
        print("  ! description cache left intact: this build skipped the frontend")
    else:
        seen_files = {(m.get("source") or "").split(":")[0] for m in methods.values()}
        cache = {k: v for k, v in cache.items()
                 if k in methods or v.get("file") not in seen_files}
    _save_json(DESCRIPTIONS_PATH, cache)
    if pending:
        _save_json(PENDING_PATH, pending)
    elif os.path.exists(PENDING_PATH):
        os.remove(PENDING_PATH)

    write_vault(methods, flow_dir)
    write_graph(methods, edges, graph_path)

    endpoints = [m for m in methods.values() if m["kind"] == "endpoint"]
    from_doc = sum(1 for m in methods.values() if m["desc_source"] == "docstring")
    from_ai = sum(1 for m in methods.values() if m["desc_source"] == "ai")
    scope = " (BACKEND ONLY - frontend skipped)" if frontend_degraded() else ""
    print(f"Flow: {len(methods)} node(s), {len(edges)} edge(s), {len(endpoints)} endpoint(s){scope}")
    print(f"  descriptions: {from_doc} docstring, {from_ai} cached-AI, {len(pending)} pending")
    print(f"  graph -> {graph_path}")
    print(f"  notes -> {flow_dir}")
    if frontend_degraded():
        print("  WARNING: this graph is incomplete -- JS/TS files were not parsed, so frontend")
        print("           nodes and cross-stack edges are missing. Do not commit it as the")
        print("           project's map; install the parser and rebuild (see the warning above).")
    if pending:
        print(f"  NOTE: {len(pending)} method(s) need an AI summary. Read {PENDING_PATH},")
        print("        write a one-line summary for each, then run apply_descriptions.py and rebuild.")
    return 0

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a method-level call/request-flow graph.")
    parser.add_argument("--src", nargs="+", default=["./src"],
                        help="One or more source roots (e.g. --src ./backend ./frontend)")
    parser.add_argument("--flow-dir", default=DEFAULT_FLOW_DIR, help="Output directory for method notes")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Output flow_graph.json path")
    args = parser.parse_args(argv)
    return build(args.src, args.flow_dir, args.graph)


if __name__ == "__main__":
    raise SystemExit(main())
