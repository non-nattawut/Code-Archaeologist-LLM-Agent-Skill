# Code Archaeologist — LLM Agent Skill

A **deterministic, Zero-RAG codebase documentation engine** packaged as an agent skill
(`code-archaeologist`). Instead of chopping source into arbitrary token chunks for RAG — which destroys
function scopes, call hierarchies, and execution context — Code Archaeologist scans code
structure, compiles a hyperlinked Markdown wiki, and builds an explicit dependency graph an
agent can query.

When an agent needs to answer *"how does the controller reach the database?"* or *"what breaks
if I change this class?"*, it doesn't read the whole repo. It runs a graph trace (~100 tokens),
gets the exact 3–5 relevant nodes, and reads only those Markdown notes (~1,500 tokens) — a
**90%+ reduction in tokens** versus scanning source.

## Why Zero-RAG?

| Standard RAG | Code Archaeologist |
| --- | --- |
| Splits code into ~500-token chunks | Keeps whole entities intact as one note each |
| Loses call hierarchy & scope | Encodes relationships as an explicit graph |
| Similarity search, non-deterministic | Deterministic BFS graph traversal |
| Re-reads large context per query | Reads only the nodes on the traced path |

## Features

- **Two complementary maps:**
  - **Project Structure** (class-level) — which classes/entities reference or import which.
  - **Request / Execution Flow** (method-level) — which method calls which method, resolved from
    the code, so you can trace an actual flow like
    `OrderController.create_order → OrderService.place_order → OrderRepository.save`. Every node
    describes *what that method does* (docstring or auto-summary), its signature, callers, and
    callees.
- **Backend + frontend, monorepo-aware, cross-stack** — `--src` accepts multiple roots
  (`--src ./backend ./frontend`), and both land in one graph. Python (`.py`) is parsed by the
  stdlib AST; JS/TS (`.js/.jsx/.ts/.tsx`) by a Node/`@babel/parser` extractor. Frontend
  `fetch`/`axios` calls are **linked to the matching backend route handler** (method + path), so a
  single trace crosses the whole stack:
  `submitOrder → createOrder → OrderController.create_order → OrderService.place_order → OrderRepository.save`.
- **AST-based scanner** — parses Python with the standard-library `ast` module (accurate, no
  guessing), extracting classes, methods, docstrings, bases, decorators, and imports.
- **Heuristic call resolution** — resolves `self.<dep>.method()` via `__init__` type hints,
  typed params/locals, and same-class `self.method()` calls; controller methods are marked as
  `endpoint` roots so request flows have a clear entry point.
- **Hybrid descriptions (AST + optional AI), cached & incremental** — node descriptions come from,
  cheapest first: the docstring → a cached AI summary (valid while the method's source hash is
  unchanged) → a deterministic fallback. The AI only writes summaries for methods that are *new or
  changed and undocumented*; unchanged methods are never re-described and deletions are pruned —
  so keeping the map current after a code change costs only the diff.
- **Bidirectional Markdown vault** — one `[[wikilink]]`-cross-referenced note per entity (and per
  method for the flow map), compatible with Obsidian and any Markdown viewer.
- **Explicit dependency graphs** — `graph.json` / `flow_graph.json` (nodes + edges) and
  `registry.json`, compiled deterministically.
- **Execution-flow tracing** — shortest path (or all paths) between any two components, at class
  *or* method granularity.
- **Blast-radius / impact analysis** — reverse-traversal listing every upstream caller affected
  by a change, for a class, a specific method, or an **entire git diff** (`--impact-of-diff` maps
  changed files to nodes and unions their impact — "what does this PR affect?").
- **Staleness guard** — every build records a content-hash of the source it scanned;
  `archaeologist.py check` re-scans and reports whether the maps are stale (and exactly which files
  changed) before you trust a trace, so answers are never built on a drifted graph.
- **Architectural smell report + health grade** (`analyze.py`) — deterministic graph checks for
  circular dependencies, orphan/dead nodes (no callers, not an entry point), backwards layer
  violations (e.g. a repository calling a controller), high-coupling hubs and god objects, plus
  name-based idiom detection (singleton / factory / observer / React hook) and a **0-100 health
  score with an A-F grade** that folds in the risk findings below.
