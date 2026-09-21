#!/usr/bin/env python3
"""check_regressions.py -- one case per silent failure this project has had.

Every bug recorded in this repo's history had the same shape: the build exited 0
and the output was quietly wrong. Each one was found once, by accident or by a
diff, and nothing stopped it coming back. This is the list, as assertions.

    python tools/check_regressions.py

Run it after a build of `sample_src` (some cases read the committed artifacts,
and the freshness cases need the manifest that build writes). Each case names
the failure it guards, where it was found, and what it would look like if it
returned.

The first ten are the table in `docs/ROADMAP_PLAN.md`'s phase 4; the rest were
found after that table was written. One historical check cannot be re-run: the
JS/TS equivalence diff against `@babel/parser` died with it at step 4, and its
record is commit `fd9c7d8`.

Repo tool, not part of the installed skill.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(REPO, ".agents", "skills", "code-archaeologist")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import paths  # noqa: E402,F401
from paths import DATA_DIR  # noqa: E402

import analyze  # noqa: E402
import brief  # noqa: E402
import build_flow  # noqa: E402
import context  # noqa: E402
import duplicates  # noqa: E402
import grammars  # noqa: E402
import manifest  # noqa: E402
import py_extract as px  # noqa: E402
import taxonomy  # noqa: E402
import langs_extract  # noqa: E402
import trace_path  # noqa: E402

FIX = os.path.join(REPO, "tests", "fixtures", "langs")
SAMPLE = os.path.join(REPO, "sample_src")
FLOW = os.path.join(DATA_DIR, "flow", "flow_graph.json")


def _flow(root):
    methods, edges = build_flow.analyze([root])
    return methods, {(s, t) for s, t, kind in edges if kind == "calls"}


# --- the ten from the phase-4 table ---------------------------------------------

def r01_go_receiver():
    """phase 2: Go's receiver was handed to a helper expecting a declaration, so every
    Go method became a free function."""
    methods, _ = _flow(os.path.join(FIX, "go"))
    node = methods.get("WidgetService.Place")
    if not node or node.get("cls") != "WidgetService":
        return "WidgetService.Place is not a method of WidgetService"
    if "Place" in methods:
        return "a free function named Place exists -- the receiver was lost"


def r02_csharp_field_type():
    """phase 2: C# field types were read as type *and* name (`InvoiceStore _store`),
    so no call through a field resolved."""
    _, calls = _flow(os.path.join(FIX, "csharp"))
    if ("WidgetService.Place", "WidgetStore.Save") not in calls:
        return "the call through the declared field _store did not resolve"


def r03_go_map_type():
    """phase 2: `map[string]string` collapsed to a type named `mapstringstring`, and the
    identifier guard passed it because stripping brackets made it identifier-shaped."""
    for path in (os.path.join(FIX, "go", "widgets.go"),
                 os.path.join(SAMPLE, "services", "orders_go", "event_store.go")):
        src = open(path, encoding="utf-8").read()
        for cls in langs_extract.extract_file(path)["classes"]:
            for field, typ in (cls.get("fields") or {}).items():
                if typ and (not re.fullmatch(r"[A-Za-z_]\w*", typ) or typ not in src):
                    return f"{cls['name']}.{field} has type {typ!r}, which the source never spells"


def r04_missed_append():
    """phase 2: the extractor never saw the builtin `append(...)` call, so the node's
    count of calls leaving the graph was silently short."""
    methods, _ = _flow(os.path.join(SAMPLE, "services", "orders_go"))
    ext = methods.get("EventStore.Append", {}).get("ext")
    if ext != 1:
        return f"EventStore.Append has ext {ext}, expected 1 (its `append` call)"


def r05_duplicates_declarations():
    """phase 1: duplicates.py gave body-less declarations a token shape; only a token
    minimum stopped two signatures clustering."""
    decls = {n["id"] for n in json.load(open(FLOW, encoding="utf-8"))["nodes"] if n.get("declaration")}
    shaped = {b["node"]["id"] for b in duplicates.node_bodies([SAMPLE], FLOW)}
    if not decls:
        return "the sample has no declaration node to test with"
    if decls & shaped:
        return f"declarations were shaped: {sorted(decls & shaped)}"


def r06_orphan_guard():
    """phase 1: an uncalled declaration would be reported as dead code; the sample's only
    declaration has a caller, so nothing exercised the guard."""
    base = {"kind": "method", "layer": "service"}
    decl = analyze.find_orphans({"d": {"id": "d", **base, "declaration": True}}, [])
    plain = analyze.find_orphans({"p": {"id": "p", **base}}, [])
    if decl:
        return "an uncalled declaration was called dead code"
    if not plain:
        return "the guard is vacuous: an uncalled ordinary method was not an orphan either"


def r07_flask_routes():
    """spike: `@app.route` handlers sit inside `decorated_definition`, so every Flask
    route was missing from the tree-sitter read."""
    methods, _ = _flow(os.path.join(SAMPLE, "api_flask"))
    got = {(r["method"], r["path"]) for r in methods.get("orders", {}).get("routes", [])}
    if got != {("GET", "/legacy/orders"), ("POST", "/legacy/orders")}:
        return f"orders serves {sorted(got)}, expected GET and POST /legacy/orders"
    if not methods.get("order_detail", {}).get("routes"):
        return "order_detail lost its <int:order_id> route"


def r08_missing_parser_is_visible():
    """earlier: a missing parser shrank the graph from 15 to 11 nodes with no error. A
    change to the installed grammar set must surface as staleness."""
    src = manifest.DEFAULT_MANIFEST
    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    recorded = dict(data.get("grammars") or {})
    if not recorded:
        return "the manifest records no grammar set"
    recorded.pop(sorted(recorded)[0])
    data["grammars"] = recorded
    tmp = os.path.join(tempfile.mkdtemp(), "manifest.json")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    res = manifest.compare(None, path=tmp)
    if not res.get("stale") or "grammars changed" not in res.get("reason", ""):
        return f"a changed grammar set was not reported: {res.get('reason')!r}"


def r09_no_absolute_paths():
    """earlier: reports embedded absolute machine paths, so the same source produced
    different bytes on another checkout."""
    needles = {os.path.abspath(REPO), os.path.abspath(REPO).replace("\\", "/"), os.path.expanduser("~")}
    needles |= {n.replace("\\", "\\\\") for n in list(needles)}      # as it appears inside JSON
    for base, _dirs, files in os.walk(DATA_DIR):
        if os.sep + "cache" in base:
            continue
        for fn in files:
            if not fn.endswith((".json", ".md")):
                continue
            text = open(os.path.join(base, fn), encoding="utf-8", errors="replace").read().lower()
            for n in needles:
                if n.lower() in text:
                    return f"{os.path.relpath(os.path.join(base, fn), REPO)} contains the machine path {n!r}"


def r10_brief_agrees_with_check():
    """earlier: `brief` reported a confident false STALE -- the one command an agent is
    told to trust disagreed with `check`."""
    b = (brief.collect().get("freshness") or {}).get("stale")
    c = manifest.compare().get("stale")
    if b != c:
        return f"brief says stale={b}, check says stale={c}"


# --- found after the table was written -------------------------------------------

def r11_test_filename_with_line():
    """2g: flow nodes are keyed `path:line`, and the `:12` landed inside the filename,
    so no filename test convention matched -- only a tests/ directory did."""
    for p in ("api/user_test.go:12", "pkg/test_user.py:3", "src/UserTest.java:9", "web/user.test.ts:4"):
        if not taxonomy.is_test_path(p):
            return f"{p} is not recognised as test code"
    if taxonomy.is_test_path("api/user.go:12"):
        return "the check is vacuous: an ordinary file is called test code"


def r12_crlf_hashes():
    """step 5: tree-sitter reads bytes, so a CRLF checkout hashed every node differently
    and every cached AI summary silently missed."""
    d = tempfile.mkdtemp()
    a, b = os.path.join(d, "a.py"), os.path.join(d, "b.py")
    open(a, "wb").write(b"def f(x):\n    return x\n")
    open(b, "wb").write(b"def f(x):\r\n    return x\r\n")
    if px.read_source(a) != px.read_source(b):
        return "LF and CRLF copies of one file read differently"


def r13_wrapped_signature():
    """step 5: a parameter list wrapped across lines came back with newlines inside
    `signature`, which is rendered into vault pages and node labels."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "w.py")
    open(p, "w", encoding="utf-8").write("def f(a,\n      b,\n      c):\n    return a\n")
    root = px.parse(px.read_source(p)).root_node
    sig = px.signature(next(node for _decs, node in px.defs_in(root)))
    if "\n" in sig or sig != "f(a, b, c)":
        return f"signature is {sig!r}"


def r14_context_budget():
    """phase 3: the trim notice was appended after cutting to --max-chars, so every
    trimmed pack overran its "hard" budget by up to 26 chars."""
    for budget in (60, 200, 400):
        text = context.render(FLOW, ["OrderService.place_order"], 2, budget, False)
        if len(text) > budget:
            return f"--max-chars {budget} produced {len(text)} chars"


def r15_moved_root_reason():
    """phase 3: renaming a source root reported "source changed" when nothing had."""
    d = os.path.join(tempfile.mkdtemp(), "renamed_src")
    shutil.copytree(SAMPLE, d)
    res = manifest.compare([d])
    if not res.get("reason", "").startswith("source root moved"):
        return f"reason was {res.get('reason')!r}"


def r16_install_hint():
    """step 3: the hint for JS/TS was an empty command, and after that a command naming
    tree-sitter-typescript twice."""
    hint = grammars.install_hint(["javascript", "typescript", "tsx"])
    names = [re.split(r"[=<>]", tok.strip('"'))[0] for tok in hint.split()]
    for pkg in ("tree-sitter-javascript", "tree-sitter-typescript"):
        if names.count(pkg) != 1:
            return f"{pkg!r} appears {names.count(pkg)} time(s) in {hint!r}"


# --- found by phase 4's own checker ----------------------------------------------

def r17_owner_respects_end():
    """phase 4: a security or debt finding was pinned on "the last node starting at or
    before its line", ignoring where that node ends -- 99 of 152 on the skill's own code."""
    import scan_security
    d = tempfile.mkdtemp()
    g = os.path.join(d, "g.json")
    json.dump({"nodes": [{"id": "f", "source": "m/a.py:10", "end": 12},
                         {"id": "Entity", "source": "m/b.py"}], "edges": []}, open(g, "w"))
    idx = scan_security.node_index(g)
    if scan_security.owner_of(idx, "m/a.py", 11) != "f":
        return "a line inside f was not attributed to f"
    if scan_security.owner_of(idx, "m/a.py", 20) is not None:
        return "a line after f ends was still attributed to f"
    if scan_security.owner_of(idx, "m/b.py", 400) != "Entity":
        return "a node with no range (structure entity) no longer owns its file"


def r18_same_name_in_two_files():
    """phase 4 / finding #5: two definitions in different files sharing one flow id
    (every `main`, every `build`) became one node carrying every definition's calls."""
    import contextlib
    import io
    d = tempfile.mkdtemp()
    open(os.path.join(d, "one.py"), "w", encoding="utf-8").write(
        "def helper():\n    return 1\n\n\ndef main():\n    return helper()\n")
    open(os.path.join(d, "two.py"), "w", encoding="utf-8").write("def main():\n    return 2\n")
    with contextlib.redirect_stderr(io.StringIO()):
        methods, calls = _flow(d)
    if "main" in methods:
        return "a bare `main` node still exists -- the two definitions were merged"
    if not {"one.main", "two.main"} <= set(methods):
        return f"expected one.main and two.main, got {sorted(methods)}"
    if ("one.main", "helper") not in calls:
        return "one.main lost its own call to helper"
    if any(src == "two.main" for src, _ in calls):
        return "two.main carries a call it does not make"
    with contextlib.redirect_stderr(io.StringIO()):
        cs, _ = _flow(os.path.join(SAMPLE, "services", "orders_cs"))
    # Overloads in one file are separate nodes (finding #8), and never qualified by file:
    # two overloads are not two files sharing a name.
    if not {"InvoiceService.Total(InvoiceRequest)", "InvoiceService.Total(int,int)"} <= set(cs):
        return f"the sample's overload pair is not two unqualified nodes: {sorted(k for k in cs if 'Total' in k)}"


# --- resolved from the findings review ---------------------------------------------

def r19_reports_are_reproducible():
    """finding #3: every report artifact carried a wall-clock `generated`, so two builds
    of identical source differed in twelve files and constraint 2 was untrue for them."""
    import report
    first, second = tempfile.mkdtemp(), tempfile.mkdtemp()
    report.build([SAMPLE], FLOW, first)
    report.build([SAMPLE], FLOW, second)
    for name in sorted(os.listdir(first)):
        a = open(os.path.join(first, name), "rb").read()
        b = open(os.path.join(second, name), "rb").read()
        if a != b:
            return f"{name} differs between two reports of identical source"


def r20_structure_shared_names():
    """phase 5: a class name two files define kept the first entity and skipped the rest,
    so the structure map silently lacked the second class."""
    import contextlib
    import io
    import build_graph
    import build_wiki
    d = tempfile.mkdtemp()
    src = os.path.join(d, "src")
    os.makedirs(src)
    open(os.path.join(src, "a.py"), "w", encoding="utf-8").write(
        "class Store:\n    pass\n\n\nclass Service(Store):\n    pass\n")
    open(os.path.join(src, "b.py"), "w", encoding="utf-8").write(
        "class Store:\n    pass\n\n\nclass Other(Store):\n    pass\n")
    vault, out = os.path.join(d, "vault"), os.path.join(d, "out")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        build_wiki.build([src], vault)
        build_graph.build(vault, out)
    g = json.load(open(os.path.join(out, "graph.json"), encoding="utf-8"))
    ids = {n["id"] for n in g["nodes"]}
    edges = {(e["source"], e["target"]) for e in g["edges"]}
    if "Store" in ids:
        return "a bare Store survives -- one definition was dropped"
    if not {"a.Store", "b.Store"} <= ids:
        return f"expected a.Store and b.Store, got {sorted(ids)}"
    if ("Service", "a.Store") not in edges or ("Other", "b.Store") not in edges:
        return f"each subclass must link to its own file's Store; edges were {sorted(edges)}"


def r21_grammars_are_pinned():
    """phase 6c: every install took the latest wheel, from two lists (grammars.py and
    bin/cli.js) -- a grammar release renaming a node type would zero a language silently."""
    for pkg in set(grammars.PIP_NAMES.values()) | {"tree-sitter"}:
        if not grammars.PINS.get(pkg):
            return f"{pkg} has no pin"
    hint = grammars.install_hint(["go"])
    if f"tree-sitter-go{grammars.PINS['tree-sitter-go']}" not in hint:
        return f"the install hint does not carry the pin: {hint!r}"
    if not set(grammars.PINS) <= {a.split("=")[0].split(">")[0] for a in grammars.install_args()}:
        return "install_args() does not name every pinned package"
    cli = open(os.path.join(REPO, "bin", "cli.js"), encoding="utf-8").read()
    if re.search(r'"tree-sitter-[a-z-]+"', cli):
        return "bin/cli.js holds its own wheel list again"
    if grammars.drift():
        return f"the grammars installed here are not the pinned ones: {grammars.drift()}"


def r22_metrics_by_graph_id():
    """phase 6a: metrics were keyed by bare name, first wins, so a name two files define
    (qualified in the graph) was never measured -- and no non-Python node was at all."""
    import contextlib
    import io
    import metrics
    import scan_security
    d = tempfile.mkdtemp()
    open(os.path.join(d, "a.py"), "w", encoding="utf-8").write(
        "class Store:\n    def save(self, x):\n        if x:\n            return 1\n        return 0\n")
    open(os.path.join(d, "b.py"), "w", encoding="utf-8").write(
        "class Store:\n    def save(self, x):\n        return x\n")
    open(os.path.join(d, "c.go"), "w", encoding="utf-8").write(
        "package c\n\nfunc Pick(a, b int) int {\n\tif a > b {\n\t\treturn a\n\t}\n\treturn b\n}\n")
    with contextlib.redirect_stderr(io.StringIO()):
        methods, _ = build_flow.analyze([d])
    paths = {key: full for full, key in scan_security.iter_source_files([d])}
    got = metrics.node_metrics([dict(i, id=n) for n, i in methods.items()], paths)
    want = {"a.Store.save": 2, "b.Store.save": 1, "Pick": 2}
    for nid, cx in want.items():
        if nid not in got:
            return f"{nid} has no metrics; measured {sorted(got)}"
        if got[nid]["complexity"] != cx:
            return f"{nid} complexity {got[nid]['complexity']}, expected {cx}"
    if got["Pick"]["params"] != 2:
        return f"Go `a, b int` is two parameters, got {got['Pick']['params']}"


def r23_long_node_paths():
    """phase 6d: a node's page is named after its id, and a path-qualified id in a deep
    install passed Windows' MAX_PATH -- open() raised and the whole build died."""
    import contextlib
    import io
    import build_graph
    import build_wiki
    d = tempfile.mkdtemp()
    src = os.path.join(d, "src")
    os.makedirs(src)
    name = "Widget" + "X" * 100
    open(os.path.join(src, "a.py"), "w", encoding="utf-8").write(f"class {name}:\n    pass\n")
    vault = os.path.join(d, "v" * max(1, 200 - len(d)))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        build_wiki.build([src], vault)
        build_graph.build(vault, os.path.join(d, "out"))
    if len(os.path.join(vault, name + ".md")) <= 260:
        return "the case no longer exercises a path past MAX_PATH"
    ids = {n["id"] for n in json.load(open(os.path.join(d, "out", "graph.json"), encoding="utf-8"))["nodes"]}
    if name not in ids:
        return f"the long-named entity is missing from the graph: {sorted(ids)}"


