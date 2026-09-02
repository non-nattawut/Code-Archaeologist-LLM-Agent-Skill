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
- **Backend + frontend, monorepo-aware** — `--src` accepts multiple roots
  (`--src ./backend ./frontend`), and both land in one graph. Python (`.py`) is parsed by the
  stdlib AST; JS/TS (`.js/.jsx/.ts/.tsx`) is parsed by a Node/`@babel/parser` extractor. Frontend
  `fetch`/`axios` HTTP calls are captured on each node (used for backend API-edge linking).
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
  by a change, for a class or a specific method.
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
- **Node.js + `@babel/parser`** — *only for frontend (JS/TS) parsing*. Without it, frontend files
  are skipped with a warning and the Python graph still builds. `@babel/parser` just needs to be
  resolvable from the project (most frontend projects already have it; this repo installs it via
  `npm install`).
- A modern browser to view the generated HTML (loads `force-graph` from a CDN).

## Installation

Install with `npx` — no clone required. From the root of the project you want to document, run:

```bash
npx code-archaeologist-skill               # interactive: pick a harness
npx code-archaeologist-skill --harness claude   # install into .claude/skills/code-wiki
npx code-archaeologist-skill --self-test        # install + build the demo to verify
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
# Project structure map  ->  data/graph.json, data/vault/, data/graph.html
python .agents/skills/code-wiki/scripts/archaeologist.py project --src ./src

# Request/execution flow map  ->  data/flow_graph.json, data/flow/, data/flow.html
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
  --graph .agents/skills/code-wiki/data/flow_graph.json \
  --from OrderController.create_order --to OrderRepository.save

# blast-radius: everything that breaks if a method changes
python .agents/skills/code-wiki/scripts/trace_path.py \
  --graph .agents/skills/code-wiki/data/flow_graph.json --impact-of PaymentClient.charge
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
`data/flow/OrderController.create_order.md`, `OrderService.place_order.md`,
`OrderRepository.save.md` — not the whole repo.

## How the agent uses it

`SKILL.md` instructs the agent to:

1. Never read raw source for architecture/flow questions.
2. Query the graph first with `trace_path.py` to find the exact path or blast-radius.
3. Read only the specific `data/vault/<Entity>.md` notes on that path.
4. Preserve `[[EntityName]]` wikilinks in answers so responses stay cross-navigable.

## Project structure

```
.agents/skills/code-wiki/
├── SKILL.md                     # Agent instructions & tool specs
├── scripts/
│   ├── archaeologist.py         # entrypoint: `project` | `flow` | `both`
│   ├── taxonomy.py              # allowed kind/layer values (single source of truth)
│   ├── build_wiki.py            # AST scan  -> data/vault/*.md (structure, [[wikilinks]])
│   ├── build_graph.py           # vault     -> graph.json + registry.json
│   ├── build_flow.py            # AST + JS calls -> flow_graph.json + data/flow/*.md
│   ├── js_extract.js            # Node/@babel JS/TS extractor (frontend)
│   ├── js_bridge.py             # runs js_extract.js from Python (graceful fallback)
│   ├── apply_descriptions.py    # cache agent-written method summaries (by source hash)
│   ├── trace_path.py            # BFS flow (--from/--to) & impact (--impact-of), any graph
│   └── build_html.py            # <graph>.json -> standalone shareable HTML viewer
├── data/
│   ├── graph.json               # structure: nodes & edges
│   ├── flow_graph.json          # flow: method nodes & call edges (Python + JS)
│   ├── registry.json            # entity -> vault path
│   ├── descriptions.json        # cached AI summaries (keyed by method source hash)
│   ├── graph.html / flow.html   # generated standalone viewers
│   ├── vault/                   # structure notes (one per class)
│   └── flow/                    # flow notes (one per method)
└── templates/
    ├── wiki_page_template.md    # page structure for generated entities
    └── TAXONOMY.md              # allowed values for each template field
bin/cli.js                       # npx installer (node, zero deps)
package.json                     # npm package metadata
sample_src/backend + frontend    # monorepo demo (Python API + TS client)
```

## Roadmap

- **Frontend→backend API-edge linking** (next) — match frontend `fetch`/`axios` URLs (already
  captured on each node) to backend route handlers, so a request flow crosses the stack.
- Frontend entities in the *structure* map (currently frontend is in the flow map).
- More languages (Java, Go); optional fully-offline viewer that embeds the graph library.

## License

See [LICENSE](LICENSE).
