# CLAUDE.md

You are the **skill creator** of the **Code Archaeologist LLM Agent Skill** — the agent skill that
lives in `.agents/skills/code-archaeologist/`. Your job in this repo is to build and maintain that
skill, **not** to use it on this repo.

## What the skill is

A deterministic, Zero-RAG codebase documentation engine. It builds two maps of a target codebase,
reviews them, and renders one browsable page:

| Map | Nodes | Built by | Output |
| --- | --- | --- | --- |
| **Structure** | classes / React components / module groups | `build_wiki.py` → `build_graph.py` | `data/structure/{graph.json, registry.json, vault/*.md}` |
| **Flow** | methods/functions | `build_flow.py` | `data/flow/{flow_graph.json, notes/*.md}` |

An agent answers architecture questions by **querying the graph, then reading only the notes on the
returned path** — never by scanning source.

### Pipeline (what calls what)

```
archaeologist.py  project | flow | both | check | report | brief   <- the only entrypoint
  project  -> build_wiki -> build_graph ------------------\
  flow     -> build_flow (+ js_bridge -> js_extract.js) ---+--> render_explorer()
  report   -> report.py (scan_security + git_insights + analyze + metrics + debt + tests_map)
                                                                    -> data/report/<map>/
  brief    -> brief.py (reads the artifacts above, computes nothing)
  check    -> manifest.py (source hashes vs last build)
                                                            \-> build_html.py -> data/explorer.html
```

### Where the scripts live

`scripts/` is grouped by role, and `archaeologist.py` is the only file at its root because it is
the only entrypoint:

```
scripts/
  archaeologist.py   the entrypoint
  paths.py           SKILL_ROOT / DATA_DIR / TEMPLATES_DIR, and the sys.path bootstrap
  core/     taxonomy.py  manifest.py  console.py
  extract/  build_wiki.py  build_graph.py  build_flow.py  js_bridge.py  js_extract.js
            apply_descriptions.py
  review/   analyze.py  scan_security.py  git_insights.py  metrics.py  debt.py
            tests_map.py  report.py  brief.py
  query/    trace_path.py  context.py  search.py  build_html.py
```

Dependencies point one way: `core/` imports nothing of the skill's, everything else imports
`core/`, and no two categories import each other in a cycle. Keep it that way — a new script goes
in the category it *depends on*, not the one it reads like.

Every script therefore opens with the same two lines instead of re-deriving its own paths:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
```

Importing `paths` puts `scripts/` and all four category dirs on `sys.path`, which is why sibling
imports stay bare (`import taxonomy`) and why every script still runs directly from any working
directory (constraint 3). `extract/js_bridge.py` keeps a `SCRIPT_DIR` of its own on top of that —
it needs the directory holding `js_extract.js`, not the skill root — and `console.py` and
`taxonomy.py` need no preamble at all because they touch neither `data/` nor a sibling.

- `taxonomy.py` owns every `kind`/`layer` value (mirrored in `templates/TAXONOMY.md`). Add values
  there, never inline. It also owns **what counts as a test file** (`is_test_path` /
  `is_test_file`): path and filename conventions for a dozen languages plus framework markers
  (`@Test`, `@SpringBootTest`, `[Fact]`, `#[test]`, `func TestX(t *testing.T)`). Nodes in test
  files get `layer: test`, which is why `analyze.py` never calls them dead code and
  `scan_security.py` skips them. Every pass must ask taxonomy, never re-implement the check.
- `trace_path.py` is the query tool: `--from/--to` (BFS path), `--impact-of` (blast radius),
  `--impact-of-diff` (map a git diff to nodes, union their impact). Works on either graph.
- `analyze.py` is graph-only: cycles, orphans, layer violations, hubs, god objects, name-based
  idioms, and the 0–100 / A–F `health()` score (accepts security counts). Degree-based checks run
  on `app_edges()`, which drops edges touching a `layer: test` node — test calls are coverage, not
  coupling.
- `scan_security.py` is line-regex over source; every finding is attributed to the node owning that
  line. `git_insights.py` is one `git log --numstat` pass → churn, owners, hotspot risk.
- `metrics.py` is line counts per file plus LOC / cyclomatic complexity / nesting depth /
  parameter count per node, keyed like the graph nodes (per-node figures are Python only:
  `js_extract.js` now records `endLine`, but `metrics.py` does not read it yet). `report.py`
  derives `file_census` from it, so line counts have one definition.
