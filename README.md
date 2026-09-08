# Code Archaeologist

**A codebase map your AI agent can query instead of reading your whole repo.**

It scans your code once, builds two graphs plus one note per class/method, and answers
architecture questions by walking those graphs — not by grepping source. Everything is
deterministic (`ast` + graph traversal, no embeddings, no vector DB) and the Python side has
**zero dependencies**.

```
"How does a request reach the database?"

  trace  ->  submitOrder > createOrder > OrderController.create_order
             > OrderService.place_order > OrderRepository.save
  read   ->  5 notes (~1,500 tokens)     instead of the whole repo
```

---

## Why not RAG?

RAG chops code into ~500-token chunks and retrieves by similarity. That destroys the two things
architecture questions are *about*: scope and call hierarchy.

| | Standard RAG | Code Archaeologist |
| --- | --- | --- |
| **Unit** | arbitrary ~500-token chunk | one whole class / method per note |
| **Relationships** | lost | explicit graph edges |
| **Retrieval** | similarity search, non-deterministic | BFS traversal, same answer every time |
| **Cost per query** | re-reads large context | only the nodes on the path |
| **Infra** | embeddings + vector DB | a JSON file |

---

## Quick start

```bash
# 1. install the skill into your project (no clone, no npm account)
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --harness claude

# 2. build both maps
python .claude/skills/code-archaeologist/scripts/archaeologist.py both --src ./src

# 3. review them
python .claude/skills/code-archaeologist/scripts/archaeologist.py report --src ./src
```

Then open `data/explorer.html` — one self-contained page, both maps, works offline from `file://`.

> Scanning JS/TS? Run `cd .claude/skills/code-archaeologist && npm install` first (installs
> `@babel/parser`). Skip it and the frontend is left out — the build says so loudly.

---

## The two maps

Both are built from the same scan and answer different questions.

| | **Structure map** | **Flow map** |
| --- | --- | --- |
| **Node** | a class / entity | a method / function |
| **Edge** | references, imports | calls |
| **Answers** | "how is this organized?", "who uses X?" | "how does a request travel?", "what calls what?" |
| **Output** | `data/structure/` | `data/flow/` |

They cross the stack. Frontend `fetch`/`axios` calls are matched to backend route handlers by HTTP
method + normalized path, so **one trace runs from a button click to the database**.

---

## What it can tell you

Every item below is a command, and every answer is computed from the graphs — never from an LLM
guessing. Full syntax lives in **[USAGE.md](USAGE.md)**.

### Navigate

| Question | Command |
| --- | --- |
| Where is X handled? | `search.py --name X` (also `--calls`, `--called-by`, `--orphans`) |
| How do A and B connect? | `trace_path.py --from A --to B` |
| What breaks if I change X? | `trace_path.py --impact-of X` |
| What does my current PR affect? | `trace_path.py --impact-of-diff` |
| Everything about one node, in one call | `context.py --node X` |
| Orient me on this repo (~35 lines) | `archaeologist.py brief` |

### Review

| Question | Command |
| --- | --- |
| Is this codebase healthy? (0–100, A–F) | `analyze.py` |
| Any secrets / SQL injection / XSS sinks? | `scan_security.py` |
| What's rotting? (TODOs, dead code) | `debt.py` |
| What's tested — and what isn't? | `tests_map.py` |
| Where's the churn and who owns it? | `git_insights.py` |
| How big / complex is each piece? | `metrics.py` |
| All of it, as one report | `archaeologist.py report` |

### Trust

| Question | Command |
| --- | --- |
| Are the maps still current? | `archaeologist.py check` |

The maps drift the moment code changes. `check` hashes every source file and reports exactly what
moved, so an agent rebuilds *before* answering rather than confidently citing a stale graph.

---

## How it works

```
   your source                         two graphs                    one page
  ┌───────────┐    ast / @babel     ┌──────────────┐   analysis   ┌──────────────┐
  │ .py .ts   │ ─────────────────▶  │ structure    │ ───────────▶ │ explorer.html│
  │ .jsx .tsx │    extract          │ flow         │   + report   │ (both maps)  │
  └───────────┘                     └──────────────┘              └──────────────┘
                                          │
                                          ▼  one Markdown note per node
                                    [[wikilinked]] vault
```

The pieces that make it cheap and repeatable:

- **Deterministic extraction.** Python via the stdlib `ast` module; JS/TS via `@babel/parser`.
  No heuristic text parsing of source, so the same input always yields the same graph.
- **Call resolution without a type checker.** `self.<dep>.method()` is resolved through `__init__`
  type hints and assignments, typed params/locals, and same-class `self.method()` calls.
  Unresolvable external calls are dropped rather than guessed.
