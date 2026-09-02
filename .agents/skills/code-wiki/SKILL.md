---
name: code-wiki
description: Zero-RAG codebase architecture navigation, execution-flow tracing, and impact/blast-radius analysis using a local dependency graph plus bidirectional Markdown wiki pages. Use when asked how components connect, what an execution flow looks like, or what breaks if a class/method changes.
---

# Skill: Code Archaeologist & Living Wiki Navigator

## Overview
Provides zero-RAG codebase architecture navigation, execution flow tracing, and impact analysis using a local dependency graph and bidirectional Markdown wiki pages.

## Operating Principles
1. NEVER read raw source code files directly for architectural or flow-related queries.
2. ALWAYS query the graph first using `trace_path.py` to identify the exact path or blast-radius.
3. Read ONLY the specific Markdown notes in `data/vault/<Entity>.md` corresponding to nodes in the discovered path.
4. Always preserve `[[EntityName]]` wikilinks in final responses so answers are cross-navigable.

## Available Tool Commands

### 1. Trace Execution Flow
Find the architectural flow connecting two components:
```bash
python .agents/skills/code-wiki/scripts/trace_path.py --from <SourceClass> --to <TargetClass>
```
Add `--all` to enumerate every path, not just the shortest.

### 2. Blast-Radius / Impact Analysis
Find all upstream callers and endpoints affected if a class is modified:
```bash
python .agents/skills/code-wiki/scripts/trace_path.py --impact-of <ClassOrMethod>
```

### 3. Rebuild Wiki & Graph Index
Run after major codebase refactors:
```bash
python .agents/skills/code-wiki/scripts/build_wiki.py --src ./src
python .agents/skills/code-wiki/scripts/build_graph.py
```

### 4. Generate Standalone Visual Graph (HTML)
Generate/update a single self-contained HTML file with the graph data embedded inline. No server needed — open it directly, commit it, or share the file:
```bash
python .agents/skills/code-wiki/scripts/build_html.py
# custom output / title:
python .agents/skills/code-wiki/scripts/build_html.py --out data/graph.html --title "My Service Map"
```
Output defaults to `data/graph.html`. Re-run after rebuilding the graph to refresh it. The file is hand-editable (layer colors and embedded data are clearly marked) for custom visuals.

## Notes
- Zero external dependencies: all scripts use the Python 3.10+ standard library. The generated HTML loads `force-graph` from a CDN in the browser.
- The initial version parses **Python** source deterministically via the stdlib `ast` module. Java/TypeScript/Go extractors are planned but not yet implemented.
- All scripts resolve paths relative to the skill root, so they work regardless of the current working directory.
- Tool output is JSON node lists (`trace_path.py`) — use those node IDs to open only the matching `data/vault/<id>.md` notes.
