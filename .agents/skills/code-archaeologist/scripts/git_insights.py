#!/usr/bin/env python3
"""git_insights.py — churn, ownership, and hotspot ranking from git history.

The graph says how the code is wired; git says which parts actually move and who
moves them. Joining the two answers the question a newcomer really has: "where is
the risk?" — code that changes often *and* has many callers.

Computed with one `git log --numstat` pass (no external deps):

  churn      commits touching each source file, plus insertions/deletions and the
             first/last commit dates.
  ownership  commit counts per author per file; the top author is the file's owner.
  hotspots   per graph node: risk = commits x (1 + fan_in + fan_out), i.e. how
             often it changes weighted by how connected it is. Ranked desc.

    python git_insights.py --src ./backend ./frontend
    python git_insights.py --src ./src --out data/report/insights.json

Not a git repo (or git missing)? It reports that and returns empty data instead of
failing the pipeline. Zero external dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "report", "insights.json")

sys.path.insert(0, SCRIPT_DIR)
from manifest import SOURCE_EXTS  # noqa: E402

RECORD = "\x01"  # commit-header marker; keeps parsing unambiguous


def _git(args: list[str], cwd: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return out.stdout if out.returncode == 0 else None


def repo_root(path: str) -> str | None:
    top = _git(["rev-parse", "--show-toplevel"], os.path.abspath(path))
    return os.path.abspath(top.strip()) if top and top.strip() else None


def churn(roots) -> dict:
    """Per-file commit counts, authors and dates for every source file under `roots`."""
    roots = [roots] if isinstance(roots, str) else roots
    root = repo_root(roots[0])
    if not root:
        return {}

    rel_roots = []
    for r in roots:
        rel = os.path.relpath(os.path.abspath(r), root).replace("\\", "/")
        rel_roots.append("." if rel == "." else rel)

    # --no-renames keeps every numstat path a real path: with rename detection on,
    # git emits compact forms like `src/{ => backend}/x.py` that match no file.
    log = _git(["log", "--no-merges", "--no-renames", "--numstat", f"--format={RECORD}%H|%an|%aI",
                "--", *rel_roots], root)
    if log is None:
        return {}

    files: dict[str, dict] = {}
    author = date = ""
    for line in log.splitlines():
        if line.startswith(RECORD):
            _, _, meta = line.partition(RECORD)
            parts = meta.split("|")
            author, date = (parts[1], parts[2]) if len(parts) >= 3 else ("", "")
            continue
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        added, deleted, path = cols
        if not path.endswith(SOURCE_EXTS):
            continue
        entry = files.setdefault(path, {"commits": 0, "insertions": 0, "deletions": 0,
                                        "authors": {}, "last_commit": date, "first_commit": date})
        entry["commits"] += 1
        entry["insertions"] += int(added) if added.isdigit() else 0
        entry["deletions"] += int(deleted) if deleted.isdigit() else 0
        entry["authors"][author] = entry["authors"].get(author, 0) + 1
        entry["first_commit"] = date  # log is newest-first, so the last seen is the oldest
    for entry in files.values():
        entry["authors"] = dict(sorted(entry["authors"].items(), key=lambda kv: (-kv[1], kv[0])))
        entry["owner"] = next(iter(entry["authors"]), None)
    return files


def _match_file(file_key: str, git_files: dict) -> str | None:
    """Map a node's `<area>/<path>` source key onto a repo-relative git path."""
    if file_key in git_files:
        return file_key
    for path in git_files:
        if path.endswith("/" + file_key) or file_key.endswith("/" + path):
            return path
    return None


def build(roots, graph_path: str = DEFAULT_GRAPH) -> dict:
    files = churn(roots)
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except (FileNotFoundError, ValueError):
        graph = {"nodes": [], "edges": []}

    fan_in: dict[str, int] = {}
    fan_out: dict[str, int] = {}
    for edge in graph.get("edges", []):
        fan_out[edge["source"]] = fan_out.get(edge["source"], 0) + 1
        fan_in[edge["target"]] = fan_in.get(edge["target"], 0) + 1

    nodes: dict[str, dict] = {}
    resolved: dict[str, str | None] = {}
    for node in graph.get("nodes", []):
        nid = node["id"]
        file_key = (node.get("source") or "").rpartition(":")[0] or (node.get("source") or "")
        if file_key not in resolved:
            resolved[file_key] = _match_file(file_key, files)
        git_path = resolved[file_key]
        stats = files.get(git_path, {}) if git_path else {}
        commits = stats.get("commits", 0)
        fin, fout = fan_in.get(nid, 0), fan_out.get(nid, 0)
        authors = stats.get("authors", {})
        nodes[nid] = {
            "file": git_path or file_key, "commits": commits, "owner": stats.get("owner"),
            "authors": dict(list(authors.items())[:3]),  # top 3, already sorted by commits
            "last_commit": stats.get("last_commit"), "first_commit": stats.get("first_commit"),
            "fan_in": fin, "fan_out": fout,
            "risk": commits * (1 + fin + fout),
        }

    hotspots = sorted(({"node": nid, **data} for nid, data in nodes.items() if data["risk"] > 0),
                      key=lambda h: (-h["risk"], h["node"]))
    return {
        "files": dict(sorted(files.items())),
        "nodes": nodes,
        "hotspots": hotspots,
        "summary": {
            "files_with_history": len(files),
            "commits_counted": sum(f["commits"] for f in files.values()),
            "authors": len({a for f in files.values() for a in f["authors"]}),
            "graph": os.path.basename(graph_path),
            "note": None if files else "no git history found (not a git repo, or git unavailable)",
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Churn, ownership and hotspot ranking from git history.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph to join the history onto")
    parser.add_argument("--top", type=int, default=0, help="Print only the top N hotspots")
    parser.add_argument("--out", default=None, help=f"Also write the result to this path (e.g. {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    result = build(args.src, args.graph)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
        print(f"Wrote {args.out}  ({len(result['hotspots'])} ranked hotspot(s))")
    else:
        if args.top:
            result = {"hotspots": result["hotspots"][:args.top], "summary": result["summary"]}
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
