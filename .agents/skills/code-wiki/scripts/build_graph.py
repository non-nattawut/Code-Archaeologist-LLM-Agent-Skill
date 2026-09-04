#!/usr/bin/env python3
"""build_graph.py — Markdown vault -> graph.json + registry.json.

Parses every data/vault/*.md page, extracts [[wikilinks]] as edges and the
front-matter `layer` as node metadata, and writes a deterministic adjacency
graph plus an entity->path registry.

Zero external dependencies. Python 3.10+.
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
STRUCTURE_DIR = os.path.join(DATA_DIR, "structure")
DEFAULT_VAULT = os.path.join(STRUCTURE_DIR, "vault")

WIKILINK_RE = re.compile(r"\[\[(.*?)\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    """Minimal `key: value` front-matter parser (no PyYAML dependency)."""
    meta: dict[str, str] = {}
    m = FRONTMATTER_RE.match(text)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta


def body_after_frontmatter(text: str) -> str:
    m = FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def extract_section(body: str, heading: str) -> str:
    """Return the text under a `## <heading>` section, up to the next `##`."""
    lines = body.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            capturing = m.group(1).strip().lower() == heading.lower()
            continue
        if capturing:
            out.append(line)
    text = "\n".join(out).strip()
    return text


def build(vault: str, out_dir: str) -> int:
    if not os.path.isdir(vault):
        print(f"error: vault '{vault}' not found. Run build_wiki.py first.", file=sys.stderr)
        return 2

    os.makedirs(out_dir, exist_ok=True)

    nodes: dict[str, dict] = {}
    raw_edges: list[tuple[str, str]] = []
    registry: dict[str, str] = {}

    md_files = sorted(f for f in os.listdir(vault) if f.endswith(".md"))
    for fn in md_files:
        path = os.path.join(vault, fn)
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()

        meta = parse_frontmatter(text)
        entity = meta.get("entity") or os.path.splitext(fn)[0]
        layer = meta.get("layer", "unknown")
        body = body_after_frontmatter(text)
        summary = extract_section(body, "Summary")

        nodes[entity] = {
            "id": entity,
            "layer": layer,
            "kind": meta.get("kind", "class"),
            "source": meta.get("source", ""),
            "doc": summary or "_No description available._",
        }
        registry[entity] = os.path.relpath(path, DATA_DIR).replace("\\", "/")

        # Wikilinks in the body (exclude front-matter) become outgoing edges.
        for target in WIKILINK_RE.findall(body):
            target = target.strip()
            if target and target != entity:
                raw_edges.append((entity, target))

    # Keep only edges whose target is a known node; dedupe.
    seen: set[tuple[str, str]] = set()
    edges: list[dict] = []
    for src, dst in raw_edges:
        if dst in nodes and (src, dst) not in seen:
            seen.add((src, dst))
            edges.append({"source": src, "target": dst, "type": "references"})

    graph = {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": edges}

    graph_path = os.path.join(out_dir, "graph.json")
    registry_path = os.path.join(out_dir, "registry.json")
    with open(graph_path, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)
        fh.write("\n")
    with open(registry_path, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"Graph: {len(graph['nodes'])} node(s), {len(edges)} edge(s) -> {graph_path}")
    print(f"Registry: {len(registry)} entr(y/ies) -> {registry_path}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compile a Markdown vault into graph.json/registry.json.")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Vault directory to read")
    parser.add_argument("--out", default=STRUCTURE_DIR, help="Output directory for graph.json/registry.json")
    args = parser.parse_args(argv)
    return build(args.vault, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
