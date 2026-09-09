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
| **Node** | a class, React component or module | a method / function |
| **Edge** | references, imports | calls |
| **Answers** | "how is this organized?", "who uses X?" | "how does a request travel?", "what calls what?" |
| **Output** | `data/structure/` | `data/flow/` |

Both cover backend and frontend: a `.tsx` React component is a structure node next to a Python
service class, and a function that returns JSX is typed `component` rather than lumped into its
file's module page.

They cross the stack. Frontend `fetch`/`axios` calls are matched to backend route handlers by HTTP
method + normalized path, so **one trace runs from a button click to the database**. Routes are
read from seven framework shapes — FastAPI, Flask, Express, Nest, Spring, ASP.NET and the Go
routers (gin/chi/mux) — so a React click can be traced into Java or Go, not just Python. Where the
path does not match exactly, a unique suffix still links (so an `/api` mount prefix works) and an
ambiguous one is left alone.

---

## What it can tell you

Every item below is a command, and every answer is computed from the graphs — never from an LLM
guessing. Full syntax lives in **[USAGE.md](docs/USAGE.md)**.

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
| What's been copy-pasted? | `duplicates.py` |
| Where's the churn and who owns it? | `git_insights.py` |
| How big / complex is each piece? | `metrics.py` |
| All of it, as one report | `archaeologist.py report` |

### Trust

| Question | Command |
| --- | --- |
| Are the maps still current? | `archaeologist.py check` |

The maps drift the moment code changes. `check` hashes every source file and reports exactly what
moved, so an agent rebuilds *before* answering rather than confidently citing a stale graph. It
needs no arguments — a build records the roots it scanned, and `check` and `brief` re-use them.

---

## How it works

```
   your source                         two graphs                    one page
  ┌───────────┐                     ┌──────────────┐   analysis   ┌──────────────┐
  │ .py .ts   │  ast / @babel /     │ structure    │ ───────────▶ │ explorer.html│
  │ .jsx .tsx │  declaration scan   │ flow         │   + report   │ (both maps)  │
  │ .java .go │ ─────────────────▶  └──────────────┘              └──────────────┘
  │ .cs       │      extract              │
  └───────────┘                           ▼  one Markdown note per node
                                    [[wikilinked]] vault
```

The pieces that make it cheap and repeatable:

- **Deterministic extraction.** Python via the stdlib `ast` module; JS/TS via `@babel/parser`;
  Java, Go and C# by reading declarations textually. The first two tiers are parsed and exact; the
  third is approximate and says so on every node it produces (see [Language
  support](#language-support)). All three are deterministic — the same input always yields the same
  graph.
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

One self-contained HTML file with both maps embedded. No server, no repo access, and **no network
— the graph library is vendored and inlined**, so it opens from `file://` with the wifi off. Commit
it or email it.

- **Left** — health ring (A–F), color-by (layer / folder / churn / risk), stat tiles, language
  mix, and a file tree that filters the canvas.
- **Center** — seven views of the same graph: Graph, Treemap, Matrix, Tree, Flow, Cluster, Bundle.
  Plus folder hulls, a blast-radius toggle, and PNG export.
- **Right** — **FILE** (what it does, blast radius, connections, git ownership, risks),
  **PATTERNS** (cycles, layer violations, hubs, god objects, dead code), **SECURITY** (findings by
  severity). All click through into each other.

Both side panels drag to resize from their inner border. In the tree, `+`/`–` expands a folder and
clicking its name filters the canvas — two separate controls. The explorer fills whatever the
panels above it leave, so fold one from its heading to give the tree more room. Dragging a node
pins it where you drop it, so the **reset** button in the toolbar throws the layout away and
re-runs it from scratch — along with the current selection and filter.

---

## Language support

| Capability | Languages |
| --- | --- |
| **Graphs, exact** (parsed) | Python, JavaScript/TypeScript |
| **Graphs, approximate** (read textually) | Java, Go, C# |
| **Lines, complexity, risk scan, debt markers, test detection** | + Kotlin, Rust, Ruby, PHP, Swift, Scala, Groovy, Dart, Elixir, C/C++ |

The two graph tiers differ in how the source is read, and the difference is visible in the output
rather than buried in a caveat: every node and edge from the approximate tier carries
`approx: true`, the report opens with how many nodes it applies to, `context.py` repeats it on the
node an agent is reading, and the explorer marks it with an `approx` chip.

Approximate does not mean guessed. Comments and string bodies are blanked before anything is
matched, bodies are found by brace matching rather than regex, and a call is resolved only through
a *declared* type — a field, a parameter, a `new Foo()`. Interface dispatch, overloads and lambda
handlers cannot be resolved without a type checker, so those edges are **dropped, not invented**:
the coupling shown is a lower bound. Constructor injection (Spring, ASP.NET DI, a Go struct
literal) resolves reliably, because these languages must declare their parameter types.

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
| **A browser** | to open the explorer — no network needed |

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
│   ├── paths.py          one definition of where the skill's files live
│   │
│   ├── core/             vocabulary every other script shares
│   │   ├── taxonomy.py     the one source of truth for kind/layer values
│   │   ├── manifest.py     what counts as a source file + freshness hashes
│   │   └── console.py      stdout that survives a non-UTF-8 console
│   │
│   ├── extract/          source -> graphs + notes
│   │   ├── build_wiki.py
│   │   ├── build_graph.py
│   │   ├── build_flow.py
│   │   ├── js_extract.js   (Node/@babel)
│   │   ├── js_bridge.py
│   │   ├── lang_extract.py Java/Go/C#, read textually and marked approx
│   │   └── apply_descriptions.py
│   │
│   ├── review/           graphs -> findings
│   │   ├── analyze.py
│   │   ├── scan_security.py
│   │   ├── git_insights.py
│   │   ├── metrics.py
│   │   ├── debt.py
│   │   ├── tests_map.py
│   │   ├── duplicates.py
│   │   ├── brief.py
│   │   └── report.py
│   │
│   └── query/            ask questions, render the page
│       ├── trace_path.py
│       ├── context.py
│       ├── search.py
│       └── build_html.py  -> data/explorer.html
├── templates/            viewer.html · wiki_page_template.md · TAXONOMY.md
│   └── vendor/           force-graph.min.js, inlined so the explorer needs no network
└── data/
    ├── explorer.html     both maps, one page
    ├── structure/  flow/  report/  cache/
```

---

## What's next

Everything the earlier roadmap listed has shipped: frontend entities in the structure map,
route coverage across four frameworks, an approximate graph tier for Java/Go/C#, a fully offline
viewer, and duplicate-code clusters. What is still open:

- **Django URL-table routes.** Routes are read from decorators today, so a `urlpatterns` table is
  not picked up and Django views do not link across the stack.
- **Graphs for dynamic languages.** Ruby, PHP and Elixir are scanned for lines, risk, debt and
  tests, but have no nodes or edges — their dispatch is hard to read without executing.
- **Duplicates below function granularity.** Clones are matched whole-body, so a copied block
  inside two otherwise different functions is missed.

## License

See [LICENSE](LICENSE).
