---
name: code-archaeologist
description: Zero-RAG codebase navigation with two maps — a project-structure graph (which classes reference which) and a method-level flow graph (which method calls which, i.e. request/execution flow), plus a review pass (health grade, risk scan, git hotspots). Use to explain architecture, trace how a request flows through methods, find what breaks if a class/method changes, or review a codebase for smells, risky code and change hotspots.
---

# Skill: Code Archaeologist & Living Wiki Navigator

## Overview
Zero-RAG codebase navigation from local graphs and Markdown notes. **Two maps:**

- **Structure** (class level) — who references/imports whom.
  `data/structure/graph.json` + `data/structure/vault/<Entity>.md`
- **Flow** (method level) — who calls whom, so a real request path can be traced
  (`OrderController.create_order -> OrderService.place_order -> OrderRepository.save`).
  `data/flow/flow_graph.json` + `data/flow/notes/<Class.method>.md`

`data/` is grouped by map: `structure/`, `flow/`, `report/<map>/` (the review pass), `cache/`
(AI-summary + freshness state; you rarely touch it). Both maps share one viewer,
`data/explorer.html`, switched from its header.

## Setup — preflight before the first build

Once per machine/checkout, before the first `project` / `flow` / `both` build.

**1. Python 3.10+ — required.** The pipeline is stdlib apart from tree-sitter, which step 2
covers.
```bash
python --version        # or python3; needs 3.10+
```
Older or missing: stop and tell the user, the skill cannot run.

**2. tree-sitter — for every language, Python included.** Grammars are installed per language, so
install only what the repo actually contains. **Do this yourself — don't ask the user to.**
```bash
cd .agents/skills/code-archaeologist && python -c "import tree_sitter; print('runtime ok')"
python .agents/skills/code-archaeologist/scripts/core/grammars.py --install python typescript   # the repo's languages
python .agents/skills/code-archaeologist/scripts/core/grammars.py --install                     # or every grammar
```
These are wheels — no compiler, grammar bundled, one package per language — at the **pinned**
versions the skill was tested against (`grammars.PINS`; `--print` shows the pip command instead of
running it). Run it with the same `python` that runs the skill: the runtime wheel is built for one
Python version. Languages: `python`, `javascript`, `typescript`, `tsx`, `java`, `go`, `csharp`,
`kotlin`, `rust`, `swift`, `scala`, `groovy`, `dart`, `c`, `cpp`, `ruby`, `php`, `elixir`;
the runtime is always included. Two mappings are worth
knowing: **`tree-sitter-javascript` covers `.js` and `.jsx`**, and **`tree-sitter-typescript`
covers both `.ts` and `.tsx`** (one wheel, two grammars — `.tsx` genuinely needs the second one).

**`tree-sitter-python` is not optional if the repo has any Python.** It used to be read with the
standard library, so it needed nothing; it is now read the same way as everything else, and without
that wheel a Python repo produces an almost empty graph — with a warning saying so.

**Install it yourself — this does not touch the user's Python.** `--target vendor` puts the wheels
in `<skill>/vendor`, which the skill's `.gitignore` excludes: nothing enters the environment the
user runs their own projects in, no version can collide with theirs, and deleting the skill folder
removes every trace. Keep all three
flags — `--target` is the whole point, `--only-binary :all:` fails loudly instead of trying to
compile, and `--no-cache-dir` stops pip writing the wheels outside the skill folder.

The build tells you exactly what is missing and the exact command:

```
! csharp skipped: no tree-sitter grammar installed. Run `pip install ... --target <skill>/vendor tree-sitter-c-sharp` to enable it.
```

If instead it says **"runtime found but not loadable"**, the wheels were installed under a
different Python version than the one running now — re-run the install command above, which
rebuilds `vendor/` for this interpreter.

If a grammar is missing, the build still succeeds and those files simply produce **no nodes**.
`brief` prints a `SKIPPED` block naming the language and the fix. **Never answer a "what calls X",
"is this dead code" or "how big is this codebase" question while a language is skipped without
saying so** — the graph is smaller than the codebase, and nothing else in the output makes that
visible.

