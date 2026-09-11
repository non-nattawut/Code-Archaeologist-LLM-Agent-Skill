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
import ts_extract  # noqa: E402

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
        for cls in ts_extract.extract_file(path)["classes"]:
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
    if "InvoiceService.Total" not in cs:
        return "a same-file overload fold was qualified as if it were a collision"


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
         r32_const_base_and_client_prefix]


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
