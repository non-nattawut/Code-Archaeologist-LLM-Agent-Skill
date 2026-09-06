#!/usr/bin/env python3
"""scan_security.py — deterministic risk scan over the source roots.

A line-oriented regex sweep for the four issue classes worth flagging without any
type inference, with each finding attached to the graph node that owns that line
(so a risk can be traced and blast-radiused like anything else):

  hardcoded_secret  api keys / passwords / tokens assigned to a literal, AWS keys,
                    inline private keys.
  sql_injection     a SQL execute/query call whose statement is interpolated
                    (f-string, `+`, `%`, `.format(`, `${}`).
  dangerous_eval    eval / exec / new Function / innerHTML / dangerouslySetInnerHTML.
  debug_statement   print / console.log / debugger / breakpoint left in the code.

Tests, fixtures, docs and example folders are skipped (they legitimately contain
fake secrets and debug output). Secret values are redacted in the output.

    python scan_security.py --src ./backend ./frontend
    python scan_security.py --src ./src --out data/report/security.json

Heuristic by design: these are review prompts, not proof. Zero external
dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "flow", "flow_graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "report", "security.json")

sys.path.insert(0, SCRIPT_DIR)
from manifest import SOURCE_EXTS, SKIP_DIRS, _rel_key  # noqa: E402

# Directories/filenames whose "secrets" and debug output are intentional.
EXCLUDE_DIRS = {"test", "tests", "__tests__", "spec", "specs", "fixtures",
                "docs", "doc", "examples", "example", "migrations"}
EXCLUDE_FILE_RE = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.|^conftest\.py$)", re.I)

# Lines that look like a secret assignment but aren't one.
PLACEHOLDER_RE = re.compile(
    r"(os\.environ|os\.getenv|process\.env|getenv|config\[|settings\.|\{\{|\$\{|<[^>]+>|"
    r"changeme|your[_-]|placeholder|example|xxxx|\*\*\*|dummy)", re.I)

# Each rule is a list of regexes that must ALL match the same line.
RULES = [
    {"id": "hardcoded_secret", "severity": "high",
     "message": "Credential assigned to a literal value",
     "patterns": [re.compile(
         r"""(?i)\b\w*(api[_-]?key|secret|token|password|passwd|credential|access[_-]?key)\w*"""
         r"""\s*[:=]\s*["'][^"']{8,}["']""")]},
    {"id": "hardcoded_secret", "severity": "high",
     "message": "AWS access key id in source",
     "patterns": [re.compile(r"\bAKIA[0-9A-Z]{16}\b")]},
    {"id": "hardcoded_secret", "severity": "high",
     "message": "Private key material in source",
     "patterns": [re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")]},
    {"id": "sql_injection", "severity": "high",
     "message": "SQL statement built by string interpolation",
     "patterns": [re.compile(r"(?i)\b(execute|executemany|query|raw|raw_query)\s*\("),
                  re.compile(r"(?i)\b(select|insert|update|delete|drop)\b"),
                  re.compile(r"""(f["'])|(\$\{)|(["']\s*\+)|(\+\s*["'])|(%\s*[(\w])|(\.format\()""")]},
    {"id": "dangerous_eval", "severity": "high",
     "message": "Dynamic code execution",
     "patterns": [re.compile(r"(?<![\w.])(eval|exec)\s*\(|new\s+Function\s*\(")]},
    {"id": "dangerous_eval", "severity": "medium",
     "message": "Raw HTML injection sink",
     "patterns": [re.compile(r"dangerouslySetInnerHTML|\.innerHTML\s*=|document\.write\s*\(")]},
    {"id": "debug_statement", "severity": "low",
     "message": "Debug statement left in the code",
     "patterns": [re.compile(r"(?<![\w.])(print|breakpoint)\s*\(|console\.(log|debug)\s*\(|"
                             r"\bdebugger\b|pdb\.set_trace\s*\(")]},
]

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
COMMENT_RE = re.compile(r"^\s*(#|//|/\*|\*)")
REDACT_RE = re.compile(r"""(["'])([^"']{8,})\1""")


def _excluded(path: str) -> bool:
    parts = [p.lower() for p in path.replace("\\", "/").split("/")]
    return bool(EXCLUDE_DIRS.intersection(parts[:-1])) or bool(EXCLUDE_FILE_RE.search(parts[-1]))


def iter_source_files(roots):
    """Yield (absolute path, `<root-basename>/<relpath>` key) for every source file."""
    roots = [roots] if isinstance(roots, str) else roots
    for root in roots:
        root = os.path.abspath(root)
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in sorted(names):
                if fn.endswith(SOURCE_EXTS):
                    full = os.path.join(dirpath, fn)
                    yield full, _rel_key(full, root)


def node_index(graph_path: str) -> dict[str, list[tuple[int, str]]]:
    """file key -> [(line, node id), ...] sorted, so a finding can name its owner."""
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except (FileNotFoundError, ValueError):
        return {}
    index: dict[str, list[tuple[int, str]]] = {}
    for node in graph.get("nodes", []):
        src = node.get("source") or ""
        path, _, line = src.rpartition(":")
        if not path or not line.isdigit():
            path, line = src, "0"
        index.setdefault(path, []).append((int(line), node["id"]))
    for entries in index.values():
        entries.sort()
    return index


def owner_of(index: dict, file_key: str, line: int) -> str | None:
    """The last node that starts at or before `line` in the same file."""
    owner = None
    for start, node_id in index.get(file_key, []):
        if start <= line:
            owner = node_id
        else:
            break
    return owner


def snippet_of(line: str, rule_id: str) -> str:
    """The offending line, with string literals masked when it may hold a secret."""
    text = line.strip()[:160]
    if rule_id != "hardcoded_secret":
        return text
    return REDACT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)[:3]}...redacted{m.group(1)}", text)


def scan(roots, graph_path: str = DEFAULT_GRAPH) -> dict:
    index = node_index(graph_path)
    findings, scanned, skipped = [], 0, 0

    for full, key in iter_source_files(roots):
        if _excluded(key):
            skipped += 1
            continue
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        scanned += 1
        for lineno, raw in enumerate(lines, 1):
            if COMMENT_RE.match(raw) or len(raw) > 500:
                continue
            for rule in RULES:
                if not all(p.search(raw) for p in rule["patterns"]):
                    continue
                if rule["id"] == "hardcoded_secret" and PLACEHOLDER_RE.search(raw):
                    continue
                findings.append({
                    "rule": rule["id"], "severity": rule["severity"],
                    "message": rule["message"], "file": key, "line": lineno,
                    "node": owner_of(index, key, lineno),
                    "snippet": snippet_of(raw, rule["id"]),
                })
                break  # one finding per line keeps the report readable

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["file"], f["line"]))
    by_severity = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}
    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    return {
        "findings": findings,
        "summary": {"total": len(findings), "by_severity": by_severity, "by_rule": by_rule,
                    "files_scanned": scanned, "files_skipped": skipped},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Scan source roots for security/debug risks.")
    parser.add_argument("--src", nargs="+", default=["./src"], help="One or more source roots")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Graph used to attribute findings to nodes")
    parser.add_argument("--out", default=None, help=f"Also write the report to this path (e.g. {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    report = scan(args.src, args.graph)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
        print(f"Wrote {args.out}  ({report['summary']['total']} finding(s))")
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