def r24_route_table_handlers():
    """phase 8: a route declared in a table (Django urlpatterns, routes.rb, ...) reached no
    node at all; now it must reach exactly one -- and never guess between two."""
    import contextlib
    import io
    d = tempfile.mkdtemp()
    for name in ("a", "b"):                       # OrdersController.index, defined twice
        os.makedirs(os.path.join(d, name))
        open(os.path.join(d, name, "orders_controller.rb"), "w", encoding="utf-8").write(
            "class OrdersController\n  def index\n    1\n  end\nend\n")
    os.makedirs(os.path.join(d, "config"))
    open(os.path.join(d, "config", "routes.rb"), "w", encoding="utf-8").write(
        'Rails.application.routes.draw do\n  get "/orders", to: "orders#index"\nend\n')
    os.makedirs(os.path.join(d, "shop"))
    open(os.path.join(d, "shop", "urls.py"), "w", encoding="utf-8").write(
        "from django.urls import path\nfrom . import views\n\n"
        "urlpatterns = [path('api/items/', views.item_list)]\n")
    open(os.path.join(d, "shop", "views.py"), "w", encoding="utf-8").write(
        "def item_list(request):\n    return []\n")
    open(os.path.join(d, "client.js"), "w", encoding="utf-8").write(
        "export function loadItems() {\n  return fetch('/api/items/');\n}\n")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        methods, edges = build_flow.analyze([d])
    attached = [n for n, i in methods.items() if "OrdersController" in n and i.get("routes")]
    if attached:
        return f"a route to a handler two files define was attached to {attached} -- a guess"
    if "route-table route(s) name no single handler" not in err.getvalue():
        return "the ambiguous table route was dropped silently"
    if not (methods.get("item_list") or {}).get("routes"):
        return "the Django table route did not reach its view"
    if ("loadItems", "item_list", "http") not in set(edges):
        return "a frontend fetch did not link to a handler routed only by a table"


def r25_copied_blocks():
    """phase 9: clones were matched whole-body only, so a block pasted into two otherwise
    different functions was invisible -- and a block finder must not re-report clusters."""
    import contextlib
    import io
    d = tempfile.mkdtemp()
    open(os.path.join(d, "ledger.py"), "w", encoding="utf-8").write(
        "def load_sales(rows):\n"
        "    header = rows[0]\n"
        "    total = 0\n"
        "    for row in rows[1:]:\n"
        "        if row.amount > 0 and row.kind == 'sale':\n"
        "            total = total + row.amount * row.rate\n"
        "            audit(row.name, total, 'sale')\n"
        "    return header, total\n\n\n"
        "def load_refunds(entries, limit):\n"
        "    count = len(entries)\n"
        "    running = 0\n"
        "    for entry in entries[1:]:\n"
        "        if entry.amount > 0 and entry.kind == 'sale':\n"
        "            running = running + entry.amount * entry.rate\n"
        "            audit(entry.name, running, 'sale')\n"
        "    print(count, limit)\n"
        "    return running\n\n\n"
        "def load_other(items, scale, flag):\n"          # the same block, one operator flipped
        "    acc = 0\n"
        "    for item in items[1:]:\n"
        "        if item.amount > 0 and item.kind == 'sale':\n"
        "            acc = acc - item.amount * item.rate\n"
        "            audit(item.name, acc, 'sale')\n"
        "    raise ValueError(flag)\n\n\n"
        "def load_more(batch, a, b, c):\n"               # a third copy of the same block
        "    seen = set()\n"
        "    subtotal = 0\n"
        "    for rec in batch[1:]:\n"
        "        if rec.amount > 0 and rec.kind == 'sale':\n"
        "            subtotal = subtotal + rec.amount * rec.rate\n"
        "            audit(rec.name, subtotal, 'sale')\n"
        "    yield seen\n")
    graph = os.path.join(d, "flow.json")
    with contextlib.redirect_stderr(io.StringIO()):
        methods, edges = build_flow.analyze([d])
    build_flow.write_graph(methods, edges, graph)
    blocks = duplicates.build([d], graph)["blocks"]
    by_ids = {tuple(sorted({p["id"] for p in b["places"]})): b for b in blocks}
    hit = by_ids.get(("load_more", "load_refunds", "load_sales"))
    if hit is None:
        return f"one block in three functions is not one entry with three places: {sorted(by_ids)}"
    if len(blocks) != 1:
        return f"finding #7: one block pasted three times became {len(blocks)} entries"
    if {p["id"]: p["lines"] for p in hit["places"]} != \
            {"load_sales": [3, 7], "load_refunds": [13, 17], "load_more": [33, 37]}:
        return f"the block is not the five copied lines: {[(p['id'], p['lines']) for p in hit['places']]}"
    sample = duplicates.build([SAMPLE], FLOW)
    clustered = {tuple(sorted(n["id"] for n in c["nodes"])) for c in sample["clusters"]}
    if ("createInvoice", "createOrder") not in clustered:
        return "the sample's planted whole-body clone is no longer a cluster"
    if any(tuple(sorted({p["id"] for p in b["places"]})) in clustered for b in sample["blocks"]):
        return "a pair already in a cluster was reported again as a block"


def r26_graph_path_on_another_drive():
    """phase 9: five passes recorded their graph with a hand-rolled
    relpath(graph, SKILL_ROOT), which raises when the graph is on another drive."""
    import paths
    other = "Z:\\elsewhere\\g.json" if os.name == "nt" else "/elsewhere/g.json"
    try:
        label = paths.skill_rel(other)
    except ValueError as exc:
        return f"skill_rel raised for a path on another drive: {exc}"
    if not label.endswith("elsewhere/g.json"):
        return f"skill_rel lost the path: {label!r}"
    scripts = os.path.join(SKILL, "scripts")
    for base, _dirs, files in os.walk(scripts):
        for fn in files:
            full = os.path.join(base, fn)
            if fn.endswith(".py") and fn != "paths.py" and \
                    "relpath(graph_path, SKILL_ROOT)" in open(full, encoding="utf-8").read():
                return f"{fn} hand-rolls relpath(graph_path, SKILL_ROOT) again; use paths.skill_rel"


def r27_generated_dirs_are_not_source():
    """phase 9: five copies of "which directories are not source" had drifted, and none
    skipped `.next/` -- a Next.js dev server's generated TypeScript became 9% of a real
    repository's flow graph, and the graph changed every time it recompiled."""
    import contextlib
    import io
    import build_graph
    import build_wiki
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".next", "types"))
    open(os.path.join(d, ".next", "types", "routes.ts"),
         "w", encoding="utf-8").write("export function generatedRoute() {\n  return 1;\n}\n")
    open(os.path.join(d, "app.ts"), "w", encoding="utf-8").write(
        "export function handWritten() {\n  return 2;\n}\n")
    vault, out = os.path.join(d, "vault"), os.path.join(d, "out")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, _ = build_flow.analyze([d])
        build_wiki.build([d], vault)
        build_graph.build(vault, out)
    if "generatedRoute" in methods or "handWritten" not in methods:
        return f"flow map: expected handWritten only, got {sorted(methods)}"
    if any(".next" in (n.get("source") or "")
           for n in json.load(open(os.path.join(out, "graph.json"), encoding="utf-8"))["nodes"]):
        return "structure map: a node came from .next/"
    if any(".next" in k for k in manifest.snapshot([d])):
        return "the freshness manifest hashes .next/, so a dev server makes every build stale"
    scripts = os.path.join(SKILL, "scripts")
    for base, _dirs, files in os.walk(scripts):
        for fn in files:
            if fn.endswith(".py") and fn != "taxonomy.py" and \
                    re.search(r"^SKIP_DIRS\s*=", open(os.path.join(base, fn), encoding="utf-8").read(), re.M):
                return f"{fn} defines its own SKIP_DIRS again; import taxonomy.SKIP_DIRS"


def _tree(files: dict) -> str:
    """A temp source tree from {relative path: text}."""
    d = tempfile.mkdtemp()
    for rel, text in files.items():
        full = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
    return d


def r28_mock_patch_is_not_a_route():
    """real repo: `@patch("subprocess.run")` (unittest.mock) on a Python test was read as
    a PATCH route -- `patch` is also an HTTP verb, and nothing required a "/"."""
    d = _tree({
        "test_tools.py": 'from unittest.mock import patch\n\n\nclass TestTool:\n'
                         '    @patch("subprocess.run")\n    def test_runs(self, run):\n'
                         '        assert run\n',
        "api.py": 'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n'
                  '@router.patch("/items/{item_id}")\ndef update_item(item_id):\n'
                  '    return item_id\n'})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, _ = _flow(d)
    routed = {nid: [(r["method"], r["path"]) for r in info["routes"]]
              for nid, info in methods.items() if info.get("routes")}
    if routed != {"update_item": [("PATCH", "/items/{item_id}")]}:
        return f"expected only update_item's PATCH route, got {routed}"