- **Risk / security scan** (`scan_security.py`) — a deterministic line sweep for hardcoded
  secrets, SQL built by string interpolation, `eval` / `new Function` / `innerHTML` sinks, and
  leftover debug statements. Every finding is **attributed to the graph node that owns the line**,
  so a risk can be traced and blast-radiused like any other node; tests/fixtures/docs are skipped
  and secret values are redacted.
- **Orientation brief** (`archaeologist.py brief`) — the whole codebase as a ~35-line digest:
  counts and grade per map, staleness, size, entry points, and the top longest / most complex /
  most churned / riskiest nodes. Fixed size regardless of repo size, so an agent can start every
  session with it instead of reading the full report.
- **Graph-aware search** (`search.py`) — find nodes by name, description, file, layer, kind,
  language or connectivity (`--calls X`, `--called-by X`, `--orphans`) and get ids back, so
  "where is X handled" never becomes a grep over source.
- **Compact answers by default** — `trace_path.py` prints `A > B > C` and `analyze.py --format text`
  prints the grade, the counts and the lists; `--format json` is there when something machine-reads
  the output.
- **One-call context packs** (`context.py`) — everything known about a node in a single budgeted
  block: facts, size and complexity, churn and owner, description, immediate callers and callees
  *each with their own description*, and the risks attributed to it. `--diff` packs every node the
  current changeset touches. Replaces "trace, then open five notes".
- **Size & complexity** (`metrics.py`) — lines per file split into code / comment / blank plus
  the language mix, and for every Python node its LOC, cyclomatic complexity, nesting depth and
  parameter count. Node entries are **keyed like the graph nodes**, so "the longest and most
  tangled code in this repo" is a lookup, not a source read.
- **Polyglot where it can be** — the graphs need an extractor (Python, JS/TS), but lines,
  complexity, risk scan, debt markers and test detection also read Java, Kotlin, Go, Rust, C#,
  Ruby, PHP, Swift, Scala, Dart, Elixir and C/C++.
- **Debt inventory** (`debt.py`) — TODO / FIXME / HACK / XXX / BUG / DEPRECATED markers found in
  comments and attributed to the node that owns the line, plus dead code: nodes nothing calls and
  files where *every* node is dead.
- **Test coverage map** (`tests_map.py`) — which nodes the test suite names and which it never
  mentions. Name-based, so there is no runner and nothing to install: a `Class.method` counts when
  a test file names both the class and the method. Test files are recognized across languages —
  pytest, Jest/Vitest, **JUnit 5 / Spring Boot** (`OrderServiceTest.java`, `@SpringBootTest`), Go
  (`*_test.go`), Rust (`#[test]`), .NET (`[Fact]`), RSpec, PHPUnit — and their nodes are tagged
  `layer: test`, so **test code is never reported as dead code**.
- **Churn, ownership & hotspots** (`git_insights.py`) — one `git log --numstat` pass gives commits
  per file, the top author per file, and a **hotspot ranking** (`risk = commits x (1 + fan_in +
  fan_out)`): the code that changes most *and* has the most callers. Degrades to empty data outside
  a git repo.
- **One-shot architecture report** (`archaeologist.py report`) — census (files, lines, language
  mix), health grade, smells, anti-patterns, risk findings and hotspots joined into
  `data/report/<map>/architecture_report.md` (plus `.json`, `security.json`, `insights.json`, one
  set per map) — a review artifact you can paste into a PR, the data behind the explorer's panels,
  and the cheapest way for an agent to answer "how healthy is this codebase?".