## Operating Principles
1. NEVER read raw source for architecture, flow or review questions.
2. Pick the map: **structure** for "how is this organized / who uses X"; **flow** for "how does a
   request travel / what calls what".
3. Start from the graph, not from grep: `search.py` (Command 4) to find node ids, `trace_path.py`
   (Commands 5-6) for the path or blast-radius. Ids are bare (`place_order`,
   `OrderService.place_order`) **unless two files define the same name** — then each definition
   is qualified by its file (`tests_map.build`, `report.build`). So find an id with
   `search.py --name 'build$'` rather than typing one from memory; and a call to a shared name from
   a file that does not define it was dropped, not guessed.
4. Then take the facts in ONE call with `context.py --node <id>` (Command 7). Read individual notes
   (`data/structure/vault/<Entity>.md`, `data/flow/notes/<Class.method>.md`) only when the pack is
   not enough, and only for nodes on the discovered path.
5. Preserve `[[EntityName]]` / `[[Class.method]]` wikilinks in answers so they stay navigable.
6. **Check freshness before trusting a map** (Command 9). If it says `stale`, rebuild first — see
   "Keeping the maps current".
7. For review questions ("is this healthy?", "where is the risk?", "what to refactor first?"), run
   the report (Command 14), read the **brief** (Command 1), and open
   `data/report/<map>/architecture_report.md` only for the detail the brief points at.
8. **Say that edges are a lower bound, and name the loss when the node names it.** This is true
   in *every* language: a call is drawn only when the receiver's type can be read from the source,
   and anything else is dropped rather than guessed. Where a specific loss is known the node
   carries `precision` — `interface-dispatch` (the call stops at an interface), `overloads`
   (signatures folded into one node), `name-matched` (JS/TS, Ruby, PHP, Elixir, Groovy: a call
   through an object with no declared type dropped). What
   is trustworthy everywhere is the declarations; what is partial is
   **resolution**. A call is followed only through a *declared* type, and anything else (overloads,
   lambda handlers) is dropped rather than guessed. A call through an interface resolves to the
   interface's own node, which carries `declaration: true`: the trace stops at the declaration and
   does **not** continue into the implementations, so "what actually runs" is still unanswered
   there. So their edges are a **lower bound** — "nothing calls X" is only "nothing the extractor
   could resolve calls X". Tell the user that when you answer from one, and say it plainly if a
   whole answer (dead code, blast radius, "who calls this") rests on edges that were resolved
   rather than declared. `context.py` and the report both carry the caveat for you, and name the
   specific loss where a node has one; do not quietly drop it.

## Available Tool Commands

> First build in this project? Run the **Setup preflight** above first.
> Paths below assume the default install; if the skill lives elsewhere, that prefix is already
> rewritten to match.

### 1. Orientation brief — start here
Fixed-size digest of what is built: counts and grade per map, staleness, size, entry points, and
the top longest / most complex / most churned / riskiest nodes. Costs the same on a 200-file repo
as on a 5-file one, so use it instead of reading `architecture_report.json`.
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py brief --src ./src
```
`--map structure` switches the detail sections, `--top N` sizes them, `--json` for tooling. `--src`
is optional here too — without it the freshness line uses the roots the last build recorded.

### 2. Build the Project Structure map
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py project --src ./src
```
Nodes are classes, React components and one `<Name>Module` page per file of module-level
functions, from Python and JS/TS alike. A JS/TS function that returns JSX gets `kind: component`
and `layer: ui`, and an `import ... from "./x"` becomes an edge to whatever that file defines.

