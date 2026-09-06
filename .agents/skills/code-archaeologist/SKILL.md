---
name: code-archaeologist
description: Zero-RAG codebase navigation with two maps — a project-structure graph (which classes reference which) and a method-level flow graph (which method calls which, i.e. request/execution flow), plus a review pass (health grade, risk scan, git hotspots). Use to explain architecture, trace how a request flows through methods, find what breaks if a class/method changes, or review a codebase for smells, risky code and change hotspots.
---

# Skill: Code Archaeologist & Living Wiki Navigator

## Overview
Provides zero-RAG codebase navigation using local dependency graphs and Markdown wiki pages.
There are **two complementary maps**:

- **Project Structure** (class-level) — which classes/entities reference or import which.
  Data: `data/structure/graph.json` + `data/structure/vault/<Entity>.md`.
- **Flow / Request Flow** (method-level) — which method calls which method, so you can trace an
  actual execution/request flow such as `OrderController.create_order -> OrderService.place_order
  -> OrderRepository.save`. Each node describes what the method does. Data:
  `data/flow/flow_graph.json` + `data/flow/notes/<Class.method>.md`.

`data/` is organized by map: `structure/` (class graph + vault), `flow/` (call graph + `notes/`),
`report/<map>/` (the review pass for that map: architecture report, risk scan, git insights), and
`cache/` (internal AI-summary cache + source-freshness manifest — you rarely touch these directly).
Both maps share ONE viewer, `data/explorer.html`, switched from its header.

## Setup — run this preflight before the first build

Do this once per machine/checkout, **before** the first `project` / `flow` / `both` build. Both
steps are cheap and idempotent; skip nothing, then report to the user what is available.

**1. Python 3.10+ — required, nothing to install.** The whole `.py` pipeline is stdlib:
```bash
python --version        # or python3 --version; needs 3.10 or newer
```
If Python is older than 3.10 or missing, stop and tell the user — the skill cannot run.

**2. `@babel/parser` — required only for frontend (`.js/.jsx/.ts/.tsx`) code.** Skip this entirely
for a Python-only project. Otherwise check whether the parser already resolves, and install it if
it does not:
```bash
# check (run from the skill directory)
cd .agents/skills/code-archaeologist && node -e "require('@babel/parser'); console.log('parser ok')"

# install if that failed
cd .agents/skills/code-archaeologist && npm install
```
`npm install` pulls the single dependency declared in the skill's own `package.json` into
`<skill>/node_modules`, which the skill's `.gitignore` keeps out of commits. **Install it yourself
— don't ask the user to.**

If **Node itself** is missing, do not stop: run the build anyway. Frontend files are skipped with a
one-line warning and the backend graph is still produced — just tell the user that installing
Node.js would add the frontend half of the map (and the cross-stack `http` edges).

## Operating Principles
1. NEVER read raw source code files directly for architectural or flow-related queries.
2. Pick the right map: **structure** for "how are components organized / who uses X"; **flow**
   for "how does a request travel / what calls what / trace this execution".
3. ALWAYS query the graph first with `trace_path.py` (point `--graph` at the right graph) to find
   the exact path or blast-radius.
4. Then pull the facts in ONE call with `context.py --node <id>` (Command 6) instead of opening
   notes one at a time. Read individual notes
   (`data/structure/vault/<Entity>.md`, `data/flow/notes/<Class.method>.md`) only when the pack is
   not enough — and only for nodes on the discovered path.
5. Always preserve `[[EntityName]]` / `[[Class.method]]` wikilinks so answers are cross-navigable.
6. **Check freshness before trusting the maps.** Before answering a flow/impact question, run
   `archaeologist.py check --src <roots>` (Command 8). If it reports `stale`, rebuild the relevant
   map first — see "Keeping the maps current" — so the graphs and HTML match the current code.
