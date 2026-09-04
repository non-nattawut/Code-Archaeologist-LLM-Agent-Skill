# Code Archaeologist — LLM Agent Skill

A **deterministic, Zero-RAG codebase documentation engine** packaged as an agent skill
(`code-wiki`). Instead of chopping source into arbitrary token chunks for RAG — which destroys
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
- **Architectural smell report** (`analyze.py`) — deterministic graph checks for circular
  dependencies, orphan/dead nodes (no callers, not an entry point), and backwards layer violations
  (e.g. a repository calling a controller).
- **Standalone shareable visualizer** — generates a single self-contained HTML file with the data
  embedded inline; open via `file://`, commit it, or email it. Full-screen dark canvas with a
  layer legend, search (`/`), neighbor-highlighting on click, and a **slide-in detail panel**:
  click any node to see what that method/class does, its signature, source file, and clickable
  callers/callees. Hand-editable colors.
- **Layer inference** — auto-classifies entities (controller / service / repository / model /
  client / config) for architectural coloring.
- **Zero external dependencies** — pure Python 3.10+ standard library. No `pip install`, no
  server required for the graph.

## Requirements

- **Python 3.10+** — required; the backend pipeline uses only the standard library.
- **Node.js + `@babel/parser`** — *only for frontend (JS/TS) parsing*. Install it once from the
  skill directory: `cd .agents/skills/code-wiki && npm install`. Without it, frontend files are
  skipped with a warning and the Python graph still builds.
- A modern browser to view the generated HTML (loads `force-graph` from a CDN).

## Installation

Install with `npx` — no clone or npm account required. From the root of the project you want to document, run:

```bash
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill               # interactive: pick a harness
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --harness claude   # install into .claude/skills/code-wiki
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --self-test        # install + build the demo to verify
```

Run without a flag in a terminal and you'll be prompted to choose where the skill goes.

**Supported harnesses** (pick with `--harness <name>`):

| Harness | Installs to |
| --- | --- |
| `agents` (default) | `.agents/skills/code-wiki` |
| `claude` | `.claude/skills/code-wiki` |
| `cursor` | `.cursor/skills/code-wiki` |
| `windsurf` | `.windsurf/skills/code-wiki` |
| `zed` | `.zed/skills/code-wiki` |

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

The CLI verifies Python 3.10+, copies `SKILL.md`, `scripts/`, and `templates/` into the chosen
harness folder, and creates a fresh empty `data/` workspace. It has **no npm dependencies**
(Node ≥ 16.7, built-ins only) — the skill itself still runs on Python.

## Usage

There are two commands, each building one map (scan → graph → HTML in one shot):

```bash
# Project structure map  ->  data/structure/{graph.json, vault/, graph.html}
python .agents/skills/code-wiki/scripts/archaeologist.py project --src ./src

# Request/execution flow map  ->  data/flow/{flow_graph.json, notes/, flow.html}
python .agents/skills/code-wiki/scripts/archaeologist.py flow --src ./src

# Monorepo: pass multiple roots (backend + frontend land in one graph)
python .agents/skills/code-wiki/scripts/archaeologist.py flow --src ./backend ./frontend

# ...or build both maps
python .agents/skills/code-wiki/scripts/archaeologist.py both --src ./src
```

Then trace paths or impact on either graph (structure is the default; add `--graph` for flow):

```bash
# structure: how are two classes connected?
python .agents/skills/code-wiki/scripts/trace_path.py --from OrderController --to OrderRepository

# flow: how does a request travel, method by method?
python .agents/skills/code-wiki/scripts/trace_path.py \
  --graph .agents/skills/code-wiki/data/flow/flow_graph.json \
  --from OrderController.create_order --to OrderRepository.save

# blast-radius: everything that breaks if a method changes
python .agents/skills/code-wiki/scripts/trace_path.py \
  --graph .agents/skills/code-wiki/data/flow/flow_graph.json --impact-of PaymentClient.charge
```

Keep the maps honest and review changes with three more commands:

```bash
# freshness: are the maps stale vs the current source? (rebuild if so)
python .agents/skills/code-wiki/scripts/archaeologist.py check --src ./src

# changeset blast-radius: what does my current git diff affect?
python .agents/skills/code-wiki/scripts/trace_path.py \
  --graph .agents/skills/code-wiki/data/flow/flow_graph.json --impact-of-diff

# smells: cycles, orphan/dead nodes, backwards layer violations
python .agents/skills/code-wiki/scripts/analyze.py \
  --graph .agents/skills/code-wiki/data/flow/flow_graph.json
```