- `search.py` is the "which nodes are these" filter over one graph (name/doc/layer/kind/lang/file
  plus `--calls` / `--called-by` / `--orphans`). It exists so neither the agent nor a human greps
  source to find a starting node.
- `context.py` is the per-node pack: graph facts + metrics/security/insights for one node and its
  neighbors, rendered under a hard `--max-chars` budget. Like `brief.py` it only reads artifacts.
- `debt.py` (markers in comments + orphan nodes/files) and `tests_map.py` (which nodes a test file
  names) are the two "what is rotting / what is untested" passes. Both are heuristics on purpose
  and neither feeds the health grade -- they report, they do not judge.
- `brief.py` is the fixed-size digest an agent should open a session with — it only reads what the
  other scripts wrote. Anything expensive belongs upstream of it, never inside it.
- `report.py` joins all of it into `data/report/<map>/architecture_report.{md,json}` plus
  `security.json` / `insights.json`. **One report per map** — node ids differ between maps, so a
  report from the other map must never be embedded (`build_html.report_for()` enforces this).
- `build_html.py` is thin: it loads `templates/viewer.html`, substitutes `__TITLE__` and
  `__MAPS_DATA__`, and writes **one** `data/explorer.html` holding both maps (header switch).

### Where the front-end lives

The explorer filters test nodes at load (`loadMap` -> `HAS_TESTS` / `EDGES`), so the **Tests**
checkbox re-renders through `applyMap`; anything reading edges must use `EDGES`, not `GRAPH.edges`.

`templates/viewer.html` is a normal HTML/CSS/JS file (three-pane explorer: health ring + tiles +
LOC/language mix + file tree | seven views: Graph/Treemap/Matrix/Tree/Flow/Cluster/Bundle |
FILE/PATTERNS/SECURITY tabs). Edit it directly; don't move markup back into Python. Its per-map
state is rebuilt by `loadMap()` / `applyMap()` — anything derived from a graph belongs in there,
not in a top-level `const`.

### Colour rules

One meaning, one colour, everywhere — a reader learns the scheme once, from any view.

- **Test code is green** (`TEST_COLOR` in `viewer.html`): the node (`LAYER_COLORS.test`), its
  folder area, the legend, all the same green. It is deliberately kept out of `FOLDER_COLORS`, so
  an ordinary folder can never be handed it.
- **A folder's colour comes from its index in `allFolders`** — every folder in the map — never
  from the visible list. Colouring off the visible list meant hiding the test folder re-coloured
  everything after it, and pink stopped meaning the same folder from one screenshot to the next.
- **A new `layer` / `kind` value needs its colour in `LAYER_COLORS` in the same commit** that adds
  it to `taxonomy.py`. The legend, the node painter and every view read from there; nothing
  hard-codes a colour at a call site.
- The chrome is deliberately quiet so the data can be loud: near-black ground `#08090b`, hairline
  rules `#1b1f26`, one accent (amber `#d99f4a`) for the active state and nothing else, and a system
  monospace stack. No emoji anywhere in the UI — icons are inline SVG on a 16px grid. Keep it that
  way; the palette below is the only saturated thing on screen.
- Already spoken for: controller/endpoint pink `#f778ba`, service blue `#6ea8fe`, repository green
  `#3fb950`, model amber `#e3b341`, client teal `#39c5cf`, config purple `#a371f7`, ui orange
  `#f0883e`, test green `#57ab5a`, unknown grey `#8b98ad`. Pick something distinguishable from all
  of them on the dark background — and if two must be close (the two greens are), keep them in
  different channels: node dots vs folder areas.

### Layout rules

The explorer is a three-pane desktop app, and it behaves like one: chrome holds still, content
scrolls.

- **One scroll region per pane, never two nested.** The left rail scrolls in the file tree only;
  the right panel scrolls in its body only. If something does not fit, fold it or shrink it —
  never add a second scrollbar.