7. For **review** questions ("is this codebase healthy?", "where is the risk?", "what should
   we refactor first?"), run the report (Command 13), then read the **brief** (Command 1) and
   go to `data/report/<map>/architecture_report.md` only for the detail it points at — still
   without reading raw source.

## Available Tool Commands

> First build in this project? Run the **Setup preflight** above first.

### 1. Orientation brief — start here
A fixed-size digest of whatever is already built: node/edge counts and grade per map, staleness,
size, entry points, and the top few longest / most complex / most churned / riskiest nodes. It
reads the artifacts, computes nothing, and costs the same on a 200-file repo as on a 5-file one —
so use it instead of reading `architecture_report.json`:
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py brief --src ./src
```
`--map structure` switches which map the detail sections describe, `--top N` how many rows each
gets, `--json` emits the same digest for tooling. Read the full report only when the brief points
you at something you need the detail for.

### 2. Build the Project Structure map
Which classes reference/import which → `graph.json`, `vault/` (+ `explorer.html`):
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py project --src ./src
```

### 3. Build the Flow / Request-Flow map
Method-level call graph → `flow/flow_graph.json`, `flow/notes/` (+ `explorer.html`):
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./src
```
Build both at once with `... archaeologist.py both --src ./src`.

**Monorepo & frontend.** `--src` accepts multiple roots, so backend and frontend land in one
graph:
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./backend ./frontend
```
Python (`.py`) is parsed by the stdlib AST. JS/TS (`.js/.jsx/.ts/.tsx`) is parsed by the Node
extractor (`js_extract.js`, needs Node + `@babel/parser` resolvable from the project); if Node or
the parser is missing, frontend files are skipped with a warning and the Python graph still builds.
Node `source` fields are prefixed with their root area (e.g. `backend/…`, `frontend/…`).

Frontend `fetch`/`axios` calls are linked to backend route handlers (`@router.post("/orders")`,
`@app.route(..., methods=[...])`, etc.) by matching HTTP method + normalized path, producing
cross-stack `http` edges. So a single flow trace can run frontend → API → service → repository:
```bash
python .agents/skills/code-archaeologist/scripts/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --from submitOrder --to OrderRepository.save
```

### 4. Trace Execution Flow
Find the path connecting two components. Structure uses the default graph; flow needs `--graph`:
```bash
# structure (class -> class)
python .agents/skills/code-archaeologist/scripts/trace_path.py --from <SourceClass> --to <TargetClass>

# request flow (method -> method)
python .agents/skills/code-archaeologist/scripts/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json \
  --from OrderController.create_order --to OrderRepository.save
```
Add `--all` to enumerate every path.

### 5. Blast-Radius / Impact Analysis
All upstream callers affected if a class or method changes:
```bash
# class-level
python .agents/skills/code-archaeologist/scripts/trace_path.py --impact-of <ClassName>

# method-level
python .agents/skills/code-archaeologist/scripts/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --impact-of <Class.method>
```

**Blast-radius of a whole changeset (git diff).** For "what does this PR/edit affect?", map the
changed files to nodes and union their impact in one shot. Works on either graph:
```bash
# uncommitted working-tree changes (default)
python .agents/skills/code-archaeologist/scripts/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --impact-of-diff
# staged changes, or against a base ref
python .agents/skills/code-archaeologist/scripts/trace_path.py --impact-of-diff --staged
python .agents/skills/code-archaeologist/scripts/trace_path.py --impact-of-diff --base origin/main
```
Reports `changed_nodes` (nodes in the edited files) and `impacted` (everything upstream of them).

### 6. Context pack for a node (one call, budgeted)
Everything known about a node, assembled from the artifacts: kind/layer/source, size and
complexity, churn and owner, its description, its immediate callers and callees *each with their
own one-line description*, and the risk findings attributed to it. This replaces "trace, then open
five notes":
```bash
python .agents/skills/code-archaeologist/scripts/context.py --node OrderService.place_order
python .agents/skills/code-archaeologist/scripts/context.py --node A B --depth 2 --max-chars 8000
python .agents/skills/code-archaeologist/scripts/context.py --diff        # every node the diff touches
```
`--max-chars` (default 6000) is a hard budget: neighbor lists shrink until the pack fits, and it
says when it trimmed. `--graph` selects the map (default: flow). `--format json` for tooling.

### 7. Regenerate / Refresh the HTML explorer
`archaeologist.py` regenerates `data/explorer.html` automatically. To rebuild it alone (it picks
up both maps and both reports from the standard paths):
```bash
python .agents/skills/code-archaeologist/scripts/build_html.py
```
One page holds **both maps**; its header switches between Structure and Flow, and the whole UI
(grade, tiles, explorer tree, canvas, tabs) re-renders for the active map. Layout: health grade +
stat tiles + language mix + file tree on the left; seven views of the graph in the middle (Graph,
Treemap, Matrix, Tree, Flow, Cluster, Bundle) with folder hulls, a blast-radius toggle and PNG
export; FILE / PATTERNS / SECURITY tabs on the right (blast radius with an impact bar, connections,
git ownership, sibling functions with internal/external call counts, risk findings). A map with no
report still renders — just without the grade, churn/risk colors and the two review tabs. The page
itself lives in `templates/viewer.html`, so it can be restyled without touching Python.

### 8. Check freshness (are the maps stale?)
Before trusting a trace/impact answer, confirm the maps match the current source. Returns
`{stale, changed, added, deleted}` — tiny and deterministic. Rebuild if `stale` is true:
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py check --src ./src
```

### 9. Architectural smell report & health grade
Deterministic checks over a graph — circular dependencies, orphan/dead nodes (no callers, not an
entry point), backwards layer violations (e.g. a repository calling a controller), high-coupling
hubs, god objects, name-based idioms (singleton/factory/observer/React hook), and a 0-100 health
score with an A-F grade (pass `--security <security.json>` to fold risk findings into the grade):
```bash
# structure graph (default)
python .agents/skills/code-archaeologist/scripts/analyze.py
# flow graph
python .agents/skills/code-archaeologist/scripts/analyze.py --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json
```

### 10. Risk / security scan
Deterministic line scan for hardcoded secrets, interpolated SQL, `eval`/`innerHTML` sinks and
leftover debug statements. Each finding names the graph node that owns the line, so it can be
traced and blast-radiused like anything else (tests/fixtures/docs are skipped, secrets redacted):
```bash
python .agents/skills/code-archaeologist/scripts/scan_security.py --src ./src
```
Add `--graph <flow_graph.json>` to attribute findings to method nodes instead of classes, or
`--out <file.json>` to save the report.

### 11. Churn, ownership & hotspots (git)
Joins git history onto the graph: commits per file, top author per file, and a hotspot ranking
where `risk = commits x (1 + fan_in + fan_out)` — code that changes often *and* has many callers:
```bash
python .agents/skills/code-archaeologist/scripts/git_insights.py --src ./src --top 10
```
Outside a git repo it returns empty data with a note instead of failing.

### 12. Size & complexity (lines of code)
Line counts per file (total / code / comment / blank + language mix) and, for Python nodes,
LOC, cyclomatic complexity, nesting depth and parameter count — keyed by the same node ids the
graphs use, so "how long / how tangled is `OrderService.place_order`" is answered without
opening a file:
```bash
python .agents/skills/code-archaeologist/scripts/metrics.py --src ./src --top 10
python .agents/skills/code-archaeologist/scripts/metrics.py --src ./src --out <path>.json
```
Pass `--graph <graph.json>` to rank only that map's nodes (methods for flow, classes for
structure). The full report command below runs this for you and writes `data/report/<map>/metrics.json`.

### 13. Full architecture report
One review pass per built map — census, health grade, smells, anti-patterns, risk findings and
hotspots, plus size and complexity — written to `data/report/<map>/architecture_report.md`
(+ `.json`, `security.json`, `insights.json`, `metrics.json`; `<map>` is `structure` or `flow`). It also re-renders `data/explorer.html` with
both reports embedded, which turns on the health ring, churn/risk color modes, ownership and the
Patterns/Security tabs:
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./src
```
Use this for "review this codebase", "where is the risk", "what should we refactor first" —
then read the Markdown report instead of any source.

## Keeping the maps current (hybrid AI descriptions)

The graph *structure* (nodes, edges, signatures, calls) is always extracted deterministically by
AST — fast, exact, zero tokens. Method *descriptions* are resolved cheapest-source-first:
docstring → cached AI summary (valid while the method's source hash is unchanged) → deterministic
fallback. This means **the AI only writes a summary for methods that are new or changed**, and
only when they lack a docstring; everything else is free.

After any code add/change/delete, refresh a map:

1. Rebuild (AST + cache), which also detects what needs describing:
   ```bash
   python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./src
   ```
2. If the output reports **pending** descriptions, open `data/cache/pending_descriptions.json`
   (each entry has the method's `signature` + `code`), write a concise one-line summary of what
   each method does, and save them as JSON `{ "<Class.method>": "<summary>", ... }`, then:
   ```bash
   python .agents/skills/code-archaeologist/scripts/apply_descriptions.py --input <your_summaries.json>
   python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./src   # rebuild to fold them in
   ```
   Summaries are cached in `data/cache/descriptions.json` (keyed by source hash), so unchanged methods
   are never re-described. Deleted methods are pruned automatically.
3. If there are **0 pending**, you're done — the graph, notes, and `explorer.html` are up to date.

## Notes
- Zero external dependencies for the **Python** pipeline (stdlib only). **Frontend** parsing is the
  one exception: it needs Node + `@babel/parser`. The generated HTML loads `force-graph` from a CDN.
- Backend is parsed deterministically via the stdlib `ast` module; frontend via `@babel/parser`.
- Field values (`kind`, `layer`, `lang`, `desc_source`, plus the review-pass `severity`/`rule`/
  `grade` sets) come from `scripts/taxonomy.py` and `scripts/scan_security.py`; see
  `templates/TAXONOMY.md` for the allowed values. Keep them consistent by editing those, not
  individual pages.
- Flow call resolution is heuristic (no full type inference): it resolves `self.<dep>.m()` via
  `__init__` type hints/assignments, typed params/locals, and same-class `self.m()` calls.
  Calls that stay unresolved (libraries, stdlib) become no edge — they are counted per node as
  `ext`, which the explorer shows as "N ext" next to "N int".
- `resolve_descriptions()` in `build_flow.py` is where descriptions are chosen (docstring → cached
  AI summary → `_auto_summary()` fallback); that is the hook for richer summaries.
- All scripts resolve paths relative to the skill root, so they work from any working directory.