Each stage is also runnable on its own (`build_wiki.py`, `build_graph.py`, `build_flow.py`,
`build_html.py`) — `archaeologist.py` just orchestrates them.

### Example

Running against the bundled `sample_src/` (a controller → service → repository/client trio):

```console
# Structure: how two classes connect
$ trace_path.py --from OrderController --to OrderRepository
{ "path": ["OrderController", "OrderService", "OrderRepository"], "found": true }

# Flow: the actual request path, method by method
$ trace_path.py --graph .../flow_graph.json --from OrderController.create_order --to OrderRepository.save
{ "path": ["OrderController.create_order", "OrderService.place_order", "OrderRepository.save"], "found": true }

# Flow blast-radius: what calls (directly or transitively) into the payment client?
$ trace_path.py --graph .../flow_graph.json --impact-of PaymentClient.charge
{ "impacted": ["OrderController.create_order", "OrderService.place_order"], "count": 2 }
```

The agent then reads only the notes on that path — e.g.
`data/flow/notes/OrderController.create_order.md`, `OrderService.place_order.md`,
`OrderRepository.save.md` — not the whole repo.

## How the agent uses it

`SKILL.md` instructs the agent to:

1. Never read raw source for architecture/flow questions.
2. Check freshness (`archaeologist.py check`) and rebuild if the source changed since last build.
3. Query the graph first with `trace_path.py` to find the exact path or blast-radius.
4. Read only the specific `data/structure/vault/<Entity>.md` notes on that path.
5. Preserve `[[EntityName]]` wikilinks in answers so responses stay cross-navigable.

## Project structure

```
.agents/skills/code-wiki/
├── SKILL.md                     # Agent instructions & tool specs
├── scripts/
│   ├── archaeologist.py         # entrypoint: `project` | `flow` | `both` | `check`
│   ├── taxonomy.py              # allowed kind/layer values (single source of truth)
│   ├── build_wiki.py            # AST scan  -> structure/vault/*.md (structure, [[wikilinks]])
│   ├── build_graph.py           # vault     -> structure/graph.json + registry.json
│   ├── build_flow.py            # AST + JS calls -> flow/flow_graph.json + flow/notes/*.md
│   ├── js_extract.js            # Node/@babel JS/TS extractor (frontend)
│   ├── js_bridge.py             # runs js_extract.js from Python (graceful fallback)
│   ├── apply_descriptions.py    # cache agent-written method summaries (by source hash)
│   ├── manifest.py              # source-freshness snapshot powering `check`
│   ├── analyze.py               # smell report: cycles, orphans, layer violations
│   ├── trace_path.py            # BFS flow (--from/--to), impact (--impact-of[-diff]), any graph
│   └── build_html.py            # <graph>.json -> standalone shareable HTML viewer
├── data/
│   ├── structure/               # structure map
│   │   ├── graph.json           #   nodes & edges
│   │   ├── registry.json        #   entity -> vault path
│   │   ├── graph.html           #   standalone viewer
│   │   └── vault/               #   notes (one per class)
│   ├── flow/                    # flow map
│   │   ├── flow_graph.json      #   method nodes & call edges (Python + JS)
│   │   ├── flow.html            #   standalone viewer
│   │   └── notes/               #   notes (one per method)
│   └── cache/                   # internal build state
│       ├── descriptions.json    #   cached AI summaries (keyed by method source hash)
│       ├── pending_descriptions.json  # methods awaiting an AI summary (transient)
│       └── manifest.json        #   source hashes for staleness detection
└── templates/
    ├── wiki_page_template.md    # page structure for generated entities
    └── TAXONOMY.md              # allowed values for each template field
bin/cli.js                       # npx installer (node, zero deps)
package.json                     # npm package metadata
sample_src/backend + frontend    # monorepo demo (Python API + TS client)
```

## Roadmap

- Frontend entities in the *structure* map (currently frontend appears in the flow map).
- Wider route/framework coverage for API-edge linking (Flask/Express/Nest/etc.).
- More languages (Java, Go); optional fully-offline viewer that embeds the graph library.

## License

See [LICENSE](LICENSE).