- **Standalone code explorer (single HTML file)** — **both maps in one page**, switched from the
  header (Structure / Flow); everything embedded inline; open via `file://`, commit it, or email it.
  No server, no repo access, works offline. It's a three-pane IDE-style UI:
  - **Left** — A–F **health ring**, color-by selector (layer / folder / churn / risk), stat tiles
    (files, functions, links, unused), **lines of code + language mix**, and a **file explorer
    tree** that filters the canvas (with per-file risk counts).
  - **Center** — seven views of the same graph: **Graph** (force), **Treemap** (folders → files by
    size), **Matrix** (adjacency), **Tree** (top-down DAG), **Flow** (left-right DAG), **Cluster**
    (grouped by folder), **Bundle** (radial). Plus **folder hulls** with path labels, a
    **blast-radius toggle** (transitive impact, not just neighbors), zoom/fit controls, **PNG
    export**, and a status bar (files · nodes · links · affected).
  - **Right** — **FILE / PATTERNS / SECURITY** tabs. FILE shows what the node does, its signature
    and source, **blast radius** (severity badge, impact bar, affected list, propagation depth),
    **connections**, **git ownership** (owner, contributors, last change), **functions in the file**
    with internal/external call counts, and its risk findings. PATTERNS lists cycles, layer
    violations, hubs, god objects, dead nodes and idioms; SECURITY lists findings by severity —
    both click straight through into FILE (with a "← Back to Issues" link).
  - Risky nodes get a red/amber ring; the page layout lives in `templates/viewer.html`, so it can
    be restyled without touching Python.
- **Layer inference** — auto-classifies entities (controller / service / repository / model /
  client / config) for architectural coloring.
- **Zero external dependencies** — pure Python 3.10+ standard library. No `pip install`, no
  server required for the graph.

## Requirements

- **Python 3.10+** — required; the backend pipeline uses only the standard library.
- **Node.js + `@babel/parser`** — *only for frontend (JS/TS) parsing*. Install it once from the
  skill directory: `cd .agents/skills/code-archaeologist && npm install`. The resulting `node_modules/` is
  git-ignored by the skill's own `.gitignore`. Without it, frontend files are skipped with a
  warning and the Python graph still builds.
- **git** — *optional*; only for churn/ownership/hotspots. Outside a git repo the report is built
  without them.
- A modern browser to view the generated HTML (loads `force-graph` from a CDN).

## Installation

Install with `npx` — no clone or npm account required. From the root of the project you want to document, run:

```bash
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill               # interactive: pick a harness
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --harness claude   # install into .claude/skills/code-archaeologist
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --self-test        # install + build the demo to verify
```

Run without a flag in a terminal and you'll be prompted to choose where the skill goes.

**Supported harnesses** (pick with `--harness <name>`):

| Harness | Installs to |
| --- | --- |
| `agents` (default) | `.agents/skills/code-archaeologist` |
| `claude` | `.claude/skills/code-archaeologist` |
| `cursor` | `.cursor/skills/code-archaeologist` |
| `windsurf` | `.windsurf/skills/code-archaeologist` |
| `zed` | `.zed/skills/code-archaeologist` |

Anything else? Use `--dir <path>` for a fully custom location.

Useful flags:

| Flag | Description |
| --- | --- |
| `--harness <name>` | Target harness (see table above) |
| `--dir <path>` | Custom install path (overrides `--harness`) |
| `--target <dir>` | Project root to install into (default: current directory) |
| `--self-test` | After installing, build the bundled `sample_src/` demo end to end |
| `--force` | Overwrite an existing `data/` workspace (default: keep it) |
| `--help` | Show usage |

The CLI verifies Python 3.10+, copies `SKILL.md`, `scripts/`, `templates/` and a `.gitignore` into
the chosen harness folder, and creates a fresh empty `data/` workspace. That `.gitignore` keeps the
skill's `node_modules/` (the frontend parser) and its build state out of your repo, while leaving
the generated maps under `data/` committable. It has **no npm dependencies**
(Node ≥ 16.7, built-ins only) — the skill itself still runs on Python.

## Usage

One command builds both maps; a second reviews them. Point `--src` at your source root(s):

```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py both   --src ./src
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./src
```

Then open `.agents/skills/code-archaeologist/data/explorer.html`, or let the agent answer from the
graphs and notes.

**Full command reference — tracing, blast radius, freshness, scans, hotspots, worked example:
[USAGE.md](USAGE.md).** The agent's own instructions (same commands, plus when to use each) live in
[`SKILL.md`](.agents/skills/code-archaeologist/SKILL.md).

## How the agent uses it

`SKILL.md` instructs the agent to:

1. Run the setup preflight (Python 3.10+; `npm install` for the frontend parser only when the
   project has JS/TS) before the first build.
