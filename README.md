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

- **AST-based scanner** — parses Python with the standard-library `ast` module (accurate, no
  guessing), extracting classes, methods, docstrings, bases, decorators, and imports.
- **Bidirectional Markdown vault** — one `[[wikilink]]`-cross-referenced note per entity,
  compatible with Obsidian and any Markdown viewer.
- **Explicit dependency graph** — `graph.json` (nodes + edges) and `registry.json`
  (entity → file path), compiled deterministically from the vault.
- **Execution-flow tracing** — shortest path (or all paths) between any two components.
- **Blast-radius / impact analysis** — reverse-traversal listing every upstream caller affected
  by a change.
- **Standalone shareable visualizer** — generates a single self-contained `graph.html` with the
  data embedded inline; open via `file://`, commit it, or email it. Layer-colored, searchable,
  and hand-editable.
- **Layer inference** — auto-classifies entities (controller / service / repository / model /
  client / config) for architectural coloring.
- **Zero external dependencies** — pure Python 3.10+ standard library. No `pip install`, no
  server required for the graph.

## Requirements

- **Python 3.10+** (only the standard library is used).
- A modern browser to view the generated `graph.html` (loads `force-graph` from a CDN).

## Installation

Clone the repo, then run the installer for your platform.

**Windows (PowerShell):**
```powershell
git clone https://github.com/non-nattawut/Code-Archaeologist-LLM-Agent-Skill.git
cd Code-Archaeologist-LLM-Agent-Skill
.\install.ps1 -SelfTest
```

**macOS / Linux (bash):**
```bash
git clone https://github.com/non-nattawut/Code-Archaeologist-LLM-Agent-Skill.git
cd Code-Archaeologist-LLM-Agent-Skill
./install.sh --self-test
```

The installer verifies Python 3.10+ and (with `--self-test` / `-SelfTest`) builds the bundled
`sample_src/` demo end to end.

### Install into another project

To use the skill on your own codebase, copy it into that project's `.agents/skills/` folder:

```powershell
.\install.ps1 -Target C:\work\my-service      # Windows
```
```bash
./install.sh --target /work/my-service         # macOS / Linux
```

This copies the scripts, `SKILL.md`, and templates, and creates a fresh empty `data/` workspace
(the demo vault is not carried over).

## Usage

The pipeline is four steps — scan, graph, trace, visualize:

```bash
# 1. Scan source into the Markdown vault
python .agents/skills/code-wiki/scripts/build_wiki.py --src ./src

# 2. Compile the vault into graph.json + registry.json
python .agents/skills/code-wiki/scripts/build_graph.py

# 3a. Trace an execution flow (shortest path; add --all for every path)
python .agents/skills/code-wiki/scripts/trace_path.py --from OrderController --to OrderRepository

# 3b. Blast-radius: everything that breaks if a class changes
python .agents/skills/code-wiki/scripts/trace_path.py --impact-of OrderRepository

# 4. Generate a standalone, shareable HTML graph (data embedded inline)
python .agents/skills/code-wiki/scripts/build_html.py
# then open .agents/skills/code-wiki/data/graph.html
```

### Example

Running against the bundled `sample_src/` (a controller → service → repository/client trio):

```console
$ python .agents/skills/code-wiki/scripts/trace_path.py --from OrderController --to OrderRepository
{
  "mode": "flow",
  "from": "OrderController",
  "to": "OrderRepository",
  "path": ["OrderController", "OrderService", "OrderRepository"],
  "found": true
}

$ python .agents/skills/code-wiki/scripts/trace_path.py --impact-of OrderRepository
{
  "mode": "impact",
  "target": "OrderRepository",
  "impacted": ["OrderController", "OrderService"],
  "count": 2
}
```

The agent then reads only `data/vault/OrderController.md`, `OrderService.md`, and
`OrderRepository.md` — not the whole repo.

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
│   ├── build_wiki.py            # AST scan  -> data/vault/*.md (with [[wikilinks]])
│   ├── build_graph.py           # vault     -> graph.json + registry.json
│   ├── trace_path.py            # BFS flow (--from/--to) & impact (--impact-of)
│   └── build_html.py            # graph.json -> standalone shareable graph.html
├── data/
│   ├── graph.json               # cached nodes & edges
│   ├── registry.json            # entity -> vault path
│   ├── graph.html               # generated standalone viewer
│   └── vault/                   # generated Markdown notes (Obsidian-compatible)
└── templates/
    └── wiki_page_template.md    # page structure for generated entities
install.ps1 / install.sh         # installers (verify Python, install, self-test)
sample_src/                      # demo controller/service/repository/client trio
```

## Roadmap

- Additional language scanners (Java, TypeScript/JS, Go) — `build_wiki.py` is structured so a
  per-language extractor can slot in alongside the Python `ast` path.
- Optional LLM-generated entity summaries.
- Optional fully-offline viewer (`--inline-lib`) that embeds the graph library.

## License

See [LICENSE](LICENSE).
