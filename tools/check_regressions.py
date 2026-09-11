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
    for pkg in ("tree-sitter-javascript", "tree-sitter-typescript"):
        if hint.count(pkg + " ") + hint.endswith(pkg) != 1:
            return f"{pkg!r} appears {hint.count(pkg)} time(s) in {hint!r}"


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


def r18_id_collision_is_said():
    """phase 4: two definitions in different files sharing one flow id (every `main`,
    every `build`) became one node with every definition's call edges -- silently."""
    import contextlib
    import io
    d = tempfile.mkdtemp()
    for name in ("one.py", "two.py"):
        open(os.path.join(d, name), "w", encoding="utf-8").write("def main():\n    return 1\n")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        build_flow.analyze([d])
    if "id collision: main" not in err.getvalue():
        return "two files defining main() produced no collision warning"
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        build_flow.analyze([os.path.join(FIX, "csharp")])    # an overload fold, one file
    if "id collision" in err.getvalue():
        return "a same-file overload fold was reported as a collision"


CASES = [r01_go_receiver, r02_csharp_field_type, r03_go_map_type, r04_missed_append,
         r05_duplicates_declarations, r06_orphan_guard, r07_flask_routes,
         r08_missing_parser_is_visible, r09_no_absolute_paths, r10_brief_agrees_with_check,
         r11_test_filename_with_line, r12_crlf_hashes, r13_wrapped_signature,
         r14_context_budget, r15_moved_root_reason, r16_install_hint,
         r17_owner_respects_end, r18_id_collision_is_said]


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