def r29_names_differing_only_by_case():
    """real repo: `login` (a service) and `Login` (a page) kept bare ids, so their notes
    were one file on Windows and macOS and one silently overwrote the other."""
    d = _tree({
        "src/services/authService.ts": "export function login() {\n  return 1;\n}\n",
        "src/app/Login.tsx": 'import { login } from "../services/authService";\n\n'
                             "export function Login() {\n  login();\n  return <div />;\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = _flow(d)
    ids_ = sorted(methods)
    if len({i.lower() for i in ids_}) != len(ids_):
        return f"two ids differ only by case: {ids_}"
    lower = {i.split(".")[-1]: i for i in ids_}
    if (lower.get("Login"), lower.get("login")) not in edges:
        return f"the call Login -> login was lost once the ids were qualified: {sorted(edges)}"


def r30_imported_axios_instance():
    """real repo: an axios instance is created once and imported everywhere, but only a
    same-file `axios.create` counted -- a Next.js frontend had 0 HTTP calls and no
    cross-stack edge."""
    d = _tree({
        "web/src/services/http.ts": 'import axios from "axios";\n\n'
                                    'const http = axios.create({ baseURL: "/api" });\n'
                                    "export const admin = axios.create();\nexport default http;\n\n"
                                    # a factory: the instance is made inside a function
                                    "const make = () => {\n  const i = axios.create();\n"
                                    "  i.interceptors.request.use((c) => {\n    return c;\n  });\n"
                                    "  return i;\n};\nexport const made = make();\n",
        "web/src/services/orders.ts": 'import http, { admin as a, made } from "@/services/http";\n\n'
                                      # awaited + generic: the await parses *inside* the callee
                                      'export async function loadOrders() {\n'
                                      '  const { data } = await http.get<string[]>("/orders");\n'
                                      '  return data;\n}\n\n'
                                      "export async function dropOrder(id: string) {\n"
                                      "  return a.delete(`/orders/${id}`);\n}\n\n"
                                      "export async function renameOrder(id: string) {\n"
                                      "  return made.put(`/orders/${id}`);\n}\n",
        "api/orders.controller.ts": 'import { Controller, Delete, Get, Put } from "@nestjs/common";\n\n'
                                    '@Controller("orders")\nexport class OrdersController {\n'
                                    "  @Get()\n  list() {\n    return [];\n  }\n\n"
                                    '  @Delete(":id")\n  remove() {\n    return 1;\n  }\n\n'
                                    '  @Put(":id")\n  update() {\n    return 2;\n  }\n}\n'})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    http = {(s, t) for s, t, kind in edges if kind == "http"}
    want = {("loadOrders", "OrdersController.list"), ("dropOrder", "OrdersController.remove"),
            ("renameOrder", "OrdersController.update")}
    if http != want:
        return f"expected {sorted(want)}, got {sorted(http)}"


def r31_unknown_url_links_nowhere():
    """real repo: a call whose URL is a variable (`get(ENDPOINT[section])`) normalized to
    `/` and was linked to the app's `GET /` handler -- a wrong edge, not a missing one."""
    d = _tree({
        "web/api.ts": 'import axios from "axios";\n\nconst ENDPOINT = { blog: "/blog" };\n\n'
                      "export async function getPosts(section) {\n"
                      "  return axios.get(ENDPOINT[section]);\n}\n\n"
                      "export async function getOne(id) {\n  return axios.get(`${id}`);\n}\n",
        "api/app.controller.ts": 'import { Controller, Get } from "@nestjs/common";\n\n'
                                 "@Controller()\nexport class AppController {\n"
                                 '  @Get()\n  getHello() {\n    return "hi";\n  }\n\n'
                                 '  @Get(":id")\n  getById() {\n    return 1;\n  }\n}\n'})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    http = sorted((s, t) for s, t, kind in edges if kind == "http")
    if http:
        return f"a URL with no literal segment was linked: {http}"


def r32_const_base_and_client_prefix():
    """real repo: services wrote `${API_BASE_URL}/list` with a same-file string const base,
    through an axios baseURL ending in `/api` -- 89 calls read as `:API_BASE_URL/list`, and
    even resolved, `/orders/list` never met the route `/api/orders/list`."""
    d = _tree({
        "web/orders.ts": 'import axios from "axios";\n\nconst API_BASE_URL = "/orders";\n\n'
                         "export async function listOrders() {\n"
                         "  return axios.get(`${API_BASE_URL}/list`);\n}\n\n"
                         "export async function login(base) {\n"
                         "  return axios.post(`${base}/login`);\n}\n",
        "api/OrderController.java": "package demo;\n\n"
                                    '@RestController\n@RequestMapping("/api/orders")\n'
                                    "public class OrderController {\n"
                                    '    @GetMapping("/list")\n    public String list() {\n'
                                    '        return "";\n    }\n\n'
                                    '    @PostMapping("/auth/login")\n    public String login() {\n'
                                    '        return "";\n    }\n}\n'})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    http = {(s, t) for s, t, kind in edges if kind == "http"}
    if http != {("listOrders", "OrderController.list")}:
        return (f"expected only listOrders -> OrderController.list (an unknown base must not "
                f"link), got {sorted(http)}")


def r33_overloads_are_separate_nodes():
    """finding #8: an overload set was ONE node -- every overload's calls, one overload's
    range. Each overload is now its own node, and each call site picks its overload by
    argument count and stated argument types, or is dropped and marked `overloads`."""
    d = _tree({
        "Printer.java": "package demo;\n\npublic class Printer {\n"
                        "    public void run(Report report) {\n        render(report);\n"
                        "        render(report, 2);\n        render(report, \"wide\");\n"
                        "        render(report, pick());\n    }\n\n"
                        "    void render(Report report) {\n        report.close();\n    }\n\n"
                        "    int pick() {\n        return 1;\n    }\n\n"
                        "    void render(Report report, int width) {\n        pick();\n    }\n\n"
                        "    void render(Report report, String style) {\n        pick();\n    }\n}\n",
        "NPrinter.cs": "public class NPrinter\n{\n    public void Run(int w)\n    {\n"
                       "        Render(w);\n        Render(w, \"x\");\n    }\n\n"
                       "    public void Render(int w)\n    {\n    }\n\n"
                       "    public void Render(int w, string s)\n    {\n    }\n}\n",
        "KPrinter.kt": "class KPrinter {\n    fun run(w: Int) {\n        render(w)\n"
                       "        render(w, \"x\")\n    }\n\n    fun render(w: Int) {\n    }\n\n"
                       "    fun render(w: Int, s: String) {\n    }\n}\n",
        "SPrinter.scala": "class SPrinter {\n  def run(w: Int): Unit = {\n    render(w)\n"
                          "    render(w, \"x\")\n  }\n\n  def render(w: Int): Unit = {\n  }\n\n"
                          "  def render(w: Int, s: String): Unit = {\n  }\n}\n",
        "WPrinter.swift": "class WPrinter {\n    func run(w: Int) {\n        render(w: w)\n"
                          "        render(w: w, s: \"x\")\n    }\n\n    func render(w: Int) {\n    }\n\n"
                          "    func render(w: Int, s: String) {\n    }\n}\n",
        "CPrinter.cpp": "class CPrinter {\npublic:\n    void run(int w) {\n        render(w);\n"
                        "        render(w, 1.5);\n    }\n\n    void render(int w) {\n    }\n\n"
                        "    void render(int w, double s) {\n    }\n};\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = _flow(d)
    want = {("Printer.run", "Printer.render(Report)"), ("Printer.run", "Printer.render(Report,int)"),
            ("Printer.run", "Printer.render(Report,String)"),
            ("Printer.render(Report,int)", "Printer.pick"),
            ("Printer.render(Report,String)", "Printer.pick"),
            ("NPrinter.Run", "NPrinter.Render(int)"), ("NPrinter.Run", "NPrinter.Render(int,string)"),
            ("KPrinter.run", "KPrinter.render(Int)"), ("KPrinter.run", "KPrinter.render(Int,String)"),
            ("SPrinter.run", "SPrinter.render(Int)"), ("SPrinter.run", "SPrinter.render(Int,String)"),
            ("WPrinter.run", "WPrinter.render(Int)"), ("WPrinter.run", "WPrinter.render(Int,String)"),
            ("CPrinter.run", "CPrinter.render(int)"), ("CPrinter.run", "CPrinter.render(int,double)")}
    if want - edges:
        return f"missing edges {sorted(want - edges)}; got {sorted(e for e in edges if 'rinter' in e[0])}"
    if ("Printer.render(Report)", "Printer.pick") in edges:
        return "an overload carries another overload's call again"
    run = methods.get("Printer.run", {})
    if run.get("ambiguous") != ["Printer.render"] or run.get("precision") != ["overloads"]:
        return (f"render(report, pick()) must be dropped as ambiguous and marked: "
                f"ambiguous={run.get('ambiguous')} precision={run.get('precision')}")
    folded = sorted(k for k, m in methods.items() if m.get("signatures"))
    if folded:
        return f"overloads still folded into one node: {folded}"
    lines = {methods[k]["source"] for k in methods if k.startswith("Printer.render(")}
    if len(lines) != 3:
        return f"the three render overloads do not have three ranges: {sorted(lines)}"


def r34_js_method_calls_resolve():
    """A JS/TS call through a receiver whose class the source states was dropped: the
    receiver was discarded at extraction and class methods were never candidates, so no
    edge could land on one -- the TypeScript fixture resolved 0 of 3. An untyped
    receiver must still drop, which is the half of the behaviour worth keeping."""
    d = _tree({
        "store.ts": "export class Store {\n  save(item: object) {\n    return item;\n  }\n}\n",
        "service.ts": "import { Store } from \"./store\";\n\n"
                      "export class Service {\n"
                      "  private store: Store = new Store();\n\n"
                      "  place(item: object) {\n    return this.store.save(item);\n  }\n\n"
                      "  twice(item: object) {\n    this.place(item);\n"
                      "    return new Store().save(item);\n  }\n\n"
                      "  blind(other: any) {\n    return other.save(item);\n  }\n}\n",
        "page.js": "const { Service } = require(\"./service\");\n\n"
                   "function run(item) {\n  const svc = new Service();\n"
                   "  return svc.place(item);\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = _flow(d)
    want = {("Service.place", "Store.save"),        # this.<typed field>.m()
            ("Service.twice", "Service.place"),     # this.m()
            ("Service.twice", "Store.save"),        # new Store().m()
            ("run", "Service.place")}               # local assigned a `new Service()`
    if want - edges:
        return f"missing edges {sorted(want - edges)}; got {sorted(edges)}"
    if any(s == "Service.blind" for s, _ in edges):
        return "a call through an untyped receiver (`other.save()`) was guessed at"
    if methods.get("Service.blind", {}).get("ext") != 1:
        return f"the dropped call is not counted: ext={methods.get('Service.blind', {}).get('ext')}"


def r35_dropped_calls_are_named():
    """`ext` counted dropped calls and threw their names away, so "called `dumps()`" --
    nothing in the graph is named that, correctly dropped -- looked exactly like "called
    something this graph defines and could not place", which is a missing edge. The names
    of the second kind are kept in `unresolved`."""
    d = _tree({
        "shop.py": "import json\n\n\nclass Store:\n    def save(self, x):\n        return x\n\n\n"
                   "class Service:\n    def place(self, store, x):\n"
                   "        json.dumps(x)\n        return store.save(x)\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = _flow(d)
    place = methods.get("Service.place", {})
    if place.get("ext") != 2:
        return f"both dropped call sites must still be counted: ext={place.get('ext')}"
    if place.get("unresolved") != ["save"]:
        return ("unresolved must name `save` (the graph defines it) and not `dumps` (it does"
                f" not): {place.get('unresolved')}")
    if ("Service.place", "Store.save") in edges:
        return "an edge was invented for the unresolved call"
    if "_dropped" in place:
        return "the working list leaked into the node"


def r36_render_failure_keeps_the_maps():
    """real install: npm dropped templates/vendor/force-graph.min.js, the render after the
    structure map raised, and `both` ended before the flow map was built. A missing graph
    library must cost the explorer page only -- named, non-zero -- never a map."""
    import archaeologist
    import build_html
    d = _tree({"src/shop.py": "class Store:\n    def save(self, x):\n        return x\n"})
    out = tempfile.mkdtemp()
    saved = (build_html.VENDOR_JS_PATH, archaeologist.STRUCTURE_DIR, archaeologist.FLOW_DIR,
             archaeologist.REPORT_DIR, archaeologist.EXPLORER_HTML, dict(archaeologist.GRAPHS),
             archaeologist.manifest.write)
    wrote = []
    try:
        build_html.VENDOR_JS_PATH = os.path.join(out, "missing", "force-graph.min.js")
        archaeologist.STRUCTURE_DIR = os.path.join(out, "structure")
        archaeologist.FLOW_DIR = os.path.join(out, "flow")
        archaeologist.REPORT_DIR = os.path.join(out, "report")
        archaeologist.EXPLORER_HTML = os.path.join(out, "explorer.html")
        archaeologist.GRAPHS.update(structure=os.path.join(out, "structure", "graph.json"),
                                    flow=os.path.join(out, "flow", "flow_graph.json"))
        archaeologist.manifest.write = lambda src: wrote.append(src)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = archaeologist.main(["both", "--src", os.path.join(d, "src")])
    finally:
        (build_html.VENDOR_JS_PATH, archaeologist.STRUCTURE_DIR, archaeologist.FLOW_DIR,
         archaeologist.REPORT_DIR, archaeologist.EXPLORER_HTML, graphs,
         archaeologist.manifest.write) = saved
        archaeologist.GRAPHS.clear()
        archaeologist.GRAPHS.update(graphs)
    if not os.path.isfile(os.path.join(out, "flow", "flow_graph.json")):
        return "the flow map was not built after the explorer failed to render"
    if not wrote:
        return "the manifest was not written, so `check` would call fresh maps stale"
    if not rc:
        return "a missing explorer exited 0 -- the failure is silent"
    if "force-graph.min.js" not in buf.getvalue():
        return "the output does not name the missing file"
    if os.path.exists(os.path.join(out, "explorer.html")):
        return "an explorer was written without its graph library"


def r37_secret_names_are_not_secrets():
    """real repo: all ten "hardcoded secrets" on a Spring + Next.js repository named a
    credential rather than holding one -- a storage key, a route, prose -- and at 10 points
    each they decided the grade. A secret actually held in the source must still be found."""
    import scan_security
    lines = ['const API_KEY = "sk_live_9f8a7b6c5d";',
             "const password = 'hunter22!x';",
             'const KEYS = { ACCESS_TOKEN: "accessToken" };',
             'const ROUTES = { RESET_PASSWORD: "/reset-password" };',
             'export const REFRESH_TOKEN_COOKIE_PATH = "/api/auth/refresh";',
             'const tokenNote = "Spacing tokens scale in 4px steps";',
             # the retest's two survivors: a design token's CSS class, an event name
             'const spacing = { token: "space-y-4" };',
             'export const EVENTS = { TOKEN_REFRESHED: "auth:token-refreshed" };',
             # a UUID is kebab-shaped but its segments mix letters and digits: still a secret
             'const API_KEY_PROD = "550e8400-e29b-41d4-a716-446655440000";']
    d = _tree({"src/constants.ts": "\n".join(lines) + "\n"})
    with contextlib.redirect_stdout(io.StringIO()):
        found = scan_security.scan([os.path.join(d, "src")], os.path.join(d, "no_graph.json"))
    hits = sorted(f["line"] for f in found["findings"] if f["rule"] == "hardcoded_secret")
    if hits != [1, 2, 9]:
        return f"expected the three held secrets (lines 1, 2, 9) and nothing else, got lines {hits}"


def r38_layer_from_annotation():
    """real repo: `handler` was a controller word and names outranked annotations, so 24
    `MaintenanceService -> MasterDataUploadHandler` calls were layer violations and
    Spring's `@Component` matched the `ui` rule."""
    got = taxonomy.infer_layer("MasterDataUploadHandler", ["Component"])
    if got in ("controller", "ui"):
        return f"@Component MasterDataUploadHandler inferred as {got}"
    if taxonomy.infer_layer("OrderHandler", ["Service"]) != "service":
        return "@Service did not outrank the class name"
    if taxonomy.infer_layer("GlobalExceptionHandler", ["RestControllerAdvice"]) != "controller":
        return "@RestControllerAdvice is not a controller"
    if taxonomy.infer_layer("createOrderHandler order_router") != "controller":
        return "a handler in a router file lost its controller layer"


def r39_type_name_receivers():
    """real repo: `GlobalResponse.success()` / `DateUtil.now()` had no callers -- Java and
    JS/TS sent a receiver that is a class name to "?", so every static call was dropped.
    A class the graph does not have (`Math`) must still drop."""
    d = _tree({
        "java/DateUtil.java": "public class DateUtil {\n    public static String now() {\n"
                              '        return "x";\n    }\n}\n',
        "java/Clock.java": "public class Clock {\n    public String stamp() {\n"
                           "        Math.max(1, 2);\n        return DateUtil.now();\n    }\n}\n",
        "ts/dateFmt.ts": 'export class DateFmt {\n  static today(): string {\n    return "x";\n  }\n}\n',
        "ts/clock.ts": 'import { DateFmt } from "./dateFmt";\n\nexport function stampTs(): string {\n'
                       "  Math.max(1, 2);\n  return DateFmt.today();\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, calls = _flow(d)
    missing = [e for e in (("Clock.stamp", "DateUtil.now"), ("stampTs", "DateFmt.today"))
               if e not in calls]
    if missing:
        return f"a class-name receiver did not resolve: {missing}; edges {sorted(calls)}"
    if any(t.startswith("Math.") for _, t in calls):
        return "an edge was invented to Math.max"


def _written(methods: dict, edges) -> tuple[dict, list]:
    """Nodes and edges as flow_graph.json holds them -- what analyze, debt and report read.
    r40/r41 first asserted on build_flow.analyze()'s dicts and passed, while `write_graph`
    never copied `entry` into the file: every framework entry was still dead on a real repo."""
    path = os.path.join(tempfile.mkdtemp(), "flow_graph.json")
    build_flow.write_graph(methods, edges, path)
    with open(path, encoding="utf-8") as fh:
        graph = json.load(fh)
    return ({n["id"]: n for n in graph["nodes"]},
            [(e["source"], e["target"], e["type"]) for e in graph["edges"]])


def r40_framework_entries_are_not_dead():
    """real repo: every Spring filter, @Scheduled job and bean factory was reported dead --
    the framework calls them, so nothing in the graph ever will. Named per node as `entry`;
    an uncalled method with no such reason is still dead."""
    d = _tree({
        "Jobs.java": "public class Jobs {\n    @Scheduled(cron = \"0 0 * * * *\")\n"
                     "    public void nightly() {\n    }\n\n    public void unused() {\n    }\n}\n",
        "AuthFilter.java": "public class AuthFilter extends OncePerRequestFilter {\n    @Override\n"
                           "    protected void doFilterInternal(String req) {\n    }\n}\n",
        "Worker.cs": "public class Worker : BackgroundService {\n"
                     "    protected override void Execute() {\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = _written(*build_flow.analyze([d]))
    want = {"Jobs.nightly": "@Scheduled", "AuthFilter.doFilterInternal": "@Override",
            "Worker.Execute": "override"}
    wrong = {k: methods.get(k, {}).get("entry") for k, v in want.items()
             if methods.get(k, {}).get("entry") != v}
    if wrong:
        return f"entry not named: {wrong}"
    orphans = set(analyze.find_orphans(methods, list(edges)))
    if orphans & set(want):
        return f"framework-called methods reported dead: {sorted(orphans & set(want))}"
    if "Jobs.unused" not in orphans:
        return "an uncalled method with no framework caller stopped being dead"


def r41_next_conventions_are_entries():
    """real repo: a Next.js app router page, route handler and generateMetadata have no
    caller in any graph. Inside a Next app (next.config.*) they carry `entry`; the same
    files outside one do not. An anonymous default export gets a node, named by its file."""
    files = {
        "src/app/dashboard/page.tsx": "export default function DashboardPage() {\n  return loadRows();\n}\n\n"
                                      "function loadRows() {\n  return 1;\n}\n\n"
                                      "export async function generateMetadata() {\n  return {};\n}\n",
        "src/app/api/rows/route.ts": "export async function GET() {\n  return 1;\n}\n",
        "src/components/Dashboard.tsx": "export default function () {\n  return 2;\n}\n"}
    want = {"DashboardPage": "next:page", "GET": "next:route",
            "generateMetadata": "next:generateMetadata"}
    for with_next in (True, False):
        d = _tree({**files, **({"next.config.mjs": "export default {};\n"} if with_next else {})})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            methods, edges = _written(*build_flow.analyze([d]))
        if "Dashboard" not in methods:
            return f"the anonymous default export has no node: {sorted(methods)}"
        got = {k: methods.get(k, {}).get("entry") for k in want}
        orphans = set(analyze.find_orphans(methods, list(edges)))
        if with_next and (got != want or orphans & set(want)):
            return f"inside a Next app: entries {got}, dead {sorted(orphans & set(want))}"
        if not with_next and any(got.values()):
            return f"outside a Next app the conventions applied anyway: {got}"
        if "loadRows" in orphans:
            return "loadRows is called by the page and must not be dead"


def r42_ts_imports_fixture():
    """real repo: live Next.js files were reported dead. `tests/fixtures/ts_imports` pins the
    import shapes behind it: a tsconfig `@/` alias, a namespace import, a name two files
    define, an anonymous default export and an App Router page."""
    import build_graph
    import build_wiki
    root = os.path.join(REPO, "tests", "fixtures", "ts_imports")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, calls = _flow(root)
    want = {("OrderSummary", "formatSize"), ("OrderSummary", "toMessage"),
            ("OrderSummary", "ts_imports/src/lib/labels.label"), ("Dashboard", "formatSize")}
    if want - calls:
        return f"missing flow edge(s): {sorted(want - calls)}"
    if any(t == "ts_imports/src/legacy/labels.label" for _, t in calls):
        return "an edge went to the `label` the caller did not import"
    if methods.get("DashboardPage", {}).get("entry") != "next:page":
        return f"the page's default export is not next:page: {methods.get('DashboardPage', {}).get('entry')}"
    out = tempfile.mkdtemp()
    vault = os.path.join(out, "vault")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        build_wiki.build([root], vault)
        build_graph.build(vault, out)
    graph = json.load(open(os.path.join(out, "graph.json"), encoding="utf-8"))
    refs = {(e["source"], e["target"]) for e in graph["edges"]}
    want = {("OrderSummary", "FileSizeFormatModule"), ("OrderSummary", "ApiErrorModule"),
            ("OrderSummary", "ApiError"),                          # new ApiError(...)
            ("OrderSummary", "ts_imports/src/lib/labels.LabelsModule")}   # a name two files define
    if want - refs:
        return f"missing structure edge(s): {sorted(want - refs)}"
    if ("OrderSummary", "ts_imports/src/legacy/labels.LabelsModule") in refs:
        return "a structure edge went to the LabelsModule the import did not name"


def r43_installed_skill_copy_is_not_source():
    """real repo: the skill installed at `.claude/skills/code-archaeologist/` was graphed as
    part of the project it documents -- its scripts became orphans, dead files and untested
    nodes. Every walker skips a copy; pointing --src at the skill itself still graphs it."""
    skill = ".claude/skills/code-archaeologist"
    d = _tree({"app/shop.py": "def place_order():\n    return 1\n",
               f"{skill}/SKILL.md": "# skill\n",
               f"{skill}/scripts/archaeologist.py": "def skill_main():\n    return 0\n"})
    import scan_security
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, _ = build_flow.analyze([d])
        direct, _ = build_flow.analyze([os.path.join(d, *skill.split("/"))])
    if "skill_main" in methods or "place_order" not in methods:
        return f"flow map over the project: {sorted(methods)}"
    if any("code-archaeologist" in k for k in manifest.snapshot([d])):
        return "the freshness manifest hashes the skill copy"
    if any("code-archaeologist" in k for _, k in scan_security.iter_source_files([d])):
        return "the security scan reads the skill copy"
    if "skill_main" not in direct:
        return "--src pointed at the skill itself no longer graphs it"


def r44_java_method_references():
    """real repo: `schedule(this::clearFileStorageBin, ...)` registered a job and the job
    looked dead -- a method reference was not read as a call. Its receiver is stated as
    plainly as a call's (`this`, a type, a typed field), so the target is exact."""
    d = _tree({
        "Schedule.java": "public class Schedule {\n    private Store store;\n\n"
                         "    public void register(Runner runner) {\n        runner.run(this::clearBin);\n"
                         "        runner.run(Store::compact);\n        runner.run(store::flush);\n"
                         "        runner.run(Store::new);\n    }\n\n    public void clearBin() {\n    }\n}\n",
        "Store.java": "public class Store {\n    public static void compact() {\n    }\n\n"
                      "    public void flush() {\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, calls = _flow(d)
    want = {("Schedule.register", "Schedule.clearBin"), ("Schedule.register", "Store.compact"),
            ("Schedule.register", "Store.flush")}
    if want - calls:
        return f"method reference(s) not resolved: {sorted(want - calls)}; edges {sorted(calls)}"


def r45_module_load_calls():
    """real repo: `export const axiosInstance = createApiInstance(...)` runs when the module
    loads, outside any function, so createApiInstance had no caller and was dead. Named as
    `entry: module`; a call inside a function *passed* at top level is not load time."""
    d = _tree({"src/axiosInstance.ts": "function createApiInstance(base: string) {\n  return base;\n}\n\n"
                                       "function neverCalled() {\n  return 1;\n}\n\n"
                                       "function setup(fn: () => number) {\n  return fn;\n}\n\n"
                                       'export const axiosInstance = createApiInstance("/api");\n'
                                       "setup(() => neverCalled());\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([d]))
    got = {k: nodes.get(k, {}).get("entry") for k in ("createApiInstance", "setup", "neverCalled")}
    if got != {"createApiInstance": "module", "setup": "module", "neverCalled": None}:
        return f"module-load entries wrong: {got}"
    dead = set(analyze.find_orphans(nodes, edges))
    if {"createApiInstance", "setup"} & dead:
        return f"called at module load but reported dead: {sorted({'createApiInstance', 'setup'} & dead)}"


def r46_calls_on_a_call_result():
    """real repo: `resolveHandler(type).downloadFile(x)` (26 upload-handler methods) and
    `props.getPnoData().validate()` were dropped -- the receiver is a call, and no return
    type was recorded. Typed from declared return types and Lombok getters; any step
    unknown, or overloads disagreeing on a return type, still drops."""
    d = _tree({
        "UploadHandler.java": "public interface UploadHandler {\n    void downloadFile(String name);\n}\n",
        "Other.java": "public class Other {\n    public void go() {\n    }\n}\n",
        "PnoData.java": "public class PnoData {\n    private String cron;\n\n    public void validate() {\n    }\n}\n",
        "BatchProps.java": "@Data\npublic class BatchProps {\n    private PnoData pnoData;\n}\n",
        "MaintenanceService.java": (
            "public class MaintenanceService {\n    private BatchProps props;\n\n"
            "    public UploadHandler resolveHandler(String type) {\n        return null;\n    }\n\n"
            "    public UploadHandler pick(int a) {\n        return null;\n    }\n\n"
            "    public Other pick(String a) {\n        return null;\n    }\n\n"
            "    public void download(String type) {\n        resolveHandler(type).downloadFile(\"x\");\n"
            "        props.getPnoData().validate();\n        unknown(type).go();\n        pick(1).go();\n    }\n}\n"),
        "Screen.kt": "class Widget {\n    fun render() {}\n}\n\nclass Repo {\n    fun find(): Widget? {\n"
                     "        return null\n    }\n}\n\nclass Screen(val repo: Repo) {\n"
                     "    fun show() {\n        repo.find().render()\n    }\n}\n",
        "web/projectApi.ts": "export class ProjectApi {\n  approve(): string {\n    return \"x\";\n  }\n}\n\n"
                             "export function getApi(): ProjectApi {\n  return new ProjectApi();\n}\n\n"
                             "export function onApprove() {\n  return getApi().approve();\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, calls = _flow(d)
    want = {("MaintenanceService.download", "UploadHandler.downloadFile"),
            ("MaintenanceService.download", "PnoData.validate"),
            ("Screen.show", "Widget.render"), ("onApprove", "ProjectApi.approve")}
    if want - calls:
        return f"call(s) on a call's result not resolved: {sorted(want - calls)}"
    if ("MaintenanceService.download", "Other.go") in calls:
        return "an edge was guessed through an unknown call or disagreeing overload return types"


def r47_calls_through_a_variable():
    """real repo: `api.approveSetdatProject(...)` in an onClick reached nothing. Every exact
    shape now resolves -- a barrel re-export behind `import * as api`, an imported
    `new ProjectApi()` instance, an object literal's inline member and a member naming a
    function -- while a hook's untyped return value still drops."""
    root = os.path.join(REPO, "tests", "fixtures", "ts_imports")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([root]))
    calls = {(s, t) for s, t, kind in edges if kind == "calls"}
    want = {("ProjectActions", "approveSetdatProject"), ("ProjectActions", "ProjectApi.approve"),
            ("ProjectActions", "objectApi.reject"), ("ProjectActions", "archive"),
            ("objectApi.refresh", "helper")}
    if want - calls:
        return f"missing edge(s): {sorted(want - calls)}"
    if ("ProjectActions", "listProjects") in calls:
        return "an edge was guessed through a hook's untyped return value"
    if nodes.get("helper", {}).get("entry"):
        return "a call inside an object literal's method was taken for module-load code"


def r48_python_module_load_calls():
    """`app = create_app()` and `if __name__ == "__main__": raise SystemExit(main())` call
    functions from outside any node, so they looked dead -- JS/TS had the same gap (r45).
    Two files' `main`s stay each file's own; code inside a def or lambda is not load time."""
    d = _tree({
        "one.py": "def create_app():\n    return 1\n\n\ndef unused():\n    return 2\n\n\n"
                  "def main():\n    return 0\n\n\napp = create_app()\nlater = lambda: unused()\n\n"
                  "if __name__ == \"__main__\":\n    raise SystemExit(main())\n",
        "two.py": "def main():\n    return 0\n\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, _ = _written(*build_flow.analyze([d]))
    got = {k: nodes.get(k, {}).get("entry") for k in ("create_app", "one.main", "two.main", "unused")}
    if got != {"create_app": "module", "one.main": "module", "two.main": "module", "unused": None}:
        return f"module-load entries wrong: {got}; nodes {sorted(nodes)}"


def r49_jsx_render_edges():
    """`page.tsx` renders `<Dashboard />`, and the flow map had no edge for it: an impact
    query on a component missed every page that renders it. A `renders` edge now, resolved
    like a call; `<Ctx.Item />` names an object's member, so it draws nothing."""
    d = _tree({
        "src/Badge.tsx": "export function Badge() {\n  return <span>b</span>;\n}\n\n"
                         "export function Item() {\n  return <li>i</li>;\n}\n",
        "src/Card.tsx": 'import { Badge } from "./Badge";\n\nexport function Card() {\n'
                        "  return (\n    <div>\n      <Badge />\n      <Ctx.Item />\n    </div>\n  );\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = _written(*build_flow.analyze([d]))
    if ("Card", "Badge", "renders") not in edges:
        return f"no renders edge Card -> Badge: {edges}"
    if any(t == "Item" for _, t, _k in edges):
        return "`<Ctx.Item />` drew an edge to a component named Item"
    if ("Card", "Badge", "calls") in edges:
        return "a render was recorded as a call"
    fixture = os.path.join(REPO, "tests", "fixtures", "ts_imports")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, fixture_edges = _written(*build_flow.analyze([fixture]))
    if ("DashboardPage", "Dashboard", "renders") not in fixture_edges:
        return "the fixture's page does not render its Dashboard"


def r50_implements_links():
    """A call through an interface stopped at the declaration, and every implementation of
    it was reported as dead code: nothing joined them. An `implements` link now does --
    directly or through an abstract class -- and traces, impact and orphans walk it from
    the declaration to the implementation, while cycles, layers and coupling ignore it."""
    d = _tree({
        "shop/PricingRule.java": "interface PricingRule {\n    int price(int units);\n}\n",
        "shop/Rates.java": "abstract class BaseRate implements PricingRule {\n}\n\n"
                           "class FlatRate implements PricingRule {\n"
                           "    public int price(int units) { return 1; }\n}\n\n"
                           "class TieredRate extends BaseRate {\n"
                           "    public int price(int units) { return 2; }\n}\n\n"
                           "class CachedRate implements PricingRule {\n"
                           "    private PricingRule inner;\n"
                           "    public int price(int units) { return inner.price(units); }\n}\n\n"
                           "class Unrelated {\n    public int price(int units) { return 3; }\n}\n",
        "shop/Checkout.java": "class Checkout {\n    private PricingRule rule;\n"
                              "    public int total(int units) { return rule.price(units); }\n}\n",
        "shop/shapes.py": "class Shape:\n    def area(self):\n        return 0\n\n\n"
                          "class Square(Shape):\n    def area(self):\n        return 4\n\n\n"
                          "def measure(shape: Shape):\n    return shape.area()\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, raw = build_flow.analyze([d])
    path = os.path.join(tempfile.mkdtemp(), "flow_graph.json")
    build_flow.write_graph(methods, raw, path)
    nodes, edges = analyze.load(path)
    want = {("FlatRate.price", "PricingRule.price"), ("TieredRate.price", "PricingRule.price"),
            ("CachedRate.price", "PricingRule.price"), ("Square.area", "Shape.area")}
    got = {(s, t) for s, t, k in edges if k in taxonomy.INHERITANCE_LINKS}
    if got != want:
        return f"implements links {sorted(got)}, expected {sorted(want)}"
    # `Shape.area` has a body, so replacing it is `overrides`; the interface's is `implements`.
    if ("Square.area", "Shape.area", "overrides") not in edges or \
            ("FlatRate.price", "PricingRule.price", "implements") not in edges:
        return f"link kinds wrong: {sorted(e for e in edges if e[2] in taxonomy.INHERITANCE_LINKS)}"
    # CachedRate.price really calls PricingRule.price (`inner.price`), so it has both links.
    if any(k == "calls" and (s, t) in want - {("CachedRate.price", "PricingRule.price")} for s, t, k in edges):
        return "an implementation was recorded as calling the method it implements"
    orphans = analyze.find_orphans(nodes, edges)
    if set(orphans) & {"FlatRate.price", "TieredRate.price", "Square.area"} or "Unrelated.price" not in orphans:
        return f"orphans {orphans}: implementations must not be dead, Unrelated.price must"
    _ids, adj, radj, _src = trace_path.load_graph(path)
    trace = trace_path.bfs_shortest(adj, "Checkout.total", "TieredRate.price")
    if trace != ["Checkout.total", "PricingRule.price", "TieredRate.price"]:
        return f"trace Checkout.total -> TieredRate.price is {trace}"
    if "Checkout.total" not in trace_path.impact_of(radj, "FlatRate.price"):
        return "changing FlatRate.price does not reach Checkout.total"
    if any("CachedRate.price" in comp for comp in analyze.find_cycles(nodes, edges)):
        return "a decorator that delegates to its own interface was reported as a cycle"
    if any(k in taxonomy.INHERITANCE_LINKS for _s, _t, k in analyze.app_edges(nodes, edges)):
        return "implements links were counted as coupling"


def r51_name_matched_is_earned():
    """`precision: name-matched` sat on every JS/TS, Ruby, PHP, Elixir and Groovy node whether
    or not it lost a call -- a language label (finding #25). It is earned now, in any language:
    only a node that dropped a call through a receiver of unknown type, to a name the graph
    defines, carries it -- and names that call in `untyped`."""
    d = _tree({
        "src/store.ts": "export class Store {\n  save(x: string) {}\n}\n",
        "src/use.ts": 'import { Store } from "./store";\n\n'
                      'export function typed() {\n  new Store().save("a");\n}\n\n'
                      'export function untyped(other) {\n  other.save("b");\n}\n\n'
                      'export function library() {\n  console.log("c");\n}\n',
        # `thing` is typed (Object, not in the graph: dropped, but not untyped); the type of
        # `thing.inner` is stated nowhere, so the call through it is.
        "shop/Worker.java": "class Worker {\n    Object thing;\n"
                            "    void run() { thing.toString(); thing.inner.save(\"x\"); }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, _ = _written(*build_flow.analyze([d]))
    got = {k: nodes.get(k, {}).get("precision") for k in ("typed", "untyped", "library", "Worker.run")}
    want = {"typed": None, "untyped": ["name-matched"], "library": None, "Worker.run": ["name-matched"]}
    if got != want:
        return f"precision {got}, expected {want}"
    if nodes["untyped"].get("untyped") != ["save"]:
        return f"untyped of `untyped` is {nodes['untyped'].get('untyped')}, expected ['save']"


def r52_calls_through_globals():
    """A call through a global dropped in Python, Kotlin and Go, and Python's own
    `ClassName.method()` dropped where every other language linked it (finding #27). A
    module-level or top-level `x = Store()`, one imported from another file, a Go package
    `var`, and `Registry.STORE.save()` through a static field's declared type now resolve;
    a parameter or local of the same name still wins."""
    d = _tree({
        "py/store.py": "class PyStore:\n    def save(self):\n        pass\n\n"
                       "    @staticmethod\n    def make():\n        pass\n\n\nstore = PyStore()\n\n\n"
                       "def py_class_call():\n    PyStore.make()\n\n\n"
                       "def py_global():\n    store.save()\n\n\n"
                       "def py_shadowed(store):\n    store.save()\n",
        "py/user.py": "from store import store\n\n\ndef py_imported():\n    store.save()\n",
        "kt/Globals.kt": "class KtStore {\n    fun save() {}\n}\n\nval ktStore = KtStore()\n\n"
                         "fun ktGlobal() {\n    ktStore.save()\n}\n\n"
                         "fun ktShadowed(ktStore: Any) {\n    ktStore.save()\n}\n",
        "go/globals.go": "package main\n\ntype GoStore struct{}\n\nfunc (s *GoStore) Save() {}\n\n"
                         "var goStore = &GoStore{}\n\nfunc goGlobal() {\n\tgoStore.Save()\n}\n\n"
                         "func goShadowed() {\n\tgoStore := other()\n\tgoStore.Save()\n}\n\n"
                         "func other() int { return 1 }\n",
        "java/Registry.java": "class OrderStore {\n    void save() {}\n}\n\n"
                              "class Registry {\n    static final OrderStore STORE = new OrderStore();\n}\n\n"
                              "class JavaCaller {\n    void viaRegistry() { Registry.STORE.save(); }\n}\n",
        "cs/Registry.cs": "class CsStore\n{\n    public void Save() { }\n}\n\n"
                          "static class CsRegistry\n{\n    public static CsStore Store = new CsStore();\n}\n\n"
                          "class CsCaller\n{\n    void ViaRegistry() { CsRegistry.Store.Save(); }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = _written(*build_flow.analyze([d]))
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("py_class_call", "PyStore.make"), ("py_global", "PyStore.save"), ("py_imported", "PyStore.save"),
            ("ktGlobal", "KtStore.save"), ("goGlobal", "GoStore.Save"),
            ("JavaCaller.viaRegistry", "OrderStore.save"), ("CsCaller.ViaRegistry", "CsStore.Save")}
    if want - calls:
        return f"missing call links {sorted(want - calls)}"
    wrong = {(s, t) for s, t in calls if s in ("py_shadowed", "ktShadowed", "goShadowed")
             and t in ("PyStore.save", "KtStore.save", "GoStore.Save")}
    if wrong:
        return f"a parameter or local named like a global was typed as the global: {sorted(wrong)}"


def r53_calls_outside_methods():
    """A call in a field initializer, a static or init block, a constructor or a Go package
    `var` was never collected: its callee had no caller, no `entry` and no `unresolved`
    trace, so it was dead code with no hint why (finding #28). Each callee now carries
    `entry: init`, and a Go `func init()` too; a method nothing calls is still an orphan."""
    d = _tree({
        "java/Init.java": "class JStore {\n    static int save() { return 1; }\n"
                          "    static int load() { return 2; }\n    static int open() { return 3; }\n"
                          "    static int unused() { return 4; }\n}\n\n"
                          "class JApp {\n    int x = JStore.save();\n\n    static {\n        JStore.load();\n    }\n\n"
                          "    JApp() {\n        JStore.open();\n    }\n}\n",
        "cs/Init.cs": "class CStore\n{\n    public static int Save() { return 1; }\n"
                      "    public static int Open() { return 2; }\n}\n\n"
                      "class CApp\n{\n    int x = CStore.Save();\n\n    CApp() { CStore.Open(); }\n}\n",
        "kt/Init.kt": "object KStore {\n    fun save(): Int = 1\n    fun load(): Int = 2\n    fun top(): Int = 3\n}\n\n"
                      "class KApp {\n    val x = KStore.save()\n\n    init {\n        KStore.load()\n    }\n}\n\n"
                      "val y = KStore.top()\n",
        "go/init.go": "package main\n\nfunc goSave() int { return 1 }\n\nvar x = goSave()\n\nfunc init() {}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([d]))
    want = ("JStore.save", "JStore.load", "JStore.open", "CStore.Save", "CStore.Open",
            "KStore.save", "KStore.load", "KStore.top", "goSave", "init")
    got = {k: nodes.get(k, {}).get("entry") for k in want}
    if any(v != "init" for v in got.values()):
        return f"entries {got}, expected every one to be 'init'"
    if "JStore.unused" not in analyze.find_orphans(nodes, edges):
        return "JStore.unused is called by nothing, and is no longer reported"


def r54_spring_injected_beans():
    """A call through an injected interface stopped at the declaration even where the source
    settles which bean Spring injects. It now links to that bean's method when exactly one
    bean implements the type, `@Qualifier` names one, one is `@Primary`, or a `@Bean` method
    builds it -- and still stops at the declaration when two beans could be meant or one of
    them is conditional (`@Profile`)."""
    d = _tree({
        "shop/Single.java": "interface Repo {\n    String find();\n}\n\n"
                            "@Repository\nclass JpaRepo implements Repo {\n"
                            "    public String find() { return \"x\"; }\n}\n\n"
                            "@Service\nclass UsesSingle {\n    private final Repo repo;\n"
                            "    UsesSingle(Repo repo) { this.repo = repo; }\n"
                            "    String run() { return repo.find(); }\n}\n",
        "shop/Qualified.java": "interface Rule {\n    int price();\n}\n\n"
                               "@Service(\"fast\")\nclass FastRule implements Rule {\n"
                               "    public int price() { return 1; }\n}\n\n"
                               "@Service(\"slow\")\nclass SlowRule implements Rule {\n"
                               "    public int price() { return 2; }\n}\n\n"
                               "@Service\nclass UsesQualifier {\n    @Qualifier(\"slow\")\n    @Autowired\n"
                               "    private Rule rule;\n    int total() { return rule.price(); }\n}\n\n"
                               "@Service\nclass UsesAmbiguous {\n    @Autowired\n    private Rule rule;\n"
                               "    int total() { return rule.price(); }\n}\n",
        "shop/Primary.java": "interface Clock {\n    long now();\n}\n\n"
                             "@Component\nclass SystemClock implements Clock {\n"
                             "    public long now() { return 1; }\n}\n\n"
                             "@Primary\n@Component\nclass FixedClock implements Clock {\n"
                             "    public long now() { return 2; }\n}\n\n"
                             "@Service\nclass UsesPrimary {\n    @Autowired\n    private Clock clock;\n"
                             "    long stamp() { return clock.now(); }\n}\n",
        "shop/Config.java": "interface Mailer {\n    void send();\n}\n\n"
                            "class SmtpMailer implements Mailer {\n    public void send() {}\n}\n\n"
                            "class LogMailer implements Mailer {\n    public void send() {}\n}\n\n"
                            "@Configuration\nclass MailConfig {\n    @Bean\n    Mailer mailer() {\n"
                            "        return new SmtpMailer();\n    }\n}\n\n"
                            "@Service\nclass UsesBean {\n    @Autowired\n    private Mailer mailer;\n"
                            "    void notifyUsers() { mailer.send(); }\n}\n",
        "shop/Profiled.java": "interface Cache {\n    void put();\n}\n\n"
                              "@Component\nclass RedisCache implements Cache {\n    public void put() {}\n}\n\n"
                              "@Profile(\"test\")\n@Component\nclass MemoryCache implements Cache {\n"
                              "    public void put() {}\n}\n\n"
                              "@Service\nclass UsesProfiled {\n    @Autowired\n    private Cache cache;\n"
                              "    void store() { cache.put(); }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([d]))
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("UsesSingle.run", "JpaRepo.find"), ("UsesQualifier.total", "SlowRule.price"),
            ("UsesPrimary.stamp", "FixedClock.now"), ("UsesBean.notifyUsers", "SmtpMailer.send")}
    if want - calls:
        return f"missing injected call links {sorted(want - calls)}"
    if ("UsesSingle.run", "Repo.find") in calls or "interface-dispatch" in (nodes["UsesSingle.run"].get("precision") or []):
        return "a call Spring resolves still stops at the declaration"
    stays = {("UsesAmbiguous.total", "Rule.price"), ("UsesProfiled.store", "Cache.put")}
    if stays - calls:
        return f"an unsettled injection lost its link to the declaration: {sorted(stays - calls)}"
    guessed = {(s, t) for s, t in calls if s in ("UsesAmbiguous.total", "UsesProfiled.store") and (s, t) not in stays}
    if guessed:
        return f"an injection two beans could satisfy was guessed: {sorted(guessed)}"


def r56_kotlin_spring_injected_beans():
    """r54's Spring rule reached Java and Groovy only: a Kotlin service's call through an
    injected interface stopped at the declaration even where the source settled the bean
    (finding #30). Kotlin's stereotypes, `@Qualifier` on a constructor property or a
    `lateinit` field, `@Primary` and `@Bean` functions are read now, into the same rule."""
    d = _tree({
        "shop/Beans.kt": "interface Repo {\n    fun find(): String\n}\n\n"
                         "@Repository\nclass JpaRepo : Repo {\n    override fun find(): String = \"x\"\n}\n\n"
                         "@Service\nclass UsesSingle(private val repo: Repo) {\n    fun run(): String = repo.find()\n}\n\n"
                         "interface Rule {\n    fun price(): Int\n}\n\n"
                         "@Service(\"fast\")\nclass FastRule : Rule {\n    override fun price(): Int = 1\n}\n\n"
                         "@Service(\"slow\")\nclass SlowRule : Rule {\n    override fun price(): Int = 2\n}\n\n"
                         "@Service\nclass UsesQualifier(@Qualifier(\"slow\") private val rule: Rule) {\n"
                         "    fun total(): Int = rule.price()\n}\n\n"
                         "@Service\nclass UsesField {\n    @Autowired\n    @Qualifier(\"fast\")\n"
                         "    lateinit var rule: Rule\n\n    fun total(): Int = rule.price()\n}\n\n"
                         "@Service\nclass UsesAmbiguous(private val rule: Rule) {\n    fun total(): Int = rule.price()\n}\n\n"
                         "interface Clock {\n    fun now(): Long\n}\n\n"
                         "@Component\nclass SystemClock : Clock {\n    override fun now(): Long = 1L\n}\n\n"
                         "@Primary\n@Component\nclass FixedClock : Clock {\n    override fun now(): Long = 2L\n}\n\n"
                         "@Service\nclass UsesPrimary(private val clock: Clock) {\n    fun stamp(): Long = clock.now()\n}\n\n"
                         "interface Mailer {\n    fun send()\n}\n\n"
                         "class SmtpMailer : Mailer {\n    override fun send() {}\n}\n\n"
                         "class LogMailer : Mailer {\n    override fun send() {}\n}\n\n"
                         "@Configuration\nclass MailConfig {\n    @Bean\n    fun mailer(): Mailer = SmtpMailer()\n}\n\n"
                         "@Service\nclass UsesBean(private val mailer: Mailer) {\n    fun notifyUsers() = mailer.send()\n}\n\n"
                         "interface Cache {\n    fun put()\n}\n\n"
                         "@Component\nclass RedisCache : Cache {\n    override fun put() {}\n}\n\n"
                         "@Profile(\"test\")\n@Component\nclass MemoryCache : Cache {\n    override fun put() {}\n}\n\n"
                         "@Service\nclass UsesProfiled(private val cache: Cache) {\n    fun store() = cache.put()\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = _written(*build_flow.analyze([d]))
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("UsesSingle.run", "JpaRepo.find"), ("UsesQualifier.total", "SlowRule.price"),
            ("UsesField.total", "FastRule.price"), ("UsesPrimary.stamp", "FixedClock.now"),
            ("UsesBean.notifyUsers", "SmtpMailer.send")}
    if want - calls:
        return f"missing injected call links {sorted(want - calls)}"
    stays = {("UsesAmbiguous.total", "Rule.price"), ("UsesProfiled.store", "Cache.put")}
    if stays - calls:
        return f"an unsettled injection lost its link to the declaration: {sorted(stays - calls)}"
    guessed = {(s, t) for s, t in calls if s in ("UsesAmbiguous.total", "UsesProfiled.store") and (s, t) not in stays}
    if guessed:
        return f"an injection two beans could satisfy was guessed: {sorted(guessed)}"


def r55_structure_implements_links():
    """The structure map listed every implementation of an interface as an orphan class:
    `FlatRate -> PricingRule` points from the implementation, so nothing pointed at it
    (finding #29). A base is now an `implements` link there too, walked the same way, so a
    class implementing a referenced interface is not dead; a class that nothing references
    and that implements nothing still is."""
    import build_graph
    import build_wiki
    src = _tree({"shop/Rules.java": "interface PricingRule {\n    int price();\n}\n\n"
                                    "class FlatRate implements PricingRule {\n"
                                    "    public int price() { return 1; }\n}\n\n"
                                    "class Loner {\n    void x() {}\n}\n\n"
                                    "class Checkout {\n    private PricingRule rule;\n}\n"})
    d = tempfile.mkdtemp()
    vault, out = os.path.join(d, "vault"), os.path.join(d, "out")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        build_wiki.build([src], vault)
        build_graph.build(vault, out)
    nodes, edges = analyze.load(os.path.join(out, "graph.json"))
    if ("FlatRate", "PricingRule", "implements") not in edges:
        return f"no implements link FlatRate -> PricingRule: {edges}"
    if ("Checkout", "PricingRule", "references") not in edges:
        return f"the field reference Checkout -> PricingRule was lost: {edges}"
    orphans = analyze.find_orphans(nodes, edges)
    if "FlatRate" in orphans or "Loner" not in orphans:
        return f"orphans {orphans}: FlatRate implements a referenced interface, Loner is dead"


def _structure(src: str) -> tuple[dict, list]:
    """(nodes, links) of the structure map built from `src` into a temp dir."""
    import build_graph
    import build_wiki
    d = tempfile.mkdtemp()
    vault, out = os.path.join(d, "vault"), os.path.join(d, "out")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        build_wiki.build([src], vault)
        build_graph.build(vault, out)
    return analyze.load(os.path.join(out, "graph.json"))


def r57_shared_class_names_by_package():
    """real repo: an API and a socket app in one repository both define `ConfigService`,
    `LogService` and `DateUtil`, so every call to them from another file was dropped -- a
    shared name resolved only from the caller's own file: 42 call sites, 0 callers. The
    source settles it: an exact import, a wildcard import or C# `using`, the same package."""
    app = lambda pkg, name: (f"package com.acme.{pkg}.service;\n\npublic class {name} {{\n"
                             f"    public int getConfigInt(String key) {{\n        return 1;\n    }}\n}}\n")
    d = _tree({
        "api/ConfigService.java": app("api", "ConfigService"),
        "socket/ConfigService.java": app("socket", "ConfigService"),
        "api/ApiJob.java": "package com.acme.api.job;\n\nimport com.acme.api.service.ConfigService;\n\n"
                           "public class ApiJob {\n    private ConfigService config;\n\n"
                           "    public int run() {\n        return config.getConfigInt(\"x\");\n    }\n}\n",
        "socket/SocketJob.java": "package com.acme.socket.job;\n\nimport com.acme.socket.service.*;\n\n"
                                 "public class SocketJob {\n    private ConfigService config;\n\n"
                                 "    public int run() {\n        return config.getConfigInt(\"x\");\n    }\n}\n",
        "api/ApiHelper.java": "package com.acme.api.service;\n\npublic class ApiHelper {\n"
                              "    private ConfigService config;\n\n"
                              "    public int help() {\n        return config.getConfigInt(\"x\");\n    }\n}\n",
        "web/Store.cs": "namespace Shop.Api;\n\npublic class Store {\n    public void Save() {\n    }\n}\n",
        "worker/Store.cs": "namespace Shop.Worker;\n\npublic class Store {\n    public void Save() {\n    }\n}\n",
        "web/Page.cs": "using Shop.Api;\n\nnamespace Shop.Web;\n\npublic class Page {\n"
                       "    private Store _store;\n\n    public void Go() {\n        _store.Save();\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = build_flow.analyze([d])
    where = lambda nid: methods[nid]["source"].split(":")[0].replace("\\", "/")
    calls = {(methods[s]["cls"] + "." + methods[s]["name"], where(t)) for s, t, k in edges if k == "calls"}
    want = {("ApiJob.run", "api/ConfigService.java"), ("SocketJob.run", "socket/ConfigService.java"),
            ("ApiHelper.help", "api/ConfigService.java"), ("Page.Go", "web/Store.cs")}
    missing = [w for w in want if not any(c == w[0] and f.endswith(w[1]) for c, f in calls)]
    if missing:
        return f"calls to a class name two files define not settled by package/imports: {missing}; got {sorted(calls)}"
    wrong = [(c, f) for c, f in calls if (c.startswith("ApiJob") and "socket/" in f)
             or (c.startswith("SocketJob") and "api/" in f) or (c == "Page.Go" and "worker/" in f)]
    if wrong:
        return f"a call landed in the other application's class: {wrong}"
    nodes, links = _structure(d)
    src_of = lambda nid: (nodes[nid].get("source") or "").replace("\\", "/")
    if not any(s.startswith("ApiJob") and "api/ConfigService.java" in src_of(t) for s, t, k in links):
        return f"structure map: ApiJob does not reference its own app's ConfigService: {links}"


def r58_inherited_helper_calls():
    """real repo: `nz(...)`, `detailSpecification(...)` and `stableOrder(...)` live in the
    upload handlers' base class and are called with no receiver from every subclass, yet
    were listed as dead: a bare call looked in the caller's own class, then for a module
    function, never in the classes it extends."""
    d = _tree({
        "BaseHandler.java": "public abstract class BaseHandler {\n    protected int stableOrder(int v) {\n"
                            "        return v;\n    }\n}\n",
        "MasterDataUploadHandler.java": "public abstract class MasterDataUploadHandler extends BaseHandler {\n"
                                        "    protected String nz(String v) {\n        return v;\n    }\n}\n",
        "UpcFnaUploadHandler.java": "public class UpcFnaUploadHandler extends MasterDataUploadHandler {\n"
                                    "    public String upload(String v) {\n        stableOrder(1);\n"
                                    "        missing(v);\n        return nz(v) + this.nz(v);\n    }\n}\n",
        "Caller.java": "public class Caller {\n    private UpcFnaUploadHandler handler;\n\n"
                       "    public String go() {\n        return handler.nz(\"x\");\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([d]))
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("UpcFnaUploadHandler.upload", "MasterDataUploadHandler.nz"),
            ("UpcFnaUploadHandler.upload", "BaseHandler.stableOrder"),
            ("Caller.go", "MasterDataUploadHandler.nz")}
    if want - calls:
        return f"inherited call(s) not resolved: {sorted(want - calls)}; got {sorted(calls)}"
    dead = set(analyze.find_orphans(nodes, edges))
    if {"MasterDataUploadHandler.nz", "BaseHandler.stableOrder"} & dead:
        return f"an inherited helper is still dead: {sorted(dead)}"


def r59_typed_locals():
    """real repo: `R3RequestDto request = ...; request.describe()` left `describe` dead -- a
    local's type was read only from `= new X(...)`, so a local assigned from a call had none.
    The declaration states it (Java, C#), and a for-each variable too; `var` states nothing."""
    d = _tree({
        "R3RequestDto.java": "public class R3RequestDto {\n    public String describe() {\n        return \"\";\n    }\n}\n",
        "Item.java": "public class Item {\n    public void check() {\n    }\n}\n",
        "R3ReadJudgmentHandler.java": "public class R3ReadJudgmentHandler {\n"
                                      "    public String handle(Mapper m) {\n        R3RequestDto request = m.read();\n"
                                      "        for (Item item : m.all()) {\n            item.check();\n        }\n"
                                      "        return request.describe();\n    }\n}\n",
        "Dto.cs": "public class Dto {\n    public string Describe() {\n        return \"\";\n    }\n}\n",
        "Row.cs": "public class Row {\n    public void Check() {\n    }\n}\n",
        "Handler.cs": "public class Handler {\n    public string Handle(Mapper m) {\n        Dto d = m.Read();\n"
                      "        foreach (Row r in m.All()) {\n            r.Check();\n        }\n"
                      "        return d.Describe();\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, calls = _flow(d)
    want = {("R3ReadJudgmentHandler.handle", "R3RequestDto.describe"), ("R3ReadJudgmentHandler.handle", "Item.check"),
            ("Handler.Handle", "Dto.Describe"), ("Handler.Handle", "Row.Check")}
    if want - calls:
        return f"call(s) through a typed local not resolved: {sorted(want - calls)}"


def r60_js_constructor_calls():
    """real repo: `apiError.ts` was a dead file although `throw new ApiError(...)` used it --
    `new X()` was not a call, so `ApiError.constructor` had no caller."""
    import debt
    d = _tree({"web/apiError.ts": "export class ApiError extends Error {\n  constructor(message: string) {\n"
                                  "    super(message);\n  }\n}\n",
               "web/client.ts": 'import { ApiError } from "./apiError";\n\nexport function load() {\n'
                                '  const cache = new Map();\n  throw new ApiError("x");\n}\n'})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, raw = build_flow.analyze([d])
    path = os.path.join(tempfile.mkdtemp(), "flow_graph.json")
    build_flow.write_graph(methods, raw, path)
    if ("load", "ApiError.constructor", "calls") not in raw:
        return f"no call link load -> ApiError.constructor: {raw}"
    dead = debt.find_dead(path)["files"]
    if any(f.endswith("apiError.ts") for f in dead):
        return f"apiError.ts is still a dead file: {dead}"


def r61_oop_model():
    """A class node says what it is -- `interface`, `abstract`, `class` -- and a base link says
    which relation it is: a class `implements` an interface and `extends` a class; a method
    `implements` a declaration and `overrides` a body. A default body every subclass replaces
    never runs, and is reported `overridden`, not dead (the AAS upload handler's base methods)."""
    d = _tree({
        "oop/Handler.java": "public interface Handler {\n    void handle();\n}\n",
        "oop/BaseHandler.java": "public abstract class BaseHandler implements Handler {\n"
                                "    public void saveDetails() {\n    }\n\n    public void common() {\n    }\n\n"
                                "    public abstract void columnSpecs();\n}\n",
        "oop/AasHandler.java": "public class AasHandler extends BaseHandler {\n    public void handle() {\n    }\n\n"
                               "    public void saveDetails() {\n    }\n\n    public void columnSpecs() {\n    }\n}\n",
        "oop/Runner.java": "public class Runner {\n    private Handler handler;\n    private AasHandler aas;\n\n"
                           "    public void run() {\n        handler.handle();\n        aas.common();\n    }\n}\n",
        "oop/Loner.java": "public class Loner {\n    public void unused() {\n    }\n}\n",
        "k/Repo.kt": "interface Repo {\n    fun find()\n}\n\nabstract class BaseRepo : Repo {\n"
                     "    override fun find() {}\n}\n",
        "web/base.ts": "export abstract class BaseApi {\n  load() {\n    return 1;\n  }\n}\n\n"
                       "export class ProjectApi extends BaseApi {\n  load() {\n    return 2;\n  }\n}\n",
        "py/shapes.py": "from abc import ABC, abstractmethod\nfrom typing import Protocol\n\n\n"
                        "class Drawable(Protocol):\n    def draw(self):\n        ...\n\n\n"
                        "class Shape(ABC):\n    @abstractmethod\n    def area(self):\n        raise NotImplementedError\n\n\n"
                        "class Square(Shape):\n    def area(self):\n        return 4\n"})
    nodes, links = _structure(d)
    kinds = {k: nodes.get(k, {}).get("kind") for k in
             ("Handler", "BaseHandler", "AasHandler", "Repo", "BaseRepo", "BaseApi", "ProjectApi", "Drawable", "Shape", "Square")}
    want_kinds = {"Handler": "interface", "BaseHandler": "abstract", "AasHandler": "class", "Repo": "interface",
                  "BaseRepo": "abstract", "BaseApi": "abstract", "ProjectApi": "class", "Drawable": "interface",
                  "Shape": "abstract", "Square": "class"}
    if kinds != want_kinds:
        return f"class kinds {kinds}"
    want_links = {("BaseHandler", "Handler", "implements"), ("AasHandler", "BaseHandler", "extends"),
                  ("BaseRepo", "Repo", "implements"), ("ProjectApi", "BaseApi", "extends"),
                  ("Square", "Shape", "extends")}
    got_links = {e for e in links if e[2] in taxonomy.INHERITANCE_LINKS}
    if want_links - got_links:
        return f"structure inheritance links missing: {sorted(want_links - got_links)}; got {sorted(got_links)}"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        fnodes, fedges = _written(*build_flow.analyze([d]))
    want = {("AasHandler.handle", "Handler.handle", "implements"),
            ("AasHandler.saveDetails", "BaseHandler.saveDetails", "overrides"),
            ("AasHandler.columnSpecs", "BaseHandler.columnSpecs", "implements"),
            ("BaseRepo.find", "Repo.find", "implements"),
            ("ProjectApi.load", "BaseApi.load", "overrides"),
            ("Square.area", "Shape.area", "implements")}
    got = {e for e in fedges if e[2] in taxonomy.INHERITANCE_LINKS}
    if want - got:
        return f"flow inheritance links missing: {sorted(want - got)}; got {sorted(got)}"
    overridden = analyze.find_overridden(fnodes, fedges)
    if overridden != ["BaseApi.load", "BaseHandler.saveDetails"]:
        return f"overridden {overridden}: expected the two defaults every subclass replaces"
    dead = analyze.find_orphans(fnodes, fedges)
    if set(overridden) & set(dead) or "Loner.unused" not in dead:
        return f"orphans {dead}: overridden bodies are not dead, Loner.unused is"
    if fnodes.get("BaseHandler.common", {}).get("overridden") or "BaseHandler.common" in dead:
        return "BaseHandler.common is inherited and called, so neither overridden nor dead"


def r62_alias_in_two_apps():
    """real repo: two frontends each import `exportMasterData` from `@/services/masterDataService`
    with no tsconfig `paths`; the suffix match found both files and dropped every call. An
    alias is the importer's own package's, so the file inside the nearest package.json wins."""
    svc = ("export async function exportMasterData(t: string): Promise<void> {\n  return;\n}\n"
           "export const searchMasterData = async (q: string) => {\n  return [];\n};\n")
    view = ('import { exportMasterData, searchMasterData } from "@/services/masterDataService";\n\n'
            "export function MasterDataPreview() {\n  exportMasterData(\"t\");\n  searchMasterData(\"q\");\n"
            "  return null;\n}\n")
    files = {}
    for app in ("app-a", "app-b"):
        files.update({f"{app}/package.json": '{"name": "%s"}\n' % app,
                      f"{app}/src/services/masterDataService.ts": svc,
                      f"{app}/src/components/MasterDataPreview.tsx": view})
    d = _tree(files)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    for app, other in (("app-a", "app-b"), ("app-b", "app-a")):
        for fn in ("exportMasterData", "searchMasterData"):
            if not any(f"{app}/src/components/" in s and t.endswith(f"{app}/src/services/masterDataService.{fn}")
                       for s, t in calls):
                return f"{app}'s {fn} call did not reach its own service; edges {sorted(calls)}"
        if any(f"{app}/src/components/" in s and f"{other}/" in t for s, t in calls):
            return f"a call crossed from {app} into {other}: {sorted(calls)}"


def r63_varargs_and_unpicked_overloads():
    """real repo: `this::values` names three overloads and each calls `values(String...)`, yet
    all four were dead: a method reference cannot pick an overload, `String... parts` was read
    as no parameter at all, and a varargs overload never matched a call's argument count."""
    d = _tree({"ReportMail.java":
               "public class ReportMail {\n"
               "    public String build(java.util.List<Row> rows) {\n"
               "        return rows.stream().map(this::values).findFirst().orElse(\"\");\n    }\n\n"
               "    private String values(Row row) {\n        return values(row.getA(), row.getB());\n    }\n\n"
               "    private String values(Header header) {\n        return values(header.getX(), \"h\");\n    }\n\n"
               "    private String values(Footer footer) {\n        return values(\"a\", \"b\", \"c\");\n    }\n\n"
               "    private String values(String... parts) {\n        return String.join(\",\", parts);\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([d]))
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {(f"ReportMail.values({t})", "ReportMail.values(String[])") for t in ("Row", "Header", "Footer")}
    if want - calls:
        return f"varargs call(s) not resolved: {sorted(want - calls)}; nodes {sorted(nodes)}"
    if nodes.get("ReportMail.build", {}).get("ambiguous") != ["ReportMail.values"]:
        return f"`this::values` should stay ambiguous: {nodes.get('ReportMail.build')}"
    dead = [o for o in analyze.find_orphans(nodes, edges) if o.startswith("ReportMail.values")]
    if dead:
        return f"an overload one ambiguous call may reach is called dead: {dead}"


def r64_mapstruct_expressions():
    """real repo: four mappers used `toDisplayName` only inside
    `@Mapping(expression = "java(toDisplayName(...))")`, and it was dead -- nothing read the
    Java in the string, which the generated mapper runs."""
    d = _tree({
        "ItemMapper.java": "@Mapper(componentModel = \"spring\")\npublic interface ItemMapper {\n"
                           "    @Mapping(target = \"displayName\", expression = \"java(toDisplayName(item.getName()))\")\n"
                           "    ItemDto toDto(Item item);\n\n"
                           "    @Mappings({\n        @Mapping(target = \"label\", defaultExpression = \"java(toDisplayName(\\\"-\\\"))\")\n    })\n"
                           "    ItemDto toLabel(Item item);\n\n"
                           "    default String toDisplayName(String name) {\n        return name.trim();\n    }\n}\n",
        "Item.java": "public class Item {\n    public String getName() {\n        return \"\";\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([d]))
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("ItemMapper.toDto", "ItemMapper.toDisplayName"), ("ItemMapper.toDto", "Item.getName"),
            ("ItemMapper.toLabel", "ItemMapper.toDisplayName")}
    if want - calls:
        return f"expression call(s) not read: {sorted(want - calls)}; got {sorted(calls)}"
    if "ItemMapper.toDisplayName" in analyze.find_orphans(nodes, edges):
        return "a helper used only in a MapStruct expression is still dead"


def r65_cast_receivers():
    """real repo: `((UserSecurity) userDetails).getPlantIds()` was dropped as untyped, so
    `getPlantIds` was dead -- a cast states the receiver's type as plainly as a declaration."""
    d = _tree({
        "UserSecurity.java": "public class UserSecurity {\n    public long getPlantIds() {\n        return 1;\n    }\n}\n",
        "JwtAuthFilter.java": "public class JwtAuthFilter {\n    public void filter(Object userDetails) {\n"
                              "        long ids = ((UserSecurity) userDetails).getPlantIds();\n    }\n}\n",
        "Session.cs": "public class Session {\n    public string UserId() {\n        return \"\";\n    }\n}\n",
        "Filter.cs": "public class Filter {\n    public void Run(object user) {\n"
                     "        var id = ((Session) user).UserId();\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("JwtAuthFilter.filter", "UserSecurity.getPlantIds"), ("Filter.Run", "Session.UserId")}
    if want - calls:
        return f"call(s) through a cast not resolved: {sorted(want - calls)}; got {sorted(calls)}"


def r66_function_chosen_into_a_variable():
    """real repo: `const save = formData.userId ? updateUser : createUser; save(data)` left both
    functions dead. Both branches are written in the source and one of them runs, exactly as
    `if (id) updateUser() else createUser()` would -- which already drew both links."""
    d = _tree({
        "src/users.ts": "export async function createUser(u: string) {\n  return u;\n}\n"
                        "export async function updateUser(u: string) {\n  return u;\n}\n",
        "src/misc.ts": "export function onDone() {\n  return 1;\n}\n",
        "src/UserForm.tsx": 'import { createUser, updateUser } from "./users";\n\n'
                            "export function UserForm({ userId, onDone }: P) {\n  const submit = async () => {\n"
                            "    const save = userId ? updateUser : createUser;\n    await save(userId);\n"
                            "    const done = onDone;\n    done();\n  };\n  return <form onSubmit={submit} />;\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("UserForm", "createUser"), ("UserForm", "updateUser")}
    if want - calls:
        return f"branch(es) of a chosen function not linked: {sorted(want - calls)}; got {sorted(calls)}"
    if ("UserForm", "onDone") in {(s, t) for s, t, _ in edges}:
        return "a local holding a prop was linked to another file's function of the same name"


def r67_passed_functions():
    """real repo: `createApiInstance(getUserApiBaseUrl)`, `rows.map(formatDate)` and i18n tag
    functions handed to `t.rich(key, { b: tag })` were dead -- nothing calls them from the
    graph, the code they are handed to does. A `passes` link, or `entry: module` at top level."""
    d = _tree({
        "src/config.ts": "export function getUserApiBaseUrl() {\n  return \"/api\";\n}\n"
                         "export function createApiInstance(base: () => string) {\n  return base;\n}\n",
        "src/api.ts": 'import { createApiInstance, getUserApiBaseUrl } from "./config";\n\n'
                      "export const api = createApiInstance(getUserApiBaseUrl);\n",
        "src/format.ts": "export function formatDate(d: string) {\n  return d;\n}\n"
                         "export function tag(chunks: string) {\n  return chunks;\n}\n",
        "src/Upload.tsx": 'import { formatDate, tag } from "./format";\n\n'
                          "function row() {\n  return 1;\n}\n\n"
                          "export function Upload({ rows, t }: P) {\n  const row = rows[0];\n"
                          "  return <b title={formatDate}>{t.rich(\"k\", { b: tag, row })}</b>;\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = _written(*build_flow.analyze([d]))
    passes = {(s, t) for s, t, k in edges if k == "passes"}
    want = {("Upload", "formatDate"), ("Upload", "tag")}
    if want - passes:
        return f"passed function(s) not linked: {sorted(want - passes)}; got {sorted(edges)}"
    if ("Upload", "row") in passes:
        return "a local `row` was linked to the module function `row`"
    if nodes.get("getUserApiBaseUrl", {}).get("entry") != "module":
        return f"a function handed over at module load is not `entry: module`: {nodes.get('getUserApiBaseUrl')}"
    dead = set(analyze.find_orphans(nodes, edges))
    if {"formatDate", "tag", "getUserApiBaseUrl"} & dead:
        return f"a passed function is still dead: {sorted(dead)}"
    if any("formatDate" in (n.get("calls") or []) for n in nodes.values()):
        return "a passes link was counted as a call"


def r68_objects_the_source_settles():
    """real repo: 19 service functions were called as `api.fetchX()` on an `api` whose type is
    not annotated. Three shapes settle it: `api` is a renamed or default import of an object, a
    `const` choosing between objects, or a function's result whose every return is one object
    literal naming the functions (`const api = useSetdatApi()`)."""
    d = _tree({
        "src/setdat/service.ts": "export async function fetchSetdatProjectList() {\n  return [];\n}\n"
                                 "export async function fetchSetdatDetail(id: string) {\n  return id;\n}\n"
                                 "export async function fetchNg() {\n  return [];\n}\n"
                                 "const setdatApi = { fetchSetdatProjectList, fetchSetdatDetail };\n"
                                 "export default setdatApi;\n"
                                 "export const ngApi = { fetchNg, fetchSetdatProjectList };\n",
        "src/setdat/useSetdatApi.ts": 'import { fetchSetdatDetail, fetchSetdatProjectList } from "./service";\n\n'
                                      "export function useSetdatApi() {\n"
                                      "  return { fetchSetdatDetail, fetchSetdatProjectList };\n}\n",
        "src/pages/List.tsx": 'import api from "../setdat/service";\n\n'
                              "export function List() {\n  api.fetchSetdatProjectList();\n  return null;\n}\n",
        "src/pages/Renamed.tsx": 'import { ngApi as api } from "../setdat/service";\n\n'
                                 "export function Renamed() {\n  api.fetchNg();\n  return null;\n}\n",
        "src/pages/Detail.tsx": 'import { useSetdatApi } from "../setdat/useSetdatApi";\n\n'
                                "export function Detail({ id }: P) {\n  const api = useSetdatApi();\n"
                                "  api.fetchSetdatDetail(id);\n  return null;\n}\n",
        "src/pages/Pick.tsx": 'import setdatApi, { ngApi } from "../setdat/service";\n\n'
                              "export function Pick({ ng }: P) {\n  const api = ng ? ngApi : setdatApi;\n"
                              "  api.fetchSetdatProjectList();\n  return null;\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("List", "fetchSetdatProjectList"), ("Renamed", "fetchNg"),
            ("Detail", "fetchSetdatDetail"), ("Pick", "fetchSetdatProjectList")}
    if want - calls:
        return f"call(s) through an object not resolved: {sorted(want - calls)}; got {sorted(calls)}"


def r69_data_folders_are_source():
    """real repo: `data` was in SKIP_DIRS (meant for this skill's own output folder), so a Next.js
    route segment `app/[projectId]/data/[type]/` -- six files -- was in neither map, and four
    service functions only those pages call were dead."""
    d = _tree({
        "src/services/master.ts": "export async function exportAllMasterData() {\n  return 1;\n}\n",
        "src/app/[projectId]/data/[type]/MasterDataPreview.tsx":
            'import { exportAllMasterData } from "../../../../services/master";\n\n'
            "export function MasterDataPreview() {\n  exportAllMasterData();\n  return <div />;\n}\n"})
    if "data" in taxonomy.SKIP_DIRS:
        return "`data` is in taxonomy.SKIP_DIRS again"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    if ("MasterDataPreview", "exportAllMasterData") not in {(s, t) for s, t, k in edges if k == "calls"}:
        return f"a page under a `data/` folder was not read: {sorted(edges)}"


def r70_wrapped_components():
    """real repo: `const Button = forwardRef<...>((props, ref) => ...)` (and `RenderText` the same)
    was in neither map -- only a function declared as a function was read -- so 172 `<Button />`
    uses in 51 files drew nothing. `forwardRef` and `memo` return the component they wrap."""
    d = _tree({
        "src/ui/Button.tsx": 'import { forwardRef } from "react";\n\n'
                             "export const Button = forwardRef<HTMLButtonElement, P>((props, ref) => {\n"
                             "  return <button ref={ref} {...props} />;\n});\n",
        "src/ui/RenderText.tsx": 'import React, { memo } from "react";\n\n'
                                 "function Plain({ text }: P) {\n  return <span>{text}</span>;\n}\n\n"
                                 "export const RenderText = memo(React.forwardRef(function RenderText(props: P, ref) {\n"
                                 "  return <Plain text='x' />;\n}));\n",
        "src/pages/Page.tsx": 'import { Button } from "../ui/Button";\nimport { RenderText } from "../ui/RenderText";\n\n'
                              "export function Page() {\n  return <div><Button /><RenderText /></div>;\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        nodes, edges = build_flow.analyze([d])
    for name in ("Button", "RenderText"):
        if nodes.get(name, {}).get("kind") != "component":
            return f"`{name}` wrapped in forwardRef/memo is not a component node: {nodes.get(name)}"
    renders = {(s, t) for s, t, k in edges if k == "renders"}
    want = {("Page", "Button"), ("Page", "RenderText"), ("RenderText", "Plain")}
    if want - renders:
        return f"render link(s) to a wrapped component missing: {sorted(want - renders)}; got {sorted(renders)}"


def r71_pattern_variables():
    """real repo: `if (auth instanceof UserSecurity userSecurity) userSecurity.getUserId()` left
    `getUserId` dead -- a pattern variable states its type as plainly as a declaration does."""
    d = _tree({
        "UserSecurity.java": "public class UserSecurity {\n    public long getUserId() {\n        return 1;\n    }\n"
                             "    public long getPlantId() {\n        return 2;\n    }\n}\n",
        "UserService.java": "public class UserService {\n    public long current(Object principal) {\n"
                            "        if (principal instanceof UserSecurity userSecurity) {\n"
                            "            return userSecurity.getUserId();\n        }\n"
                            "        return switch (principal) {\n            case UserSecurity s -> s.getPlantId();\n"
                            "            default -> 0L;\n        };\n    }\n}\n",
        "Session.cs": "public class Session {\n    public string UserId() {\n        return \"\";\n    }\n}\n",
        "Filter.cs": "public class Filter {\n    public void Run(object user) {\n"
                     "        if (user is Session s) {\n            s.UserId();\n        }\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("UserService.current", "UserSecurity.getUserId"), ("UserService.current", "UserSecurity.getPlantId"),
            ("Filter.Run", "Session.UserId")}
    if want - calls:
        return f"call(s) through a pattern variable not resolved: {sorted(want - calls)}; got {sorted(calls)}"


def r72_typed_hook_fields():
    """real repo: `const { api } = useSetdatVariant()`, where the context value's type says
    `api: SetdatApi` and `type SetdatApi = typeof setdatService` -- 19 service functions dead,
    though every step is written in the source. Followed: the hook's return type (or the
    `createContext<T>` it returns), that type's field, and the object `typeof` names."""
    d = _tree({
        "src/services/setdatService.ts": "export async function fetchSetdatProjectList() {\n  return [];\n}\n"
                                         "export async function fetchSetdatDetail(id: string) {\n  return id;\n}\n",
        "src/services/ngService.ts": "export async function fetchNg() {\n  return [];\n}\n"
                                     "export const ngService = { fetchNg };\n",
        "src/context/SetdatVariantContext.tsx":
            'import { createContext, useContext } from "react";\n'
            'import * as setdatService from "../services/setdatService";\n'
            'import { ngService } from "../services/ngService";\n\n'
            "export interface SetdatVariantValue {\n  api: SetdatApi;\n  ng: typeof ngService;\n  label: string;\n}\n\n"
            "const SetdatVariantContext = createContext<SetdatVariantValue | null>(null);\n\n"
            "export function useSetdatVariant() {\n  const ctx = useContext(SetdatVariantContext);\n"
            '  if (!ctx) throw new Error("outside provider");\n  return ctx;\n}\n\n'
            "type SetdatApi = typeof setdatService;\n",
        "src/context/useVariant.ts": 'import type { SetdatVariantValue } from "./SetdatVariantContext";\n\n'
                                     "export function useVariant(): SetdatVariantValue {\n  return window.variant;\n}\n",
        "src/pages/Projects.tsx": 'import { useSetdatVariant } from "../context/SetdatVariantContext";\n\n'
                                  "export function Projects() {\n  const { api, label } = useSetdatVariant();\n"
                                  "  useEffect(() => {\n    api.fetchSetdatProjectList();\n  }, [api]);\n"
                                  "  return <b>{label}</b>;\n}\n",
        "src/pages/Detail.tsx": 'import { useVariant } from "../context/useVariant";\n\n'
                                "export function Detail({ id }: P) {\n  const { api: svc, ng } = useVariant();\n"
                                "  svc.fetchSetdatDetail(id);\n  ng.fetchNg();\n  return null;\n}\n",
        "src/pages/useOther.ts": "export function useOther() {\n  return window.other;\n}\n",
        "src/pages/Untyped.tsx": 'import { useOther } from "./useOther";\n\n'
                                 "export function Untyped() {\n  const { api } = useOther();\n  api.fetchNg();\n"
                                 "  return null;\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, edges = build_flow.analyze([d])
    calls = {(s, t) for s, t, k in edges if k == "calls"}
    want = {("Projects", "fetchSetdatProjectList"), ("Detail", "fetchSetdatDetail"), ("Detail", "fetchNg")}
    if want - calls:
        return f"call(s) through a typed hook field not resolved: {sorted(want - calls)}; got {sorted(calls)}"
    if ("Untyped", "fetchNg") in calls:
        return "a field of an untyped hook's result was linked by name"


def r73_type_refs_are_references():
    """real repo: 22 classes were "referenced by nothing" while their names sat in the
    signatures. The structure map read bases, field types, parameter types and resolved call
    receivers only, so a return type, a generic argument, a local's type, `X.class` and the
    class a constant is read from produced nothing -- all of which an IDE counts as a usage."""
    one = lambda name: f"public class {name} {{\n    public int size() {{\n        return 1;\n    }}\n}}\n"
    nodes, edges = _structure(_tree({
        "api/UserResponse.java": one("UserResponse"),
        "api/PaginationResponse.java": one("PaginationResponse"),
        "api/GlobalResponse.java": one("GlobalResponse"),
        "api/IssdResultId.java": one("IssdResultId"),
        "api/TUploadDetailTestPattern.java": one("TUploadDetailTestPattern"),
        "api/SocketConstant.java": "public class SocketConstant {\n"
                                   "    public static final int INSPECTION_ID_LENGTH = 8;\n}\n",
        "api/UserController.java": "@IdClass(IssdResultId.class)\npublic class UserController {\n"
                                   "    private static final int LEN = SocketConstant.INSPECTION_ID_LENGTH;\n\n"
                                   "    public GlobalResponse<PaginationResponse<UserResponse>> list() {\n"
                                   "        UserResponse row = build();\n        return null;\n    }\n\n"
                                   "    private UserResponse build() {\n        return null;\n    }\n}\n",
        "api/PatternRepo.java": "public interface PatternRepo "
                                "extends JpaRepository<TUploadDetailTestPattern, UUID> {\n}\n"}))
    refs = {(s, t) for s, t, kind in edges if kind == "references"}
    want = {("UserController", "GlobalResponse"),        # return type, and its two generic arguments
            ("UserController", "PaginationResponse"), ("UserController", "UserResponse"),
            ("UserController", "SocketConstant"),        # a constant read off a class
            ("UserController", "IssdResultId"),          # `IssdResultId.class` in an annotation
            ("PatternRepo", "TUploadDetailTestPattern")}
    if want - refs:
        return f"reference(s) a signature states not drawn: {sorted(want - refs)}; got {sorted(refs)}"
    if ("UserController", "PatternRepo") in refs:
        return "a reference was drawn to a class the file never names"
    dead = set(analyze.find_orphans(nodes, edges))
    if {"UserResponse", "GlobalResponse", "SocketConstant"} & dead:
        return f"a class named in a signature is still dead: {sorted(dead)}"


def r74_extended_classes_are_used():
    """real repo: `Auditable` had 12 incoming `extends` links and was still reported dead.
    `find_orphans` walks inheritance backwards (so an implementation is reached through its
    declaration), which only ever marks the child -- but `class Audited extends Auditable`
    names the base in its own source, which is a use."""
    nodes, edges = _structure(_tree({
        "m/Auditable.java": "public abstract class Auditable {\n    protected String createdBy;\n}\n",
        "m/Audited.java": "public class Audited extends Auditable {\n    public int id() {\n        return 1;\n    }\n}\n",
        "m/Tagged.java": "public class Tagged extends Auditable {\n    public int tag() {\n        return 2;\n    }\n}\n",
        "m/Loner.java": "public class Loner {\n    public void x() {\n    }\n}\n"}))
    orphans = set(analyze.find_orphans(nodes, edges))
    if "Auditable" in orphans:
        return f"a base class two classes extend is reported dead: {sorted(orphans)}"
    if "Loner" not in orphans:
        return f"a class nothing names or extends is no longer dead: {sorted(orphans)}"
    if not [1 for s, t, kind in edges if (s, t, kind) == ("Audited", "Auditable", "extends")]:
        return f"the extends link itself is gone: {edges}"


def r75_structure_entry_points():
    """real repo: 11 framework-built classes were reported dead -- structure nodes carried no
    `entry` at all, though `find_orphans` checks for one. Narrow on purpose: `@Component` /
    `@Service` alone is not an entry, or a Spring app would report no dead classes at all."""
    nodes, edges = _structure(_tree({
        "app/App.java": "@SpringBootApplication\npublic class App {\n"
                        "    public static void main(String[] args) {\n    }\n}\n",
        "app/Beans.java": "@Configuration\npublic class Beans {\n"
                          "    @Bean\n    public String clock() {\n        return \"\";\n    }\n}\n",
        "app/Cron.java": "@Component\npublic class Cron {\n"
                         "    @Scheduled(cron = \"0 0 * * * *\")\n    public void run() {\n    }\n}\n",
        "app/Idle.java": "@Service\npublic class Idle {\n    public void nothing() {\n    }\n}\n"}))
    orphans = set(analyze.find_orphans(nodes, edges))
    if {"App", "Beans", "Cron"} & orphans:
        return f"a framework-built class is reported dead: {sorted(orphans)}"
    if "Idle" not in orphans:
        return f"`@Service` alone spared a class nothing uses: {sorted(orphans)}"
    if nodes["Cron"].get("entry") != "@Scheduled" or nodes["Beans"].get("entry") != "@Configuration":
        return f"entry not written onto the structure node: {nodes['Cron']}, {nodes['Beans']}"


def r76_type_position_imports():
    """real repo: `import * as setdatService` used only as `typeof setdatService` counted as
    nothing, so that module had no incoming reference. A type position is a use -- it is why
    the IDE does not grey the import out."""
    nodes, edges = _structure(_tree({
        "src/services/setdatService.ts": "export async function fetchSetdatProjectList() {\n  return [];\n}\n",
        "src/context/Variant.ts": 'import * as setdatService from "../services/setdatService";\n\n'
                                  "export type SetdatApi = typeof setdatService;\n\n"
                                  "export function useVariant() {\n  return null as unknown as SetdatApi;\n}\n"}))
    service = {nid for nid, n in nodes.items() if n.get("source", "").endswith("setdatService.ts")}
    if not service:
        return f"no node for the service module: {sorted(nodes)}"
    into = {t for _s, t, _k in edges} & service
    if not into:
        return f"the namespace import used in a type position drew no reference: {edges}"
    if service & set(analyze.find_orphans(nodes, edges)):
        return "the module reached only through a type position is still dead"


def r77_same_file_references():
    """real repo: `AdminLayout` calls `getMainContentMargin`, defined in the same `layout.tsx`,
    and not one of 385 references into a module node was same-file -- JS/TS and Python resolved
    references from the import list only, so a name a file defines itself pointed at nothing.
    Java already resolved it through `class_locator` (asserted here so it stays that way)."""
    nodes, edges = _structure(_tree({
        "app/layout.tsx": "export function getMainContentMargin(open: boolean) {\n  return open ? 1 : 0;\n}\n\n"
                          "export default function AdminLayout({ open }: P) {\n"
                          "  const m = getMainContentMargin(open);\n"
                          "  return <div style={{ margin: m }} />;\n}\n",
        "app/util.py": "def helper():\n    return 1\n\n\nclass Page:\n"
                       "    def render(self):\n        return helper()\n",
        "app/Pair.java": "class Row {\n    public int id() {\n        return 1;\n    }\n}\n\n"
                         "class Table {\n    private Row row;\n\n    public int first() {\n"
                         "        return row.id();\n    }\n}\n"}))
    refs = {(s, t) for s, t, kind in edges if kind == "references"}
    want = {("AdminLayout", "LayoutModule"), ("Page", "UtilModule"), ("Table", "Row")}
    if want - refs:
        return f"same-file reference(s) not drawn: {sorted(want - refs)}; got {sorted(refs)}"
    if any(s == t for s, t, _ in edges):
        return f"a node references itself: {edges}"
    dead = set(analyze.find_orphans(nodes, edges))
    if {"LayoutModule", "UtilModule", "Row"} & dead:
        return f"a node used only from its own file is still dead: {sorted(dead)}"


def r78_layer_words_end_where_the_word_ends():
    """real repo: `repo` matched `PnoDataReportMail` and `store` matched `StoredFileDto`, so 7
    classes were `repository`; and because that rule runs before `model`, a `*Dto` lost its
    layer -- which fabricated the report's only layer violation (service -> service scored
    repository -> service), 4 grade points on a false positive."""
    want = {"PnoDataReportMail": "unknown", "SetdatNgReportDto": "model", "StoredFileDto": "model",
            # ...and the words themselves must still match, wherever a name really ends on them.
            "EventStore": "repository", "OrderRepository": "repository", "order_repository": "repository",
            "UserDao": "repository", "OrderMapper": "repository", "PnoDataBatchService": "service"}
    got = {name: taxonomy.infer_layer(name) for name in want}
    wrong = {k: (got[k], v) for k, v in want.items() if got[k] != v}
    if wrong:
        return f"layer(s) wrong (got, want): {wrong}"


def r79_layer_from_the_folder():
    """real repo: 189 of 665 structure nodes were `unknown` -- the layer was read from the class
    name alone, though the package states it (`service/pnodata/`, `response/masterdata/`,
    `properties/`). A fallback only: an annotation or the name still wins, an exact folder name
    only (a whole application under `api/` is not six hundred clients), and a folder that names no
    layer stays unknown."""
    want = [
        ("api/service/pnodata/PnoDataJob.java", "PnoDataJob", (), "service"),
        ("api/response/masterdata/MasterFileInfo.java", "MasterFileInfo", (), "model"),
        ("api/repository/projection/PlantRow.java", "PlantRow", (), "repository"),
        ("api/properties/BatchTuning.java", "BatchTuning", (), "config"),
        ("api/util/Helpers.java", "Helpers", (), "unknown"),            # no layer word: stay honest
        ("api/exception/NotFound.java", "NotFound", (), "unknown"),
        ("app/api/users/handler.ts", "handler", (), "unknown"),         # `api/` is not a client folder
        ("api/util/AuditLog.java", "AuditLog", ("Service",), "service"),           # annotation wins
        ("api/service/OrderRepository.java", "OrderRepository", (), "repository"),  # the name wins
    ]
    wrong = {path: (taxonomy.infer_layer(name, decos, (), path), layer)
             for path, name, decos, layer in want
             if taxonomy.infer_layer(name, decos, (), path) != layer}
    if wrong:
        return f"layer(s) wrong (got, want): {wrong}"
    # ...and the path has to reach `infer_layer` from the builders, which is what broke before.
    nodes, _edges = _structure(_tree({
        "api/service/pnodata/PnoDataJob.java": "public class PnoDataJob {\n"
                                               "    public void run() {\n    }\n}\n",
        "api/util/Helpers.java": "public class Helpers {\n    public int one() {\n        return 1;\n    }\n}\n"}))
    got = {nid: n.get("layer") for nid, n in nodes.items() if nid in ("PnoDataJob", "Helpers")}
    if got != {"PnoDataJob": "service", "Helpers": "unknown"}:
        return f"the builder did not pass the path to infer_layer: {got}"


def r80_one_doc_rule():
    """Each producer answered "what documents this node" differently. JS/TS refused a comment
    that was not on the line directly above and kept one line of the *nearest* block, so a doc
    written as a run of `//` was published as its last line -- three of the sample's five JS/TS
    docs were sentence fragments. Python was truncated at its first line. `langs_extract`'s rule
    is now the only rule (`core/doc_text.py`): the block above, blank lines invisible, stop at
    code, consecutive blocks joined, everything on one line."""
    d = _tree({
        "run.ts": (
            "// Reads one page of versions,\n"
            "// filtered by the screen's criteria.\n"
            "export function fetchList() { return 1; }\n"
            "\n"
            "// Doc with a blank-line gap.\n"
            "\n"
            "export function gapped() { return 2; }\n"
            "\n"
            "// Not this one.\n"
            "const sep = 0;\n"
            "export function separated() { return sep; }\n"),
        "Svc.java": (
            "public class Svc {\n"
            "    /** Reads one page,\n"
            "     * filtered by the criteria. */\n"
            "\n"
            "    public int fetch() { return 1; }\n"
            "\n"
            "    /** Not this one. */\n"
            "    private int sep = 0;\n"
            "    public int separated() { return sep; }\n"
            "}\n"),
        "svc.py": (
            '"""Module doc.\n'
            '\n'
            'Second paragraph.\n'
            '"""\n'
            '\n'
            '\n'
            'def fetch_list():\n'
            '    """Reads one page,\n'
            '\n'
            '    filtered by the criteria.\n'
            '    """\n'
            '    return 1\n'
            '\n'
            '\n'
            '# a plain comment, which is not documentation in Python\n'
            'def commented():\n'
            '    return 2\n'),
    })
    methods, _ = _flow(d)
    want = {
        # a run of `//` is one doc, joined -- not its last line
        "fetchList": "Reads one page of versions, filtered by the screen's criteria.",
        # a blank line no longer hides a JS/TS doc, exactly as in the Java family
        "gapped": "Doc with a blank-line gap.",
        # ...but code between still stops the walk, in both
        "separated": "",
        "Svc.fetch": "Reads one page, filtered by the criteria.",
        "Svc.separated": "",
        # a Python docstring is joined whole, not cut at its first line
        "fetch_list": "Reads one page, filtered by the criteria.",
        # and a `#` comment above a def is still not a docstring
        "commented": "",
    }
    got = {nid: (methods.get(nid) or {}).get("doc", "<missing node>") for nid in want}
    if got != want:
        return f"doc(s) wrong (got, want): { {k: (got[k], want[k]) for k in want if got[k] != want[k]} }"
    # The structure map reads the same rule, and its module summary is one line too.
    nodes, _edges = _structure(d)
    mod = next((n for n in nodes.values() if n.get("kind") == "module" and n.get("lang") == "py"), None)
    if mod is None or mod.get("doc") != "Module doc. Second paragraph.":
        return f"module summary not joined: {mod and mod.get('doc')!r}"


def r81_call_sites():
    """A node calling five others could not say which call is written first, or that one runs
    only inside an `if`: a call link carried no call site. It carries `line`, and `loop` /
    `cond` where earned. Only a body counts -- the design first pinned
    `handleOrderEvents -> EventService.Events` as a loop, but a `range` expression runs once --
    and a call is `cond` only when *every* site is in a branch."""
    d = _tree({
        "svc.py": "def helper():\n    return 1\n\n\ndef other():\n    return 2\n\n\n"
                  "def load():\n    return []\n\n\ndef both():\n    return 3\n\n\n"
                  "def run(xs, a):\n    for x in load():\n        helper()\n"
                  "    if a:\n        other()\n        both()\n    both()\n",
        "a.ts": "export function items(): number[] {\n  return [];\n}\n"
                "export function save(x: number) {\n  return x;\n}\n"
                "export function sync() {\n  for (const x of items()) {\n    save(x);\n  }\n}\n",
        "Store.java": "public class Store {\n    public boolean more() { return false; }\n"
                      "    public void take() {}\n    public void flush() {}\n}\n",
        "Worker.java": "public class Worker {\n    private Store store;\n"
                       "    public void drain(boolean ok) {\n        while (store.more()) {\n"
                       "            store.take();\n        }\n        if (ok) {\n"
                       "            store.flush();\n        } else {\n            store.take();\n"
                       "        }\n    }\n}\n",
        "worker.go": "package w\n\ntype Svc struct{}\n\n"
                     "func (s *Svc) Events() []string { return nil }\n"
                     "func (s *Svc) Record() {}\n\n"
                     "func Drive(svc *Svc, n int) {\n\tfor _, e := range svc.Events() {\n\t\t_ = e\n\t}\n"
                     "\tfor i := 0; i < n; i++ {\n\t\tsvc.Record()\n\t}\n}\n",
        "Job.kt": "class Store {\n    fun load(): List<Int> = listOf()\n    fun save(x: Int) {}\n}\n\n"
                  "class Job(private val store: Store) {\n    fun run() {\n"
                  "        for (x in store.load()) {\n            store.save(x)\n        }\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = build_flow.analyze([d])
    path = os.path.join(tempfile.mkdtemp(), "flow_graph.json")
    build_flow.write_graph(methods, edges, path)
    with open(path, encoding="utf-8") as fh:
        links = {(e["source"], e["target"]): e for e in json.load(fh)["edges"] if e["type"] == "calls"}
    # (source, target) -> (line, loop, cond), as the written file must hold them
    want = {
        ("run", "load"): (18, False, False),          # a `for` iterable runs once
        ("run", "helper"): (19, True, False),
        ("run", "other"): (21, False, True),
        ("run", "both"): (22, False, False),          # one site in the `if`, one not: first line, no cond
        ("sync", "items"): (8, False, False),
        ("sync", "save"): (9, True, False),
        ("Worker.drain", "Store.more"): (4, True, False),   # a `while` condition repeats
        ("Worker.drain", "Store.take"): (5, True, False),   # in the loop, and in the `else`: not all cond
        ("Worker.drain", "Store.flush"): (8, False, True),
        ("Drive", "Svc.Events"): (9, False, False),     # `range svc.Events()`: once
        ("Drive", "Svc.Record"): (13, True, False),
        ("Job.run", "Store.load"): (8, False, False),  # Kotlin leaves both unnamed: only the block is a body
        ("Job.run", "Store.save"): (9, True, False),
    }
    missing = sorted(k for k in want if k not in links)
    if missing:
        return f"call link(s) missing: {missing}; got {sorted(links)}"
    got = {k: (links[k].get("line"), bool(links[k].get("loop")), bool(links[k].get("cond"))) for k in want}
    wrong = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    if wrong:
        return f"call site(s) wrong (got, want): {wrong}"
    if any(set(e) - {"source", "target", "type", "line", "loop", "cond", "arms"} for e in links.values()):
        return "a call link carries a key other than its call site"
    if any(e.get("loop") is False or e.get("cond") is False for e in links.values()):
        return "a false `loop` / `cond` was written instead of left out"


def r82_either_or_arms():
    """Badges 3 and 4 could be an `if` and its `else` -- exactly one runs -- or two calls in one
    `if`, and `cond` could not say which. A call site records `arms`: each either/or branch it is
    on one side of, outermost first, as `"<line>:<col>/<arm>"`. Only where the sides exclude each
    other: an else-if chain is one branch, a ternary chain too, a `match`/`when` and a `case X ->`
    switch are, a `case X:` switch (fall-through), a Go `fallthrough` switch and a `catch` are
    not. A call made on two sides keeps only the sides every site shares."""
    d = _tree({
        "svc.py": "def a():\n    return 1\n\n\ndef b():\n    return 2\n\n\ndef c():\n    return 3\n\n\n"
                  "def d():\n    return 4\n\n\ndef e():\n    return 5\n\n\n"
                  "def run(x, y):\n    a()\n    if x:\n        b()\n        if y:\n            c()\n"
                  "    elif x == 2:\n        d()\n    else:\n        e()\n        b()\n",
        "Box.java": "public class Box {\n    public void open() {}\n    public void shut() {}\n"
                    "    public void peek() {}\n    public void poke() {}\n    public void lift() {}\n"
                    "    public void drop() {}\n}\n",
        "Crate.java": "public class Crate {\n    private Box box;\n    public void act(int k) {\n"
                      "        switch (k) {\n            case 1 -> box.open();\n            default -> box.shut();\n"
                      "        }\n        switch (k) {\n            case 1: box.peek();\n            case 2: box.poke();\n"
                      "        }\n        try {\n            box.lift();\n        } catch (Exception ex) {\n"
                      "            box.drop();\n        }\n    }\n}\n",
        "choose.go": "package w\n\ntype Svc struct{}\n\nfunc (s *Svc) One() {}\nfunc (s *Svc) Two() {}\n"
                     "func (s *Svc) Three() {}\n\nfunc Choose(svc *Svc, n int) {\n\tif n > 0 {\n\t\tsvc.One()\n"
                     "\t} else if n < 0 {\n\t\tsvc.Two()\n\t}\n\tswitch n {\n\tcase 1:\n\t\tsvc.Three()\n"
                     "\t\tfallthrough\n\tcase 2:\n\t}\n}\n",
        "pick.ts": "export function hi(): number {\n  return 1;\n}\nexport function lo(): number {\n  return 0;\n}\n"
                   "export function mid(): number {\n  return 2;\n}\nexport function pick(n: number) {\n"
                   "  return n > 0 ? hi() : n < 0 ? lo() : mid();\n}\n",
        "Lamp.kt": "class Lamp {\n    fun on() {}\n    fun off() {}\n}\n\nclass Panel(private val lamp: Lamp) {\n"
                   "    fun flip(k: Int) {\n        when (k) {\n            1 -> lamp.on()\n            else -> lamp.off()\n"
                   "        }\n    }\n}\n"})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        methods, edges = build_flow.analyze([d])
    path = os.path.join(tempfile.mkdtemp(), "flow_graph.json")
    build_flow.write_graph(methods, edges, path)
    with open(path, encoding="utf-8") as fh:
        links = {(e["source"], e["target"]): e for e in json.load(fh)["edges"] if e["type"] == "calls"}
    # (source, target) -> (arms, cond)
    want = {
        ("run", "a"): (None, False),
        ("run", "b"): (None, True),                          # the `if` side and the `else` side: neither
        ("run", "c"): (["23:5/0", "25:9/0"], True),          # outer branch first, then the inner one
        ("run", "d"): (["23:5/1"], True),                    # `elif` is the chain's second side
        ("run", "e"): (["23:5/2"], True),
        ("Crate.act", "Box.open"): (["4:9/0"], True),        # `case 1 ->` cannot fall through
        ("Crate.act", "Box.shut"): (["4:9/1"], True),
        ("Crate.act", "Box.peek"): (None, True),             # `case 1:` can
        ("Crate.act", "Box.poke"): (None, True),
        ("Crate.act", "Box.lift"): (None, False),
        ("Crate.act", "Box.drop"): (None, True),             # a catch runs after its try: not either/or
        ("Choose", "Svc.One"): (["10:2/0"], True),           # `else if` nested in `alternative`: one chain
        ("Choose", "Svc.Two"): (["10:2/1"], True),
        ("Choose", "Svc.Three"): (None, True),               # this switch says `fallthrough`
        ("pick", "hi"): (["11:10/0"], True),                 # a ternary chain is one branch too
        ("pick", "lo"): (["11:10/1"], True),
        ("pick", "mid"): (["11:10/2"], True),
        ("Panel.flip", "Lamp.on"): (["8:9/0"], True),        # the `when` keyword is not an arm
        ("Panel.flip", "Lamp.off"): (["8:9/1"], True),
    }
    missing = sorted(k for k in want if k not in links)
    if missing:
        return f"call link(s) missing: {missing}; got {sorted(links)}"
    got = {k: (links[k].get("arms"), bool(links[k].get("cond"))) for k in want}
    wrong = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    if wrong:
        return f"arms wrong (got, want): {wrong}"


def r83_coupling_has_a_direction():
    """Counting callers alone could not tell a shared helper from a tangle. `GlobalResponse.success`
    (40 callers, calls nothing) scored exactly as badly as a method called from everywhere that also
    calls everything, so on a real repository 42 of 46 "high coupling" hubs were plain helpers or
    plain coordinators and the -12 deduction was a false alarm. Robert Martin's instability
    I = fan_out / (fan_in + fan_out) splits them: only a node high in *both* directions is graded."""
    nodes, edges = {}, []

    def node(nid):
        nodes[nid] = {"id": nid, "kind": "method", "layer": "service"}
        return nid

    # A shared helper: 40 callers, calls nothing.  I = 0.0
    node("Resp.success")
    for i in range(40):
        edges.append((node(f"caller{i}"), "Resp.success", "calls"))
    # A coordinator: calls 15 things, nothing calls it.  I = 1.0
    node("Panel.register")
    for i in range(15):
        edges.append(("Panel.register", node(f"step{i}"), "calls"))
    # The real thing: 6 in, 6 out.
    node("Tangle.run")
    for i in range(6):
        edges.append((node(f"up{i}"), "Tangle.run", "calls"))
        edges.append(("Tangle.run", node(f"down{i}"), "calls"))

    hubs = {h["node"] for h in analyze.find_hubs(nodes, edges)}
    helpers = {h["node"] for h in analyze.find_shared_helpers(nodes, edges)}
    coords = {h["node"] for h in analyze.find_coordinators(nodes, edges)}
    if hubs != {"Tangle.run"}:
        return f"hubs should be exactly the both-directions node, got {sorted(hubs)}"
    if "Resp.success" not in helpers or "Panel.register" not in coords:
        return (f"helper/coordinator not classified: helpers={sorted(helpers)},"
                f" coordinators={sorted(coords)}")
    if helpers & hubs or coords & hubs:
        return "a helper or a coordinator was also graded as a hub"

    # ...and neither costs a point. A graph of only helpers and coordinators deducts 0.
    calm = {k: v for k, v in nodes.items() if not k.startswith(("Tangle", "up", "down"))}
    calm_edges = [e for e in edges if not (e[0].startswith("Tangle") or e[1].startswith("Tangle"))]
    ded = analyze.health(len(calm), [], [], [], analyze.find_hubs(calm, calm_edges), [],
                         None, analyze.find_wrong_way_deps(calm, calm_edges))["deductions"]
    if ded["high_coupling"] or ded["wrong_way_deps"]:
        return f"a graph of only helpers and coordinators was penalised: {ded}"

    # Rule 4: a stable node calling an unstable one points the wrong way; the reverse does not.
    bad = analyze.find_wrong_way_deps(nodes, edges + [("Resp.success", "Panel.register", "calls")])
    if not any(v["source"] == "Resp.success" and v["target"] == "Panel.register" for v in bad):
        return "a stable node calling an unstable one was not reported as wrong-way"
    good = analyze.find_wrong_way_deps(nodes, edges + [("Panel.register", "Resp.success", "calls")])
    if any(v["source"] == "Panel.register" for v in good):
        return "an unstable node calling a stable one was reported -- that is the right direction"


def r84_graded_before_not_graded():
    """All graded analysis checks (cycles, layer violations, hubs, wrong-way deps,
    god objects, orphans) must be rendered before any non-graded checks (shared helpers,
    coordinators, overridden, duplicate code, copied blocks, idioms)."""
    vpath = os.path.join(REPO, ".agents", "skills", "code-archaeologist", "templates", "viewer.html")
    with open(vpath, "r", encoding="utf-8") as fh:
        vcontent = fh.read()
    render_pat = vcontent[vcontent.find("function renderPatterns()"):vcontent.find("// ---------------------------------------------------------------- controls")]
    graded_titles = ["Circular dependencies", "Backwards layer dependencies", "High coupling (hubs)",
                     "Wrong-direction dependencies", "God objects", "Dead / unused nodes"]
    non_graded_titles = ["Shared helpers (not graded)", "Coordinators (not graded)",
                         "Overridden everywhere (not graded)", "Duplicate code", "Copied blocks"]
    last_graded_idx = max(render_pat.find(f'"{t}"') for t in graded_titles)
    first_non_graded_idx = min(render_pat.find(f'"{t}"') for t in non_graded_titles)
    if last_graded_idx > first_non_graded_idx:
        return "viewer.html renders non-graded checks before graded checks in renderPatterns"

    sample_analysis = {
        "health": {"grade": "C", "score": 75, "deductions": {"cycles": 8, "god_objects": 3}},
        "summary": {"nodes": 10, "edges": 10, "cycles": 1, "orphans": 1, "layer_violations": 1,
                    "hubs": 1, "god_objects": 1},
        "cycles": [["A", "B"]],
        "layer_violations": [{"source": "A", "target": "B", "from": "model", "to": "service"}],
        "hubs": [{"node": "H", "fan_in": 5, "fan_out": 5, "instability": 0.5}],
        "wrong_way_deps": [{"source": "A", "target": "B", "source_instability": 0.2, "target_instability": 0.8}],
        "god_objects": [{"name": "G", "reason": "methods", "count": 25}],
        "orphans": ["O"],
        "shared_helpers": [{"node": "SH", "fan_in": 10, "fan_out": 0}],
        "coordinators": [{"node": "C", "fan_in": 0, "fan_out": 10}],
        "overridden": ["M"],
        "patterns": {"singleton": ["S"]},
    }
    txt = analyze.to_text(sample_analysis)
    lines = [line.strip().split()[0] for line in txt.splitlines() if line.startswith("  ")]
    graded_keys = ["deduction", "cycle", "violation", "hub", "wrong-way", "god", "orphan"]
    non_graded_keys = ["helper", "coord", "overridden", "idiom"]
    graded_indices = [lines.index(k) for k in graded_keys if k in lines]
    non_graded_indices = [lines.index(k) for k in non_graded_keys if k in lines]
    if max(graded_indices) > min(non_graded_indices):
        return f"analyze.to_text outputs non-graded smells before graded smells: {lines}"


CASES = [r01_go_receiver, r02_csharp_field_type, r03_go_map_type, r04_missed_append,
         r05_duplicates_declarations, r06_orphan_guard, r07_flask_routes,
         r08_missing_parser_is_visible, r09_no_absolute_paths, r10_brief_agrees_with_check,
         r11_test_filename_with_line, r12_crlf_hashes, r13_wrapped_signature,
         r14_context_budget, r15_moved_root_reason, r16_install_hint,
         r17_owner_respects_end, r18_same_name_in_two_files, r19_reports_are_reproducible,
         r20_structure_shared_names, r21_grammars_are_pinned, r22_metrics_by_graph_id,
         r23_long_node_paths, r24_route_table_handlers, r25_copied_blocks,
         r26_graph_path_on_another_drive, r27_generated_dirs_are_not_source,
         r28_mock_patch_is_not_a_route, r29_names_differing_only_by_case,
         r30_imported_axios_instance, r31_unknown_url_links_nowhere,
         r32_const_base_and_client_prefix, r33_overloads_are_separate_nodes,
         r34_js_method_calls_resolve, r35_dropped_calls_are_named,
         r36_render_failure_keeps_the_maps, r37_secret_names_are_not_secrets,
         r38_layer_from_annotation, r39_type_name_receivers,
         r40_framework_entries_are_not_dead, r41_next_conventions_are_entries,
         r42_ts_imports_fixture, r43_installed_skill_copy_is_not_source,
         r44_java_method_references, r45_module_load_calls, r46_calls_on_a_call_result,
         r47_calls_through_a_variable, r48_python_module_load_calls, r49_jsx_render_edges,
         r50_implements_links, r51_name_matched_is_earned, r52_calls_through_globals,
         r53_calls_outside_methods, r54_spring_injected_beans, r55_structure_implements_links,
         r56_kotlin_spring_injected_beans, r57_shared_class_names_by_package,
         r58_inherited_helper_calls, r59_typed_locals, r60_js_constructor_calls, r61_oop_model,
         r62_alias_in_two_apps, r63_varargs_and_unpicked_overloads, r64_mapstruct_expressions,
         r65_cast_receivers, r66_function_chosen_into_a_variable, r67_passed_functions,
         r68_objects_the_source_settles, r69_data_folders_are_source, r70_wrapped_components,
         r71_pattern_variables, r72_typed_hook_fields, r73_type_refs_are_references,
         r74_extended_classes_are_used, r75_structure_entry_points, r76_type_position_imports,
         r77_same_file_references, r78_layer_words_end_where_the_word_ends,
         r79_layer_from_the_folder, r80_one_doc_rule, r81_call_sites, r82_either_or_arms,
         r83_coupling_has_a_direction, r84_graded_before_not_graded]


def main() -> int:
    failed = 0
    for case in CASES:
        try:
            problem = case()
        except Exception as exc:                              # a crash is a failure too
            problem = f"raised {type(exc).__name__}: {exc}"
        failed += bool(problem)
        title = (case.__doc__ or "").strip().split("\n")[0]
        print(f"  {'FAIL' if problem else 'PASS'}  {case.__name__:<32} {title[:70]}")
        if problem:
            print(f"        -> {problem}")
    print(f"{len(CASES) - failed}/{len(CASES)} regression case(s) hold")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