### 3. Build the Flow / Request-Flow map
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./src
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./src   # both maps
python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./backend ./frontend
```
`--src` takes several roots, so a monorepo lands in one graph (node `source` keeps its root
prefix: `backend/…`, `frontend/…`). Every language is parsed by tree-sitter (grammar missing →
those files skipped with a warning). Frontend `fetch`/`axios`
calls are matched to backend route handlers by HTTP method + path, giving cross-stack `http`
edges — so one trace can run frontend → API → service → repository.

Route handlers are recognised in FastAPI, Flask (including `@app.route` on a module-level `def`
and `methods=["GET", "POST"]`), Express (named handler or inline arrow) and Nest (`@Controller`
prefix + `@Get`/`@Post` suffix). A node's `routes` is a **list** — say all of them when asked what
a handler serves. When a call's path does not match a route exactly, the link falls back to a
route whose path is a suffix of it, and only when exactly one route matches; an ambiguous path is
left unlinked rather than guessed, so a missing `http` edge means "could not tell", not "no
caller".

### 4. Find the nodes (instead of grepping)
Filter the graph and get ids back for the commands below. Never grep source to find "where is X
handled".
```bash
python .agents/skills/code-archaeologist/scripts/query/search.py --name "payment|charge"
python .agents/skills/code-archaeologist/scripts/query/search.py --doc "refund"
python .agents/skills/code-archaeologist/scripts/query/search.py --layer repository --kind method
python .agents/skills/code-archaeologist/scripts/query/search.py --calls OrderRepository.save
python .agents/skills/code-archaeologist/scripts/query/search.py --orphans
```
Filters AND together; `--graph` picks the map (default: flow), `--limit` caps rows.

### 5. Trace Execution Flow
Structure is the default graph; flow needs `--graph`. Output is one line per path (`A > B > C`);
add `--all` for every path, `--format json` only when something machine-reads it.
```bash
python .agents/skills/code-archaeologist/scripts/query/trace_path.py --from <SourceClass> --to <TargetClass>
python .agents/skills/code-archaeologist/scripts/query/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json \
  --from OrderController.create_order --to OrderRepository.save
```

### 6. Blast-Radius / Impact Analysis
Everything upstream of a node — and, with `--impact-of-diff`, of a whole changeset (changed files
are mapped to nodes, then their impact is unioned). Works on either graph.
```bash
python .agents/skills/code-archaeologist/scripts/query/trace_path.py --impact-of <ClassName>
python .agents/skills/code-archaeologist/scripts/query/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --impact-of <Class.method>
python .agents/skills/code-archaeologist/scripts/query/trace_path.py --impact-of-diff            # working tree
python .agents/skills/code-archaeologist/scripts/query/trace_path.py --impact-of-diff --staged
python .agents/skills/code-archaeologist/scripts/query/trace_path.py --impact-of-diff --base origin/main
```

### 7. Context pack for a node (one call, budgeted)
Everything known about a node from the artifacts: kind/layer/source, size and complexity, churn
and owner, description, immediate callers and callees *each with their own description*, and the
risks attributed to it. Replaces "trace, then open five notes".
```bash
python .agents/skills/code-archaeologist/scripts/query/context.py --node OrderService.place_order
python .agents/skills/code-archaeologist/scripts/query/context.py --node A B --depth 2 --max-chars 8000
python .agents/skills/code-archaeologist/scripts/query/context.py --diff     # every node the diff touches
```
`--max-chars` (default 6000) is a hard budget: neighbor lists shrink until it fits, and it says
when it trimmed. `--graph` picks the map (default: flow), `--format json` for tooling. When tests
call the node, the pack lists them under **Covered by** — real call edges, so it answers "which
tests should I run for this change".

### 8. Regenerate the HTML explorer
`archaeologist.py` refreshes `data/explorer.html` on every build; this rebuilds it alone:
```bash
python .agents/skills/code-archaeologist/scripts/query/build_html.py
```
One page holds both maps (header switch): grade, tiles and file tree on the left; seven views
(Graph, Treemap, Matrix, Tree, Flow, Cluster, Bundle) in the middle; FILE / PATTERNS / SECURITY
tabs on the right. A map with no report still renders, minus the grade and review tabs. A
**Tests** checkbox appears when the map has test nodes and hides them, for when you want the
architecture without the suite hanging off it.

### 9. Check freshness (are the maps stale?)
Returns `{stale, changed, added, deleted}`. Rebuild if `stale`.
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py check --src ./src
python .agents/skills/code-archaeologist/scripts/archaeologist.py check              # same roots as the last build
```
`--src` is optional: the build records its roots, so the check re-uses them. If a root has moved
you get `source root(s) not found from here` rather than a false "everything was deleted".

