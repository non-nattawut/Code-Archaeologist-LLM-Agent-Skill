#!/usr/bin/env python3
"""time_build.py -- how long the skill takes, stage by stage, on a real repository.

The skill's whole claim is that it is cheaper than reading the source. This
measures the claim instead of asserting it: wall time for each stage (`project`,
`flow`, `report`, `brief`), and the size of what an agent would otherwise read
(the source) against what the skill hands it (the brief, and a node's note).

    python tools/time_build.py                          # sample_src + the skill's own code
    python tools/time_build.py ../some-repo --json out.json

**Every corpus is read-only.** The skill writes only into its own `data/`, so it
is installed into a temp directory with `bin/cli.js --target` -- running it in
place would overwrite this repo's committed sample -- and every corpus is
snapshotted (path, size, mtime of each file outside `.git`) before and after the
run; any difference fails it. The only thing run inside a corpus is the report's
`git log`, which reads. And only aggregates are printed: no file, node or author
name from a corpus reaches the output, because a corpus may be someone else's code.

Repo tool, not part of the installed skill.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(REPO, ".agents", "skills", "code-archaeologist")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import paths  # noqa: E402,F401
from paths import long_path  # noqa: E402  (a corpus's note names can pass MAX_PATH)
import scan_security  # noqa: E402  (one definition of "a source file")

STAGES = ["project", "flow", "report", "brief"]
GRAPHABLE = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".go", ".cs"}
OWN_CODE = [os.path.join(SKILL, "scripts"), os.path.join(REPO, "tools"),
            os.path.join(REPO, "bin"), os.path.join(REPO, "tests")]


def install(tmp: str) -> str:
    """A fresh copy of the skill in `tmp`, with this machine's grammars."""
    r = subprocess.run(["node", os.path.join(REPO, "bin", "cli.js"), "--harness", "claude",
                        "--target", tmp], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        sys.exit(f"installer failed ({r.returncode})")
    skill = os.path.join(tmp, ".claude", "skills", "code-archaeologist")
    # The installer never copies vendor/ -- it is built for one interpreter -- but
    # this is that interpreter, so reuse it rather than download every grammar again.
    shutil.copytree(os.path.join(SKILL, "vendor"), os.path.join(skill, "vendor"))
    return skill


def snapshot(roots) -> dict:
    """(path, size, mtime) of every file under `roots` outside `.git`."""
    out = {}
    for root in roots:
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                full = os.path.join(base, f)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                out[full] = (st.st_size, st.st_mtime_ns)
    return out


def measure(skill: str, roots, label: str) -> dict:
    files = [(full, key) for full, key in scan_security.iter_source_files(roots)]
    graphable = [f for f, _ in files if os.path.splitext(f)[1].lower() in GRAPHABLE]
    source_bytes = sum(os.path.getsize(f) for f in graphable)

    before = snapshot(roots)
    seconds, brief_bytes = {}, 0
    for stage in STAGES:
        args = [sys.executable, os.path.join(skill, "scripts", "archaeologist.py"), stage]
        if stage != "brief":
            args += ["--src", *roots]
        t0 = time.perf_counter()
        r = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL)
        seconds[stage] = round(time.perf_counter() - t0, 2)
        if r.returncode:
            # stderr can name the corpus's files: report the code, not the text.
            sys.exit(f"{label}: `{stage}` exited {r.returncode}")
        if stage == "brief":
            brief_bytes = len(r.stdout)
    after = snapshot(roots)
    if before != after:
        changed = len(set(before.items()) ^ set(after.items()))
        sys.exit(f"{label}: {changed} file entr(y/ies) in the corpus changed during the run -- "
                 "it must be read-only. Stopping.")

    data = os.path.join(skill, "data")
    flow = json.load(open(os.path.join(data, "flow", "flow_graph.json"), encoding="utf-8"))
    struct = json.load(open(os.path.join(data, "structure", "graph.json"), encoding="utf-8"))
    notes_dir = os.path.join(data, "flow", "notes")
    notes = [os.path.getsize(long_path(os.path.join(notes_dir, f))) for f in os.listdir(notes_dir)
             if f.endswith(".md")] if os.path.isdir(notes_dir) else []
    return {
        "corpus": label, "files": len(files), "graphable_files": len(graphable),
        "source_bytes": source_bytes,
        "flow": [len(flow["nodes"]), len(flow["edges"])],
        "structure": [len(struct["nodes"]), len(struct["edges"])],
        "seconds": seconds, "total_seconds": round(sum(seconds.values()), 2),
        "brief_bytes": brief_bytes,
        "note_bytes_avg": round(sum(notes) / len(notes)) if notes else 0,
        "source_per_brief": round(source_bytes / brief_bytes, 1) if brief_bytes else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Time every stage of the skill on read-only corpora.")
    parser.add_argument("roots", nargs="*", help="One source root per corpus (default: sample_src, then the skill's own code)")
    parser.add_argument("--json", default=None, help="Also write the rows here")
    parser.add_argument("--keep", default=None,
                        help="Install into this (new) directory and leave it, so the built maps can be inspected")
    args = parser.parse_args(argv)

    corpora = ([[os.path.abspath(r)] for r in args.roots] if args.roots
               else [[os.path.join(REPO, "sample_src")], OWN_CODE])
    rows = []
    if args.keep:
        # Only the last corpus's maps survive: each run rebuilds the same install.
        _run(corpora, install(os.path.abspath(args.keep)), rows)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(rows, fh, indent=2)
                fh.write("\n")
        return 0
    # The temp install holds notes whose names can pass MAX_PATH, which the default
    # cleanup cannot delete; remove it through the long-path form instead.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        skill = install(tmp)
        try:
            _run(corpora, skill, rows)
        finally:
            shutil.rmtree(long_path(os.path.join(tmp, ".claude")), ignore_errors=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
            fh.write("\n")
    return 0


def _run(corpora, skill: str, rows: list) -> None:
    for roots in corpora:
        label = "skill's own code" if roots == OWN_CODE else os.path.basename(roots[0].rstrip("/\\"))
        rows.append(measure(skill, roots, label))
        r = rows[-1]
        print(f"{r['corpus']:<18} {r['graphable_files']:>5} graphable file(s), "
              f"{r['source_bytes'] / 1024:>7.0f} KB source -> flow {r['flow'][0]}/{r['flow'][1]}, "
              f"structure {r['structure'][0]}/{r['structure'][1]}")
        print("  " + "  ".join(f"{s} {r['seconds'][s]:.2f}s" for s in STAGES)
              + f"  | total {r['total_seconds']:.2f}s")
        per100 = {s: round(100 * r["seconds"][s] / max(1, r["graphable_files"]), 2) for s in STAGES}
        print("  per 100 graphable files: " + "  ".join(f"{s} {v:.2f}s" for s, v in per100.items()))
        print(f"  brief {r['brief_bytes']} B, note avg {r['note_bytes_avg']} B;"
              f" source is {r['source_per_brief']}x the brief")


if __name__ == "__main__":
    sys.exit(main())
