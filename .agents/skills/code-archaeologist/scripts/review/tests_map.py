#!/usr/bin/env python3
"""tests_map.py — which nodes the test suite even mentions.

Not execution coverage: no runner, no instrumentation, nothing to install. It
reads the test files, collects the identifiers they name, and marks a graph node
as *referenced* when a test file names it — `Class.method` needs both the class
and the method in the same file, a plain function or class needs its own name.

That is enough to answer the question worth asking early: **which parts of this
codebase does nothing in the test suite even talk about.**

    python tests_map.py --src ./src
    python tests_map.py --src ./backend ./frontend --graph <flow_graph.json> --out <file>.json

Dunder methods and nodes that live in test files themselves are left out of the
count. A referenced node may still be untested (it might only appear in an
import); an unreferenced one is a real gap.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR, SKILL_ROOT  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "report", "tests.json")

import console          # noqa: E402  (stdout must survive a non-UTF-8 console)
import scan_security    # noqa: E402  (one definition of "a source file")
import taxonomy         # noqa: E402  (one definition of "a test file")
import manifest  # noqa: E402

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def identifiers(full: str) -> set[str]:
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            return set(IDENT_RE.findall(fh.read()))
    except OSError:
        return set()


def build(roots, graph_path: str = DEFAULT_GRAPH, out_path: str | None = None) -> dict:
    roots = [roots] if isinstance(roots, str) else list(roots)
    tests: dict[str, set[str]] = {}
    for full, key in scan_security.iter_source_files(roots):
        if taxonomy.is_test_file(key, full):     # convention, else a framework marker
            tests[key] = identifiers(full)

    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            nodes = json.load(fh).get("nodes", [])
    except (OSError, ValueError):
        nodes = []

    referenced: dict[str, list[str]] = {}
    unreferenced: list[dict] = []
    for n in nodes:
        nid = n.get("id", "")
        name = nid.rsplit(".", 1)[-1]
        if name.startswith("__") and name.endswith("__"):
            continue                                        # called implicitly
        if taxonomy.is_test_path((n.get("source") or "").split(":")[0]):
            continue                                        # the tests themselves
        cls = n.get("cls")
        hits = sorted(f for f, ids in tests.items()
                      if name in ids and (not cls or cls in ids))
        if hits:
            referenced[nid] = hits
        else:
            unreferenced.append({"id": nid, "source": n.get("source"),
                                 "layer": n.get("layer"), "kind": n.get("kind")})

    considered = len(referenced) + len(unreferenced)
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roots": manifest.rel_roots(roots),
        "graph": os.path.relpath(graph_path, SKILL_ROOT).replace("\\", "/"),
        "summary": {
            "test_files": len(tests),
            "considered": considered,
            "referenced": len(referenced),
            "unreferenced": len(unreferenced),
            "referenced_pct": round(100 * len(referenced) / considered, 1) if considered else 0.0,
        },
        "test_files": sorted(tests),
        "referenced": dict(sorted(referenced.items())),
        "unreferenced": sorted(unreferenced, key=lambda x: x["id"]),
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Map graph nodes to the test files that name them.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph whose nodes are checked")
    parser.add_argument("--out", default=None, help=f"Write the payload here (e.g. {DEFAULT_OUT})")
    parser.add_argument("--top", type=int, default=15, help="Unreferenced nodes to print")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(argv)
    console.safe_stdout()

    missing = [r for r in args.src if not os.path.isdir(r)]
    if missing:
        print(f"error: source root(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    d = build(args.src, args.graph, args.out)
    if args.format == "json":
        print(json.dumps(d, indent=2))
        return 0

    s = d["summary"]
    print(f"Tests: {s['test_files']} test file(s), {s['referenced']}/{s['considered']} node(s) "
          f"named by a test ({s['referenced_pct']}%)")
    if not s["test_files"]:
        print("  no test files found under --src (looked for test/tests/__tests__/spec dirs, "
              "test_*.py, *_test.*, *.test.*, *.spec.*, *Test.java/kt/cs, and files carrying "
              "@Test / [Fact] / #[test] markers)")
    for n in d["unreferenced"][:args.top]:
        print(f"  untested  {n['id']:<32} {n['source']}")
    if len(d["unreferenced"]) > args.top:
        print(f"  ... {len(d['unreferenced']) - args.top} more (raise --top)")
    if args.out:
        print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