### 10. Architectural smells & health grade
Cycles, orphans/dead nodes, backwards layer violations, high-coupling hubs, god objects,
name-based idioms, and a 0-100 / A-F health score (`--security <security.json>` folds risk
findings into the grade).
```bash
python .agents/skills/code-archaeologist/scripts/review/analyze.py                    # structure (default)
python .agents/skills/code-archaeologist/scripts/review/analyze.py --format text      # no JSON envelope
python .agents/skills/code-archaeologist/scripts/review/analyze.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json
```

### 11. Risk / security scan
Line scan for hardcoded secrets, interpolated SQL, `eval`/`innerHTML` sinks and leftover debug
statements. Each finding names the node owning the line, so it can be traced and blast-radiused
(tests/fixtures/docs skipped, secrets redacted).
```bash
python .agents/skills/code-archaeologist/scripts/review/scan_security.py --src ./src
```
`--graph <flow_graph.json>` attributes findings to methods instead of classes; `--out <file.json>`
saves the report.

### 12. Churn, ownership & hotspots (git)
Commits per file, top author per file, and a hotspot ranking where
`risk = commits x (1 + fan_in + fan_out)`. Outside a git repo it returns empty data with a note.
```bash
python .agents/skills/code-archaeologist/scripts/review/git_insights.py --src ./src --top 10
```

### 13. Size & complexity (lines of code)
Lines per file (total / code / comment / blank + language mix) and, for Python nodes, LOC,
cyclomatic complexity, nesting depth and parameter count — keyed by the graph's node ids, so
"how long / how tangled is `OrderService.place_order`" needs no file read.
```bash
python .agents/skills/code-archaeologist/scripts/review/metrics.py --src ./src --top 10
```
`--graph <graph.json>` ranks only that map's nodes; `--out <path>.json` saves it. Command 14 runs
this for you into `data/report/<map>/metrics.json`.

### 14. Full architecture report
One review pass per built map — census, grade, smells, anti-patterns, risks, hotspots, size and
complexity, debt and test references — into `data/report/<map>/architecture_report.md`
(+ `.json`, `security.json`, `insights.json`, `metrics.json`, `debt.json`, `tests.json`). It also re-renders `data/explorer.html` with both reports
embedded, enabling the health ring, churn/risk colors, ownership and the Patterns/Security tabs.
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./src
```
Use it for "review this codebase" / "where is the risk" / "what should we refactor first", then
answer from the brief and the report — never from source.

### 15. Debt inventory (markers + dead code)
TODO / FIXME / HACK / XXX / BUG / DEPRECATED left in comments, each attributed to the node that
owns the line, plus nodes nothing calls and files where *every* node is dead.
```bash
python .agents/skills/code-archaeologist/scripts/review/debt.py --src ./src --top 10
```
`--graph` picks the map, `--out <file>.json` saves it, `--format json` for tooling. Answers
"what should we clean up first" without reading a file.

### 16. Test coverage map (by name)
Which nodes the test suite even mentions — and, more usefully, which it never names. A
`Class.method` counts as referenced when a test file names both the class and the method; a
function or class when the test names it.
```bash
python .agents/skills/code-archaeologist/scripts/review/tests_map.py --src ./src --top 15
```
Name-based, not execution coverage: no runner, nothing to install. A referenced node may still be
untested, but an unreferenced one is a real gap. Dunder methods and nodes living in test files are
left out of the count.

Test files are recognized by convention across languages — `test/`, `tests/`, `__tests__/`, `spec/`
directories; `test_*.py`, `*_test.go`, `*.test.tsx`, `*_spec.rb`; `OrderServiceTest.java`,
`FooTests.kt`, `PaymentIT.java`, `QuxTests.cs`; and files carrying `@Test` / `@SpringBootTest`
(JUnit 5, Spring Boot), `[Fact]` (.NET), `#[test]` (Rust) or `func TestX(t *testing.T)` (Go).
Such nodes get `layer: test` and are **never reported as dead code** — a runner calls them, so
nothing in the graph does. Their calls into production code are coverage, not coupling, so they are
also left out of the hub / god-object counts; what they *are* used for is Command 7's "Covered by"
and `--impact-of`, which then tells you which tests a change puts at risk.