- **A pane is a flex column**: `overflow: hidden` on the pane, `flex: none` on the fixed blocks,
  `flex: 1; min-height: 0` on the one region that grows, and `min-height: 0` again on the scroller
  inside it (without it the scroller inherits its content's height and the pane scrolls instead).
  Give the growing region a `min-height` floor so it cannot be squeezed to nothing.
- **Rail sections fold from their own `h3`**, with the marker in `::before` and the body hidden by
  a `folded` class on the section. Folding is how the user gives the tree room, so anything bulky
  in the rail needs a header. A folded header still carries its count (`Explorer 7 files`) — a
  section that says nothing when closed is a dead control.
- **Fold state is a class on static markup**, so it survives every re-render and map switch by
  construction. Do not store it in a variable that `applyMap()` resets.
- **Below `max-height: 620px`** the rail gives up and scrolls as a whole — a 60px tree is worse
  than a scrollbar.

## Hard constraints

1. **Zero external Python dependencies.** stdlib only, Python 3.10+. The *single* exception is
   frontend parsing (Node + `@babel/parser`, installed into the skill folder, git-ignored), and it
   must degrade gracefully: no Node → warn, skip JS/TS, still build the Python graph.
2. **Deterministic.** Same source in, same bytes out. AI text enters only through
   `apply_descriptions.py` (cached by source hash, docstring wins first, deterministic fallback
   last).
3. **Paths resolve from the skill root**, so every script runs from any working directory.
4. **The explorer is one self-contained file.** Data embedded inline, only `force-graph` from a CDN,
   opens from `file://` with no server.
5. **Windows-first testing.** Console is cp874 here: keep `print()` output ASCII (files can be
   UTF-8). Anything that echoes repo text (node ids, descriptions, paths, git author names) calls
   `console.safe_stdout()` first, so one accented author name cannot end a run. Bash heredocs mangle backslash-continuations — use the Edit/Write tools for content with
   `\` line continuations.

## Verify changes

Always run the full pipeline against the bundled sample, from the repo root:

```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./sample_src
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./sample_src
```

Expected on the current sample (it carries three deliberate smells — a hardcoded key, interpolated
SQL, an innerHTML sink — plus a pytest/unittest file, a `.test.ts` and a `.tsx` with two React
components, so the review path, the test path and the component path all have something to find):

- structure graph: 10 nodes / 12 edges — 6 Python, 4 JS/TS, of which `OrderCard` and `StatusBadge`
  are `kind: component` / `layer: ui`
- flow graph: 17 nodes / 12 edges, 3 endpoints, **0 pending** descriptions
- traces: `create_order → place_order → {save, charge}` and `get_order → find_order → get`;
  cross-stack `submitOrder → createOrder → OrderController.create_order → …`;
  structure `OrderCard → {ApiClientModule, StatusBadge}`
- grades: structure **C (70)**, flow **D (69)**; 4 risk findings each; 2 debt markers
- tests: 2 test files, flow **4/13 nodes named by a test**, and the two test nodes carry
  `layer: test` with call edges into `OrderService.place_order` / `OrderRepository.get`
- `archaeologist.py check --src ./sample_src` → `stale: false` right after a build

With `node_modules` renamed away the same build must still succeed, print the one
`frontend skipped` warning, and fall back to the Python-only 6 nodes / 9 edges.

Other checks worth running when you touch the relevant part:

```bash
python -m compileall -q .agents/skills/code-archaeologist/scripts     # syntax
python tools/check_docs.py                                            # docs vs code
node bin/cli.js --harness claude --target <tmpdir> --self-test        # installer
```

For `templates/viewer.html`, extract the inline `<script>` and parse it as a **classic script**
(`new vm.Script(code)`) — `node --check` wraps input in a CommonJS function, so it accepts top-level
`return` that a browser would reject. Then load `data/explorer.html` in a browser and exercise:
map switch, all seven views, explorer filter, blast toggle, tab drill-through. Note the in-app
preview pane does not auto-run this page's large inline script; run
`(0, eval)(document.scripts[1].textContent)` there first, or open it in a real browser.

If you changed `sample_src/`, regenerate the committed example data (both maps + both reports) in
the same commit — the repo ships it as the worked example.

---

## Working principles

### 1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

LLMs often pick an interpretation silently and run with it. Force explicit reasoning:
- **State assumptions explicitly** — if uncertain, ask rather than guess.
- **Present multiple interpretations** — don't pick silently when ambiguity exists.
- **Push back when warranted** — if a simpler approach exists, say so.
- **Stop when confused** — name what's unclear and ask for clarification.

### 2. Simplicity First
Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

The test: Would a senior engineer say this is overcomplicated? If yes, simplify.

### 3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform imperative tasks into verifiable goals:

| Instead of… | Transform to… |
| --- | --- |
| "Add validation" | "Write tests for invalid inputs, then make them pass" |
| "Fix the bug" | "Write a test that reproduces it, then make it pass" |
| "Refactor X" | "Ensure tests pass before and after" |

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let the model loop independently. Weak criteria ("make it work") require
constant clarification.

### 5. Push the work into a script, not into the context
The skill exists because deterministic scripts are cheaper than an LLM reading files — and that
applies to *building* it too. Before answering a question about this codebase by reading source,
ask whether a script (or an existing tool: `git`, `python -c`, the skill's own commands) can
produce the answer once, for every future session.

- Reach for a script or an existing tool first; write ad-hoc analysis in the terminal, not in
  prose you would have to re-derive next time.
- If you find yourself reading many files to answer one question, that question wants a script.
- The runtime rule still stands: the skill itself ships **stdlib only** (constraint 1). "Use a
  library" means use what is already on the machine while developing, never add a dependency to
  the skill.
- A new script pays for itself the second time it runs. A one-off shell pipeline is fine; copy it
  into `USAGE.md` if it will be wanted again.

### 6. Keep the docs in the same commit
Every document in this repo describes the skill to some reader. When behavior changes, they all
move with it — in the same commit, not in a follow-up that never comes.

There are **two disciplines**, and confusing them destroys the two files whose entire value is
that nobody rewrites them.

**Mirror current truth** — rewrite freely, so the file matches how the skill behaves *today*:

| File | Reader | Goes stale when |
| --- | --- | --- |
| `CLAUDE.md` | the next session working on the skill | the pipeline, script inventory, layout, constraints, colour/layout rules or the expected-numbers block change |
| `SKILL.md` | the agent using the skill | a command or an operating rule changes |
| `README.md` | a human evaluating/installing it | features, language table, requirements or the structure tree change |
| `USAGE.md` | a human running it by hand | any command's form or flags change |
| `templates/TAXONOMY.md` | anyone adding a field value | a `kind`/`layer`/severity/grade value changes |
| `PRESENTATION.html` | someone being shown the project | Features, Architecture, Honest limitations or Commands drift |

**Append, never revise** — these are records of what was actually done and thought at the time;
editing them to match the present is the one way to make them worthless:

| File | Discipline |
| --- | --- |
| `PROJECT_HISTORY.md` | extend with new phases; never rewrite a past entry to agree with the present |
| `prompt.md` | append the turn verbatim at the end of every turn (principle 7) |

**This file is not exempt.** `CLAUDE.md` describes the repo to its next session, so when the repo
changes, `CLAUDE.md` changes in the same commit. It has drifted before precisely because it was
the one doc outside its own rule — its pipeline diagram lost `brief` and nobody noticed.

A new script also needs: a docstring saying what it is and why, a line in the README structure
tree **and** in this file's script layout, a numbered command in `SKILL.md` if the agent should
call it, and its command form in `USAGE.md`.

The mechanical half of this rule is checked, so it cannot quietly rot:

```bash
python tools/check_docs.py
```

It verifies that every script is listed in `README.md` and named in `CLAUDE.md`, that every
`scripts/...` path quoted in any doc actually exists, and that every `kind`/`layer` value in
`taxonomy.py` is documented in `TAXONOMY.md`. It deliberately checks facts, never prose — keeping
the *words* honest is still the writer's job.

### 7. Log every exchange to `prompt.md`
This repo keeps a running transcript of its own construction. **At the end of every turn, append
that turn to `prompt.md`** — the user's prompt verbatim, then what you did and said.

```markdown
## [N] YYYY-MM-DD — <short title>

**Prompt**
> <the user's message, verbatim>

**Response**
<what you did: decisions made, files touched, commands run, what you found, what you told them>
```

Rules that keep the log worth having:

- **Append, never rewrite.** Earlier entries are the record of what was actually thought at the
  time; correcting them retroactively destroys the only reason to keep it.
- **Write it contemporaneously**, at the end of the turn, while the reasoning is still exact. A
  transcript reconstructed later is a summary, and should say so.
- **Record the reasoning and the misses**, not just the diff — why an approach was chosen, what a
  verification actually returned, and anything that turned out wrong. Git already stores the diff;
  the log's value is everything git cannot show.
- **Number entries sequentially** and keep them in chronological order.
- It is a plain log, not a doc for a reader: no need to keep it in sync with behavior the way
  principle 6 requires of `SKILL.md` / `README.md` / `USAGE.md`.
