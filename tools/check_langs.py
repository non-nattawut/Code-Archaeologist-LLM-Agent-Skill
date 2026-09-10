#!/usr/bin/env python3
"""check_langs.py -- prove that every language the skill claims to graph still does.

A grammar yields a parse tree; a *graph* additionally needs a query naming which
node types are classes, methods and calls, plus receiver-resolution rules. When
those are wrong the failure is silent: the language produces no nodes, and a graph
that is empty for want of a query looks exactly like a graph of a small codebase.
So each supported language has a fixture under `tests/fixtures/langs/<lang>/` and a
row in `expected.json`, and this asserts one against the other.

    python tools/check_langs.py                # every language
    python tools/check_langs.py go java        # only these
    python tools/check_langs.py --update       # rewrite expected.json from reality

`--update` exists so the expectations are recorded rather than typed, but it is
the dangerous option: it will happily bless a regression. Read the diff it
produces before committing it -- that diff *is* the review.

Every fixture is the same four things (see the fixtures' own README): a store, a
service calling it **through a declared field**, a controller with a route, and a
test file. The edges are the load-bearing assertion; nodes alone only prove the
grammar loaded, while an edge proves receiver resolution worked.

Repo tool, not part of the skill: fixtures do not ship to users.
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(REPO, ".agents", "skills", "code-archaeologist")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import paths  # noqa: E402,F401  (puts the category dirs and vendor/ on sys.path)

import build_flow  # noqa: E402

FIXTURES = os.path.join(REPO, "tests", "fixtures", "langs")
EXPECTED = os.path.join(FIXTURES, "expected.json")


def observe(lang_dir: str) -> dict:
    """What the flow map actually makes of one fixture directory."""
    methods, edges = build_flow.analyze([lang_dir])
    routes = []
    for info in methods.values():
        for r in info.get("routes") or []:
            routes.append(f"{r['method']} {r['path']}")
    return {
        "nodes": sorted(methods),
        "edges": sorted([src, dst] for src, dst, kind in edges if kind == "calls"),
        "routes": sorted(set(routes)),
        "test_nodes": sorted(n for n, i in methods.items() if i.get("layer") == "test"),
    }


def compare(lang: str, want: dict, got: dict) -> list[str]:
    out = []
    for key in ("nodes", "edges", "routes", "test_nodes"):
        expected = want.get(key, [])
        actual = got.get(key, [])
        if expected == actual:
            continue
        missing = [x for x in expected if x not in actual]
        extra = [x for x in actual if x not in expected]
        if missing:
            out.append(f"{lang}: {key} missing {missing}")
        if extra:
            out.append(f"{lang}: {key} unexpected {extra}")
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    update = "--update" in sys.argv[1:]

    if not os.path.isdir(FIXTURES):
        print(f"no fixtures at {FIXTURES}")
        return 1
    langs = sorted(d for d in os.listdir(FIXTURES)
                   if os.path.isdir(os.path.join(FIXTURES, d)))
    if args:
        unknown = [a for a in args if a not in langs]
        if unknown:
            print(f"unknown language(s): {unknown}; have {langs}")
            return 1
        langs = args

    expected = {}
    if os.path.exists(EXPECTED):
        with open(EXPECTED, "r", encoding="utf-8") as fh:
            expected = json.load(fh)

    observed = {lang: observe(os.path.join(FIXTURES, lang)) for lang in langs}

    if update:
        expected.update(observed)
        with open(EXPECTED, "w", encoding="utf-8") as fh:
            json.dump(expected, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"wrote {os.path.relpath(EXPECTED, REPO)} for {len(langs)} language(s)."
              f" READ THE DIFF -- this blesses whatever the extractor currently does.")
        return 0

    findings: list[str] = []
    for lang in langs:
        if lang not in expected:
            findings.append(f"{lang}: no row in expected.json (run --update, then read the diff)")
            continue
        findings += compare(lang, expected[lang], observed[lang])

    print(f"{len(langs)} language(s) checked: {', '.join(langs)}")
    if not findings:
        for lang in langs:
            o = observed[lang]
            print(f"  OK   {lang:<11} {len(o['nodes'])} node(s), {len(o['edges'])} edge(s), "
                  f"{len(o['routes'])} route(s), {len(o['test_nodes'])} test node(s)")
        return 0
    print(f"FAIL {len(findings)} problem(s):")
    for f in findings:
        print("  -", f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
