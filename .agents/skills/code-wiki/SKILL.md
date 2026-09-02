---
name: code-wiki
description: Zero-RAG codebase navigation with two maps — a project-structure graph (which classes reference which) and a method-level flow graph (which method calls which, i.e. request/execution flow). Use to explain architecture, trace how a request flows through methods, or find what breaks if a class/method changes.
---

# Skill: Code Archaeologist & Living Wiki Navigator

## Overview
Provides zero-RAG codebase navigation using local dependency graphs and Markdown wiki pages.
There are **two complementary maps**:

- **Project Structure** (class-level) — which classes/entities reference or import which.
  Data: `data/graph.json` + `data/vault/<Entity>.md`.
- **Flow / Request Flow** (method-level) — which method calls which method, so you can trace an
  actual execution/request flow such as `OrderController.create_order -> OrderService.place_order
  -> OrderRepository.save`. Each node describes what the method does. Data:
  `data/flow_graph.json` + `data/flow/<Class.method>.md`.

## Operating Principles
1. NEVER read raw source code files directly for architectural or flow-related queries.
2. Pick the right map: **structure** for "how are components organized / who uses X"; **flow**
   for "how does a request travel / what calls what / trace this execution".
3. ALWAYS query the graph first with `trace_path.py` (point `--graph` at the right graph) to find
   the exact path or blast-radius.
4. Read ONLY the specific Markdown notes for the nodes on the discovered path
   (`data/vault/<Entity>.md` for structure, `data/flow/<Class.method>.md` for flow).
5. Always preserve `[[EntityName]]` / `[[Class.method]]` wikilinks so answers are cross-navigable.
6. **Keep the maps current.** Whenever project source is added, changed, or deleted (e.g. after
   you edit code), re-run the relevant build so the graphs and HTML match the code — see
   "Keeping the maps current" below. Do this before answering flow/impact questions if the code
   has changed since the last build.

## Available Tool Commands

### 1. Build the Project Structure map  (`/archaeologist-project-structure`)
Which classes reference/import which → `graph.json`, `vault/`, `graph.html`:
```bash
python .agents/skills/code-wiki/scripts/archaeologist.py project --src ./src
```

### 2. Build the Flow / Request-Flow map  (`/archaeologist-flow-structure`)
Method-level call graph → `flow_graph.json`, `flow/`, `flow.html`:
```bash
python .agents/skills/code-wiki/scripts/archaeologist.py flow --src ./src
```
Build both at once with `... archaeologist.py both --src ./src`.

### 3. Trace Execution Flow
Find the path connecting two components. Structure uses the default graph; flow needs `--graph`:
```bash
# structure (class -> class)
python .agents/skills/code-wiki/scripts/trace_path.py --from <SourceClass> --to <TargetClass>

# request flow (method -> method)
python .agents/skills/code-wiki/scripts/trace_path.py \
  --graph .agents/skills/code-wiki/data/flow_graph.json \
  --from OrderController.create_order --to OrderRepository.save
```
Add `--all` to enumerate every path.

### 4. Blast-Radius / Impact Analysis
All upstream callers affected if a class or method changes:
```bash
# class-level
python .agents/skills/code-wiki/scripts/trace_path.py --impact-of <ClassName>

# method-level
python .agents/skills/code-wiki/scripts/trace_path.py \
  --graph .agents/skills/code-wiki/data/flow_graph.json --impact-of <Class.method>
```

### 5. Regenerate / Refresh the HTML viewers
`archaeologist.py` regenerates the HTML automatically. To rebuild a viewer alone:
```bash
python .agents/skills/code-wiki/scripts/build_html.py --graph <graph.json> --out <out.html> --title "..."
```

## Keeping the maps current (hybrid AI descriptions)

The graph *structure* (nodes, edges, signatures, calls) is always extracted deterministically by
AST — fast, exact, zero tokens. Method *descriptions* are resolved cheapest-source-first:
docstring → cached AI summary (valid while the method's source hash is unchanged) → deterministic
fallback. This means **the AI only writes a summary for methods that are new or changed**, and
only when they lack a docstring; everything else is free.

After any code add/change/delete, refresh a map:

1. Rebuild (AST + cache), which also detects what needs describing:
   ```bash
   python .agents/skills/code-wiki/scripts/archaeologist.py flow --src ./src
   ```
2. If the output reports **pending** descriptions, open `data/pending_descriptions.json`
   (each entry has the method's `signature` + `code`), write a concise one-line summary of what
   each method does, and save them as JSON `{ "<Class.method>": "<summary>", ... }`, then:
   ```bash
   python .agents/skills/code-wiki/scripts/apply_descriptions.py --input <your_summaries.json>
   python .agents/skills/code-wiki/scripts/archaeologist.py flow --src ./src   # rebuild to fold them in
   ```
   Summaries are cached in `data/descriptions.json` (keyed by source hash), so unchanged methods
   are never re-described. Deleted methods are pruned automatically.
3. If there are **0 pending**, you're done — the graph, notes, and `flow.html` are up to date.

## Notes
- Zero external dependencies: all scripts use the Python 3.10+ standard library. The generated HTML
  loads `force-graph` from a CDN in the browser.
- The initial version parses **Python** deterministically via the stdlib `ast` module.
- Flow call resolution is heuristic (no full type inference): it resolves `self.<dep>.m()` via
  `__init__` type hints/assignments, typed params/locals, and same-class `self.m()` calls;
  unresolved external/stdlib calls are dropped to keep the graph readable.
- `describe()` in `build_flow.py` is the marked hook where an LLM can later generate richer
  method summaries.
- All scripts resolve paths relative to the skill root, so they work from any working directory.
