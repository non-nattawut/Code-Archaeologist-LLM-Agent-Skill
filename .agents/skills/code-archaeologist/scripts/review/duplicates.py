#!/usr/bin/env python3
"""duplicates.py — copy-pasted functions, found even when the names were changed.

Clone detection by normalized token hash. Every node's body is reduced to the
shape of its code — identifiers become `ID`, literals become `LIT`, comments and
whitespace go away, keywords and operators stay — and bodies that reduce to the
same shape are the same code:

    def total(items):          def sum_all(rows):
        n = 0                      total = 0
        for i in items:            for r in rows:
            n += i.price               total += r.cost
        return n                   return total

Both normalize to `def ID ( ID ) : ID = LIT for ID in ID : ID += ID . ID return ID`,
so a rename cannot hide the copy. Changing an operator or adding a branch does
change the shape, and the two stop clustering — which is the point: this finds
copies, not merely similar-looking code.

    python duplicates.py --src ./src
    python duplicates.py --src ./src --graph <flow_graph.json> --out <file>.json

Ranges come from the graph (`source` + `end`), so this reads each file once and
never re-parses. Nodes without a usable range are skipped — a synthetic route
node has no body to compare.

Since phase 9 it also finds **blocks** -- a run of MIN_TOKENS+ tokens copied into
two otherwise different functions, which no whole-body hash can see -- by winnowed
k-gram fingerprints over the same token shapes, trimmed to whole lines. A pair
already in a whole-body cluster is never reported again as a block.

Heuristic by design: a clone here is a token-shape match, not proof of a bad
abstraction. Two validators that legitimately look alike will cluster, and a
copy someone has since edited will not. It is a review prompt, not a verdict.

It errs toward missing a copy rather than inventing one. A docstring counts as a
token, so documenting one copy and not the other hides the pair — deliberate:
every rule for stripping leading docs was fragile enough to risk clustering
functions that merely start alike, and a false positive here costs more than a
miss.

Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR, skill_rel  # noqa: E402  (also puts sibling script dirs on sys.path)
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "report", "duplicates.json")

import manifest         # noqa: E402  (portable roots in the payload)
import console          # noqa: E402  (stdout must survive a non-UTF-8 console)
import scan_security    # noqa: E402  (one definition of "which files are source")

# Below this a match is noise: getters, one-line delegates and `return None`
# bodies are identical everywhere and say nothing about copy-paste.
MIN_TOKENS = 30

# Keywords kept verbatim so structure survives normalization. One union across
# the languages the graphs cover: a word only has to normalize *consistently*,
# and treating a stray `func` in Python as a keyword costs nothing.
KEYWORDS = frozenset("""
and as assert async await break case catch class const continue def default defer del
do elif else except extends finally for from func function go goto if implements import
in interface is lambda let map new nil none not or pass private protected public raise
range return select static struct switch this throw throws try type var void while with yield
bool byte char double float int long string true false null undefined self super
""".split())

TOKEN_RE = re.compile(r"""
      (?P<ws>\s+)
    | (?P<lcomment>\#[^\n]*|//[^\n]*)
    | (?P<bcomment>/\*.*?\*/)
    | (?P<tstring>'''.*?'''|\"\"\".*?\"\"\")
    | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)
    | (?P<number>\d+\.?\d*(?:[eE][+-]?\d+)?)
    | (?P<name>[A-Za-z_$][A-Za-z_$0-9]*)
    | (?P<op>[^\s\w])
""", re.VERBOSE | re.DOTALL)


def _shape(m) -> str | None:
    """One regex match -> its token shape, or None for whitespace and comments."""
    kind = m.lastgroup
    if kind in ("ws", "lcomment", "bcomment"):
        return None
    if kind in ("tstring", "string", "number"):
        return "LIT"
    if kind == "name":
        word = m.group()
        return word if word in KEYWORDS else "ID"
    return m.group()


def normalize(text: str) -> list[str]:
    """Source text -> the token shape of its code.

    Comments and whitespace are dropped, every literal becomes `LIT`, every
    non-keyword word becomes `ID`, and operators and punctuation are kept as
    they are. What survives is control flow and structure.
    """
    return [t for t in (_shape(m) for m in TOKEN_RE.finditer(text)) if t is not None]


def tokens_with_lines(text: str, first_line: int) -> list[tuple[str, int]]:
    """`normalize`, keeping the line each token starts on -- blocks are reported by line."""
    out: list[tuple[str, int]] = []
    line, pos = first_line, 0
    for m in TOKEN_RE.finditer(text):
        line += text.count("\n", pos, m.start())
        pos = m.start()
        tok = _shape(m)
        if tok is not None:
            out.append((tok, line))
    return out


def node_bodies(roots, graph_path: str) -> list[dict]:
    """Every graph node paired with the token shape of its source range."""
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            nodes = json.load(fh).get("nodes", [])
    except (OSError, ValueError):
        return []

    # key ("<root>/<rel>") -> absolute path, from the one definition of "source file"
    paths = {key: full for full, key in scan_security.iter_source_files(roots)}
    cache: dict[str, list[str]] = {}
    out = []
    for n in nodes:
        if n.get("declaration"):
            continue                       # a signature with no body has no shape
        src = n.get("source") or ""
        key, _, start = src.partition(":")
        end = n.get("end") or 0
        if not key or not start.isdigit() or not end:
            continue                       # synthetic node: no body to compare
        start = int(start)
        if end < start or key not in paths:
            continue
        if key not in cache:
            try:
                with open(paths[key], "r", encoding="utf-8", errors="replace") as fh:
                    cache[key] = fh.readlines()
            except OSError:
                cache[key] = []
        lines = cache[key]
        body = "".join(lines[start - 1:end])
        if not body.strip():
            continue
        lined = tokens_with_lines(body, start)
        out.append({"node": n, "tokens": [t for t, _ in lined], "loc": end - start + 1,
                    "lined": lined, "file": key, "range": (start, end)})
    return out


def find_clusters(bodies: list[dict], min_tokens: int = MIN_TOKENS) -> list[dict]:
    """Group bodies by the hash of their token shape; >= 2 is a clone cluster."""
    groups: dict[str, list[dict]] = {}
    for b in bodies:
        if len(b["tokens"]) < min_tokens:
            continue
        digest = hashlib.sha1(" ".join(b["tokens"]).encode("utf-8")).hexdigest()[:12]
        groups.setdefault(digest, []).append(b)

    clusters = []
    for digest, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda b: b["node"]["id"])
        clusters.append({
            "hash": digest,
            "tokens": len(members[0]["tokens"]),
            "loc": max(b["loc"] for b in members),
            "nodes": [{"id": b["node"]["id"], "source": b["node"].get("source"),
                       "layer": b["node"].get("layer"), "kind": b["node"].get("kind")}
                      for b in members],
        })
    # Biggest first: the longest copied body is the one worth extracting.
    return sorted(clusters, key=lambda c: (-c["tokens"], -len(c["nodes"]), c["hash"]))


# --- blocks: a copy smaller than a whole body ---------------------------------------
# Whole-body hashing cannot see a block pasted into two otherwise different
# functions: each body's shape changes, so neither hash matches. Blocks are found
# by winnowing (Schleimer, Wilkerson & Aiken 2003 -- what MOSS uses): hash every run
# of K tokens, keep the smallest hash in each window of W consecutive runs. Any
# shared run of W + K - 1 tokens is then *guaranteed* to share a kept fingerprint,
# and W + K - 1 is MIN_TOKENS, so nothing long enough to report can slip through,
# while each body keeps only about 2/(W+1) of its runs.
K = 10
W = MIN_TOKENS - K + 1
# A fingerprint present in this many places is boilerplate, not a copy.
MAX_OCCURRENCES = 50
_MOD = (1 << 61) - 1          # a stable hash: Python's hash() is salted per process,
_BASE = 1_000_003             # and constraint 2 wants the same bytes every run


def _winnow(seq: list[int]) -> list[tuple[int, int]]:
    """(fingerprint, position) kept for one token-id sequence."""
    if len(seq) < K:
        return []
    top = pow(_BASE, K - 1, _MOD)
    hashes, h = [], 0
    for i, tok in enumerate(seq):
        if i >= K:
            h = (h - seq[i - K] * top) % _MOD
        h = (h * _BASE + tok) % _MOD
        if i >= K - 1:
            hashes.append(h)
    kept, last = [], -1
    for start in range(max(1, len(hashes) - W + 1)):
        window = hashes[start:start + W]
        low = min(window)
        pos = start + len(window) - 1 - window[::-1].index(low)     # rightmost minimum
        if pos != last:
            kept.append((low, pos))
            last = pos
    return kept


def _line_start(lined, i) -> bool:
    return i == 0 or lined[i][1] != lined[i - 1][1]


def _line_end(lined, i) -> bool:
    return i == len(lined) - 1 or lined[i + 1][1] != lined[i][1]


def find_blocks(bodies: list[dict], clusters: list[dict], min_tokens: int = MIN_TOKENS) -> list[dict]:
    """Runs of >= min_tokens tokens copied between two different nodes, as whole lines.

    Trimmed to whole lines in *both* copies, so a match that starts or ends halfway
    through a statement is cut back to the statements it fully covers -- and dropped
    if too little is left. That errs toward missing a copy, the same side this whole
    pass errs on. Two nodes already in one whole-body cluster are skipped (they are
    reported there), and so are two nodes whose ranges overlap (one inside the other).
    """
    usable = [b for b in bodies if b.get("lined") and len(b["lined"]) >= min_tokens]
    clustered = set()
    for c in clusters:
        ids = sorted(n["id"] for n in c["nodes"])
        clustered.update((a, b) for i, a in enumerate(ids) for b in ids[i + 1:])
    vocab: dict[str, int] = {}
    seqs = [[vocab.setdefault(t, len(vocab) + 1) for t, _ in b["lined"]] for b in usable]
    index: dict[int, list[tuple[int, int]]] = {}
    for bi, seq in enumerate(seqs):
        for fp, pos in _winnow(seq):
            index.setdefault(fp, []).append((bi, pos))

    def skip(i: int, j: int) -> bool:
        a, b = usable[i], usable[j]
        if tuple(sorted((a["node"]["id"], b["node"]["id"]))) in clustered:
            return True
        return a["file"] == b["file"] and a["range"][0] <= b["range"][1] and b["range"][0] <= a["range"][1]

    grown: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}
    for fp in sorted(index):
        occ = index[fp]
        if len(occ) < 2 or len(occ) > MAX_OCCURRENCES:
            continue
        for x in range(len(occ)):
            for y in range(x + 1, len(occ)):
                (i, p), (j, q) = sorted((occ[x], occ[y]))
                if i == j or skip(i, j):
                    continue
                regions = grown.setdefault((i, j), [])
                if any(r[0] <= p < r[1] and r[2] <= q < r[3] for r in regions):
                    continue                          # inside a region already grown
                if seqs[i][p:p + K] != seqs[j][q:q + K]:
                    continue                          # a hash collision, not a copy
                s1, s2 = p, q
                while s1 and s2 and seqs[i][s1 - 1] == seqs[j][s2 - 1]:
                    s1, s2 = s1 - 1, s2 - 1
                e1, e2 = p + K, q + K
                while e1 < len(seqs[i]) and e2 < len(seqs[j]) and seqs[i][e1] == seqs[j][e2]:
                    e1, e2 = e1 + 1, e2 + 1
                regions.append((s1, e1, s2, e2))

    # One entry per copied *shape*, listing every place it occurs (finding #7). As
    # pairs, one block pasted into N functions was N*(N-1)/2 entries -- 207 on the
    # skill's own code, most of them one piece of argparse boilerplate seen again
    # and again -- which buried the distinct copies under the repeated one.
    groups: dict[tuple, dict] = {}
    for (i, j), regions in grown.items():
        la, lb = usable[i]["lined"], usable[j]["lined"]
        for s1, e1, s2, e2 in regions:
            while s1 < e1 and not (_line_start(la, s1) and _line_start(lb, s2)):
                s1, s2 = s1 + 1, s2 + 1
            while e1 > s1 and not (_line_end(la, e1 - 1) and _line_end(lb, e2 - 1)):
                e1, e2 = e1 - 1, e2 - 1
            if e1 - s1 < min_tokens:
                continue
            places = groups.setdefault(tuple(t for t, _ in la[s1:e1]), {})
            for body, lined, s, e in ((usable[i], la, s1, e1), (usable[j], lb, s2, e2)):
                lines = (lined[s][1], lined[e - 1][1])
                places[(body["node"]["id"], lines)] = {
                    "id": body["node"]["id"], "source": body["node"].get("source"), "lines": list(lines)}
    blocks = []
    for shape, places in groups.items():
        ordered = [places[k] for k in sorted(places)]
        blocks.append({"hash": hashlib.sha1(" ".join(shape).encode("utf-8")).hexdigest()[:12],
                       "tokens": len(shape),
                       "loc": max(p["lines"][1] - p["lines"][0] + 1 for p in ordered),
                       "places": ordered})
    return sorted(blocks, key=lambda b: (-b["tokens"], -len(b["places"]), b["hash"]))


def build(roots, graph_path: str = DEFAULT_GRAPH, out_path: str | None = None) -> dict:
    roots = [roots] if isinstance(roots, str) else list(roots)
    bodies = node_bodies(roots, graph_path)
    clusters = find_clusters(bodies)
    blocks = find_blocks(bodies, clusters)

    payload = {
        "roots": manifest.rel_roots(roots),
        "graph": skill_rel(graph_path),
        "summary": {
            "clusters": len(clusters),
            "nodes_involved": sum(len(c["nodes"]) for c in clusters),
            # What deleting the copies would save: every member past the first.
            "duplicated_loc": sum(c["loc"] * (len(c["nodes"]) - 1) for c in clusters),
            "blocks": len(blocks),
        },
        "clusters": clusters,
        # Phase 9: copies smaller than a whole body. Never a pair already in a cluster.
        "blocks": blocks,
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Find copy-pasted functions by normalized token hash.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph whose nodes supply the source ranges")
    parser.add_argument("--out", default=None, help=f"Write the payload here (e.g. {DEFAULT_OUT})")
    parser.add_argument("--top", type=int, default=10, help="Clusters to print")
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
    print(f"Duplicates: {s['clusters']} cluster(s), {s['nodes_involved']} node(s), "
          f"{s['duplicated_loc']} duplicated line(s)")
    for c in d["clusters"][:args.top]:
        print(f"  {c['tokens']:>4} tokens x{len(c['nodes'])}  {', '.join(n['id'] for n in c['nodes'])}")
        for n in c["nodes"]:
            print(f"       {n['source']}")
    if d["blocks"]:
        print(f"Copied blocks: {len(d['blocks'])} (a run of {MIN_TOKENS}+ tokens in two or more different nodes)")
        for b in d["blocks"][:args.top]:
            print(f"  {b['tokens']:>4} tokens x{len(b['places'])}  "
                  + "  ~  ".join(f"{p['id']} L{p['lines'][0]}-{p['lines'][1]}" for p in b["places"]))
    if args.out:
        print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