- **AI writes prose, never structure.** Descriptions come cheapest-first: docstring → cached AI
  summary → deterministic fallback. Summaries are keyed by the method's source hash, so only
  *new or changed and undocumented* methods ever cost a token.
- **Findings attach to nodes.** A security hit, a TODO, a churn number and a complexity score all
  land on the graph node that owns that line — so any of them can be traced and blast-radiused
  like anything else.

---

## The explorer

One self-contained HTML file with both maps embedded. No server, no repo access, works offline —
commit it or email it.

- **Left** — health ring (A–F), color-by (layer / folder / churn / risk), stat tiles, language
  mix, and a file tree that filters the canvas.
- **Center** — seven views of the same graph: Graph, Treemap, Matrix, Tree, Flow, Cluster, Bundle.
  Plus folder hulls, a blast-radius toggle, and PNG export.
- **Right** — **FILE** (what it does, blast radius, connections, git ownership, risks),
  **PATTERNS** (cycles, layer violations, hubs, god objects, dead code), **SECURITY** (findings by
  severity). All click through into each other.

---

## Language support

| Capability | Languages |
| --- | --- |
| **Graphs** (nodes + edges) | Python, JavaScript/TypeScript |
| **Lines, complexity, risk scan, debt markers, test detection** | + Java, Kotlin, Go, Rust, C#, Ruby, PHP, Swift, Scala, Dart, Elixir, C/C++ |

Test files are recognized across all of them (pytest, Jest/Vitest, JUnit/Spring, `*_test.go`,
`#[test]`, `[Fact]`, RSpec, PHPUnit) and tagged `layer: test` — so **test code is never reported as
dead code** and its calls never count as coupling.

---

## Requirements

| | |
| --- | --- |
| **Python 3.10+** | required — stdlib only, no `pip install` |
| **Node + `@babel/parser`** | only for JS/TS parsing (`npm install` in the skill folder) |
| **git** | optional — only for churn / ownership / hotspots |
| **A browser** | to open the explorer |

---

## Installation

```bash
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill                    # pick a harness
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --harness claude   # or name it
npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --self-test        # install + verify
```

| Harness | Installs to |
| --- | --- |
| `agents` (default) | `.agents/skills/code-archaeologist` |
| `claude` | `.claude/skills/code-archaeologist` |
| `cursor` | `.cursor/skills/code-archaeologist` |
| `windsurf` | `.windsurf/skills/code-archaeologist` |
| `zed` | `.zed/skills/code-archaeologist` |

Use `--dir <path>` for anywhere else. Other flags: `--target <dir>`, `--force`, `--help`.

The installer checks for Python 3.10+, copies the skill in, and creates an empty `data/` workspace.
It has no npm dependencies of its own.

---

## How an agent uses it

`SKILL.md` tells the agent to:

1. **Check freshness first** — rebuild if the source moved, then orient with `brief`.
2. **Never read raw source** for architecture questions.
3. **Find** nodes with `search.py`, **trace** with `trace_path.py`, **load** them with `context.py`.
4. Read individual notes only when it needs more.
5. Keep `[[wikilinks]]` in answers so replies stay navigable.
6. For "is this healthy?", answer from the generated report.

---

## Project structure

```
.agents/skills/code-archaeologist/
├── SKILL.md              agent instructions
├── scripts/
│   ├── archaeologist.py  entrypoint: project | flow | both | check | report | brief
│   ├── taxonomy.py       the one source of truth for kind/layer values
│   │
│   ├── build_wiki.py     ─┐
│   ├── build_graph.py     │ extract: source -> graphs + notes
│   ├── build_flow.py      │
│   ├── js_extract.js      │ (Node/@babel)
│   ├── js_bridge.py       │
│   ├── apply_descriptions.py
│   └── manifest.py       ─┘ freshness hashes
│   │
│   ├── analyze.py        ─┐
│   ├── scan_security.py   │
│   ├── git_insights.py    │ review: graphs -> findings
│   ├── metrics.py         │
│   ├── debt.py            │
│   ├── tests_map.py       │
│   ├── brief.py           │
│   └── report.py         ─┘
│   │
│   ├── trace_path.py     ─┐
│   ├── context.py         │ query & render
│   ├── search.py          │
│   ├── console.py         │
│   └── build_html.py     ─┘ -> data/explorer.html
├── templates/            viewer.html · wiki_page_template.md · TAXONOMY.md
└── data/
    ├── explorer.html     both maps, one page
    ├── structure/  flow/  report/  cache/
```

---

## Roadmap

- Frontend entities in the *structure* map (today they appear in the flow map).
- Wider route/framework coverage for API linking (Flask, Express, Nest).
- Graph extractors for more languages; a fully offline viewer.
- Duplicate-code clusters, via normalized token hashing of function bodies.

## License

See [LICENSE](LICENSE).