### 17. Duplicate code clusters
Copy-pasted functions, found even when the identifiers were renamed. Every node's body is reduced
to its token shape — identifiers become `ID`, literals `LIT`, comments and whitespace vanish,
keywords and operators stay — and bodies with the same shape are the same code.
```bash
python .agents/skills/code-archaeologist/scripts/review/duplicates.py --src ./src --top 10
```
A rename cannot hide a copy; changing an operator or adding a branch does split the pair, which is
the point — it finds copies, not merely similar-looking code. Bodies under 30 tokens are ignored so
getters and one-line delegates do not flood the list. It errs toward missing a copy rather than
inventing one: a docstring counts as a token, so documenting one copy and not the other hides the
pair. Treat a cluster as a prompt to look, not proof of a bad abstraction.

## Keeping the maps current (hybrid AI descriptions)

Graph *structure* is always extracted by AST — exact, zero tokens. Method *descriptions* resolve
cheapest-source-first: docstring → cached AI summary (valid while the source hash is unchanged) →
deterministic fallback. So the AI writes a summary only for methods that are new or changed and
have no docstring.

After any code change, rebuild the map (Command 3). If it reports **pending** descriptions:

1. Open `data/cache/pending_descriptions.json` (each entry carries `signature` + `code`) and write
   a one-line summary per method as JSON `{ "<Class.method>": "<summary>", ... }`.
2. Apply them, then rebuild to fold them in:
   ```bash
   python .agents/skills/code-archaeologist/scripts/extract/apply_descriptions.py --input <summaries.json>
   python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./src
   ```

Summaries are cached in `data/cache/descriptions.json` by source hash, so unchanged methods are
never re-described; deleted ones are pruned (except after a build that skipped the frontend, which
keeps the cache intact — those nodes are missing, not gone). **0 pending** means done.

## Notes
- Graphs cover seventeen languages: Python, JS/TS/JSX/TSX, Java, Go, C#, Kotlin, Rust, Swift,
  Scala, Groovy, Dart, C, C++, Ruby, PHP and Elixir. A language whose grammar is not installed is
  skipped *by name* — the build says so and `brief` prints a `SKIPPED` block with the command —
  and the file-level passes (lines, risk scan, debt markers, test detection) still read it.
- One parser for every language: tree-sitter, whose wheels install into `<skill>/vendor` and never
  into the user's Python. Node is not used at all.
  The generated HTML needs no network: the graph library is vendored and inlined, so the explorer
  opens from `file://` offline.
- Field values (`kind`, `layer`, `lang`, `desc_source`, and the review `severity`/`rule`/`grade`
  sets) live in `scripts/core/taxonomy.py` and `scripts/review/scan_security.py` — see `templates/TAXONOMY.md`
  for the allowed values, and edit those rather than individual pages.
- Call resolution is heuristic, not type inference: `self.<dep>.m()` via `__init__` hints or
  assignments, typed params/locals, and same-class `self.m()`. Unresolved calls (libraries,
  stdlib) become no edge and are counted per node as `ext` ("N ext" in the explorer).
- `resolve_descriptions()` in `build_flow.py` is where a description is chosen — the hook for
  richer summaries.
- Every script resolves paths from the skill root, so it runs from any working directory.