2. Never read raw source for architecture/flow questions.
3. Check freshness (`archaeologist.py check`) and rebuild if the source changed since last build,
   then orient with `archaeologist.py brief` rather than reading the full report.
4. Find the nodes with `search.py`, then query the graph with `trace_path.py` for the exact path
   or blast-radius.
5. Pull the whole picture for those nodes in one call with `context.py`, and read individual
   `data/structure/vault/<Entity>.md` notes only when it needs more.
6. Preserve `[[EntityName]]` wikilinks in answers so responses stay cross-navigable.
7. For review questions ("is this healthy?", "where's the risk?", "what should we refactor
   first?"), run `archaeologist.py report` and answer from
   `data/report/<map>/architecture_report.md`.

## Project structure

The skill is one folder: instructions (`SKILL.md`), scripts grouped by role, the page/notes
templates, and the generated `data/` workspace.

```
.agents/skills/code-archaeologist/
|-- SKILL.md                      # agent instructions & tool specs (paths rewritten on install)
|-- .gitignore                    # keeps node_modules/ + build state out of your repo
|-- scripts/
|   |-- archaeologist.py          # entrypoint: project | flow | both | check | report
|   |-- taxonomy.py               # allowed kind/layer values (single source of truth)
|   |   # --- extract (source -> graphs & notes) ---
|   |-- build_wiki.py             # AST scan      -> structure/vault/*.md ([[wikilinks]])
|   |-- build_graph.py            # vault         -> structure/graph.json + registry.json
|   |-- build_flow.py             # AST + JS calls-> flow/flow_graph.json + flow/notes/*.md
|   |-- js_extract.js             # Node/@babel JS/TS extractor (frontend)
|   |-- js_bridge.py              # runs js_extract.js from Python (graceful fallback)
|   |-- apply_descriptions.py     # cache agent-written method summaries (by source hash)
|   |-- manifest.py               # source-freshness snapshot powering `check`
|   |   # --- review (graphs -> findings) ---
|   |-- analyze.py                # smells, anti-patterns, idioms, A-F health grade
|   |-- scan_security.py          # risk scan -> findings attributed to graph nodes
|   |-- git_insights.py           # git churn/ownership -> hotspot ranking
|   |-- metrics.py                # lines per file, LOC/complexity/depth per node
|   |-- debt.py                   # TODO-style markers + dead code inventory
|   |-- tests_map.py              # which nodes the tests name (name-based coverage)
|   |-- brief.py                  # fixed-size digest of the built maps (`brief`)
|   |-- report.py                 # all of the above -> report/<map>/architecture_report.*
|   |   # --- query & render ---
|   |-- trace_path.py             # BFS flow (--from/--to), impact (--impact-of[-diff])
|   |-- context.py               # one budgeted pack per node (facts + neighbors + risks)
|   |-- search.py                # find nodes by name/doc/layer/kind/connectivity
|   |-- console.py               # keeps stdout alive on a non-UTF-8 console
|   `-- build_html.py             # graphs + reports -> data/explorer.html (both maps)
|-- templates/
|   |-- viewer.html               # the explorer page (HTML/CSS/JS, 2 placeholders)
|   |-- wiki_page_template.md     # page structure for generated entities
|   `-- TAXONOMY.md               # allowed values for each field
`-- data/
    |-- explorer.html             # THE viewer: both maps in one page, switched from its header
    |-- structure/                # structure map: graph.json, registry.json, vault/
    |-- flow/                     # flow map: flow_graph.json, notes/
    |-- report/
    |   |-- structure/            # report for the structure map
    |   `-- flow/                 #   architecture_report.md/.json, security.json, insights.json
    `-- cache/                    # descriptions.json, pending_descriptions.json, manifest.json

bin/cli.js                        # npx installer (node, zero deps)
package.json                      # npm package metadata
sample_src/backend + frontend     # monorepo demo (Python API + TS client)
```

## Roadmap

- Frontend entities in the *structure* map (currently frontend appears in the flow map).
- Wider route/framework coverage for API-edge linking (Flask/Express/Nest/etc.).
- More languages (Java, Go); optional fully-offline viewer that embeds the graph library.

## License

See [LICENSE](LICENSE).
