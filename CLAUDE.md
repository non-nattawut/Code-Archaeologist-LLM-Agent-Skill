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

Three producers feed both maps -- Python (`py_extract.py`), JS/TS (`js_ts_extract.py`) and
Java/Go/C# (`ts_extract.py`) -- and since phase 2 all three are **tree-sitter**. There is one
parser in the build. Nodes from the third tier carry
`approx: true` everywhere they surface: graph, vault front-matter, `context.py`, the report's
health section, `brief.py`, and an `approx` chip in the explorer. Adding a tier means adding an
`extract_*_entities` in `build_wiki.py` and an `_analyze_*` in `build_flow.py`, nothing else.

An agent answers architecture questions by **querying the graph, then reading only the notes on the
returned path** — never by scanning source.

### Pipeline (what calls what)

```
archaeologist.py  project | flow | both | check | report | brief   <- the only entrypoint
  project  -> build_wiki -> build_graph ------------------\
  flow     -> build_flow ---------------------------------+--> render_explorer()
      both extract through: py_extract.py     (Python,        tree-sitter)
                            js_ts_extract.py  (JS/TS/JSX/TSX, tree-sitter)
                            ts_extract.py     (Java/Go/C#,    tree-sitter)
  report   -> report.py (scan_security + git_insights + analyze + metrics + debt + tests_map
                         + duplicates)
                                                                    -> data/report/<map>/
  brief    -> brief.py (reads the artifacts above, computes nothing)
  check    -> manifest.py (source hashes vs last build; --src optional, roots recorded)
                                                            \-> build_html.py -> data/explorer.html
```

### Where the scripts live

`scripts/` is grouped by role, and `archaeologist.py` is the only file at its root because it is
the only entrypoint:

```
scripts/
  archaeologist.py   the entrypoint
  paths.py           SKILL_ROOT / DATA_DIR / TEMPLATES_DIR, and the sys.path bootstrap
  core/     taxonomy.py  manifest.py  console.py  grammars.py
  extract/  build_wiki.py  build_graph.py  build_flow.py  py_extract.py
            js_ts_extract.py  ts_extract.py  apply_descriptions.py
  review/   analyze.py  scan_security.py  git_insights.py  metrics.py  debt.py
            tests_map.py  duplicates.py  report.py  brief.py
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

Importing `paths` puts `scripts/`, all four category dirs **and `<skill>/vendor`** on `sys.path`,
which is why sibling imports stay bare (`import taxonomy`), why `import tree_sitter` finds the
skill's own copy before the user's, and why every script still runs directly from any working
directory (constraint 3). `extract/js_bridge.py` keeps a `SCRIPT_DIR` of its own on top of that —
it needs the directory holding `js_extract.js`, not the skill root — and `console.py` and
`taxonomy.py` need no preamble at all because they touch neither `data/` nor a sibling.

`paths` is the one exception to "`core/` imports nothing of the skill's": `grammars.py` imports it
for `VENDOR_DIR`. That is deliberate — `paths` sits *below* the categories, imports nothing itself,
and re-deriving the skill root inside `core/` is exactly the duplication `paths` was created to
delete. Nothing else in `core/` may import a skill module.

- `taxonomy.py` owns every `kind`/`layer` value (mirrored in `templates/TAXONOMY.md`). Add values
  there, never inline. It also owns `LANG_BY_EXT` / `lang_of()` -- one answer to "what language is
  this file", read by `metrics.py` and `ts_extract.py`. And it owns **what counts as a test
  file** (`is_test_path` / `is_test_file`): path and filename conventions plus framework markers
  (`@Test`, `@SpringBootTest`, `[Fact]`, `#[test]`, `func TestX(t *testing.T)`). Nodes in test
  files get `layer: test`, which is why `analyze.py` never calls them dead code and
  `scan_security.py` skips them. Every pass must ask taxonomy, never re-implement the check.
- `grammars.py` owns "can this machine parse language X" -- the wheel table, lazy cached parsers,
  the exact `pip install` for anything missing, and the installed versions for the manifest. It
  lives in `core/` because `manifest.py` needs it, and `core/` may not import `extract/`. It also
  owns the two questions the vendor directory creates: **`origins()`** (did this resolve from
  `vendor/` or from site-packages — both can be installed, and `sys.path` order decides silently)
  and **`runtime()` / `runtime_error()`**, which turn an unloadable runtime into one sentence
  instead of a traceback. `runtime_available()` is a `find_spec`, `runtime()` is the real import;
  they disagree exactly when the wheels were built for another Python, so a caller reporting a
  skip must ask `runtime_error()` first — telling someone a grammar is missing when it is sitting
  right there sends them to reinstall what they already have.
- `py_extract.py` is the Python reader: the `ast` helpers of `build_flow.py`, `build_wiki.py` and
  `metrics.py` translated node-for-node, plus `read_source()`, which normalises newlines because
  `ast` was handed universal-newline text and tree-sitter is handed raw bytes -- without it a CRLF
  checkout hashes every node differently and silently misses the description cache. `ast` is **not**
  gone: it is the oracle, and `tools/check_py_oracle.py` parses every file both ways and fails on
  any disagreement about what was declared. That is the one reason to keep a stdlib parser around,
  and the only thing in the repo that still imports `ast`.
- `js_ts_extract.py` reads JS/JSX/TS/TSX from a tree-sitter parse: classes, functions, imports,
  Express and Nest routes, `fetch`/axios calls, and the JSX rule that makes a function a
  `kind: component`. It replaced the Node extractor behind that extractor's exact output contract
  (`find_js_files` / `extract_js_files` / `frontend_degraded`), which is why the port could be
  proved by diffing JSON rather than by reading code: the diff reported **identical output** on
  all six sample files and the graphs came out byte-identical. That reference (`js_bridge.py`,
  `js_extract.js`, `@babel/parser` 7.29.8) and the diff tool were deleted at step 4, so the
  comparison cannot be re-run -- `fd9c7d8` is its record. Four extensions, three grammars: `.tsx`
  will not parse under the TypeScript language and needs `tsx`.
- `ts_extract.py` reads Java/Go/C# from a real parse tree, and keeps the same
  `find_lang_files` / `extract_lang_files` contract the textual extractor before it had -- which is
  what let the port be verified by diffing the graph instead of by reading code. That extractor
  (`lang_extract.py`, 788 lines) was deleted at step 2 once the diff was clean; it is in git
  history if the comparison is ever wanted again. One shared consumer works
  in tree-sitter *field* names (`name`, `body`, `parameters`, `type`); only the `SPEC` table knows
  node-type spellings. Adding a language is a row there plus its receiver rule. tree-sitter gives
  declarations, bodies, param types and doc attachment; it does **not** give resolution, so
  `_calls` still answers `""` / `"Type"` / `"?"` exactly as before.
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
  `js_ts_extract.py` and `ts_extract.py` both record `endLine`, but `metrics.py` does not read
  it yet; its own complexity/depth/params now come off the CST like everything else). `report.py` derives `file_census` from it, so line counts have one definition.
- `search.py` is the "which nodes are these" filter over one graph (name/doc/layer/kind/lang/file
  plus `--calls` / `--called-by` / `--orphans`). It exists so neither the agent nor a human greps
  source to find a starting node.
- `context.py` is the per-node pack: graph facts + metrics/security/insights for one node and its
  neighbors, rendered under a hard `--max-chars` budget. Like `brief.py` it only reads artifacts.
- `debt.py` (markers in comments + orphan nodes/files) and `tests_map.py` (which nodes a test file
  names) are the two "what is rotting / what is untested" passes. Both are heuristics on purpose
  and neither feeds the health grade -- they report, they do not judge.
- `duplicates.py` is the third such pass: it reduces each node's body to a token shape
  (identifiers -> `ID`, literals -> `LIT`, comments gone) and clusters equal hashes, so a renamed
  copy still matches. It reads ranges from the graph (`source` + `end`), never re-parsing --
  which is why `build_flow.py` records `end` on every node it builds. Nodes marked
  `declaration: true` are skipped: a signature has a readable range but no body to compare.
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
  construction. Do not store it in a variable that `applyMap()` resets. Rail width works the same
  way — `--lw` / `--rw` set inline on `#app` by a drag, and nothing re-renders `#app`.
- **The rails resize, and that is all they do.** Two 9px grips (`.rsz`) straddle the pane borders.
  There is no collapse: it was built, and taken out again as a control nobody needed. The explorer
  is not resizable either — it takes every pixel the fixed blocks leave, and folding a section is
  how you give it more.
- **A rail may never eat the toolbar.** `setRail` caps a drag at what the centre still needs,
  measured by summing the toolbar's children — `clientWidth` would report "exactly what it already
  has" and let a drag ratchet controls off the right edge a pixel at a time. On a 1600px screen
  the toolbar needs nearly the whole centre, so a rail there can be narrowed but barely widened.
- **Below `max-height: 620px`** the rail gives up and scrolls as a whole — a 60px tree is worse
  than a scrollbar.
- **Dragging a node pins it** (force-graph sets `fx`/`fy` and leaves them), so `resetLayout()` is
  the only way back. It deletes `x`/`y`/`vx`/`vy` as well as clearing the pins, because `setView`
  alone only unpins and reheats — the simulation would restart from wherever the nodes were
  dragged. It hangs off the existing toolbar **reset** rather than a button of its own: the
  toolbar already wants ~930px against a 928px stage at 1600px wide, so one more control would
  make it clip by default.

## Hard constraints

1. **One parser per language, and every one of them degrades.** Python 3.10+.
   **Every language is tree-sitter, Python included**: the runtime plus the wheel for that
   language (`tree-sitter-python`, `tree-sitter-javascript` for `.js`/`.jsx`,
   `tree-sitter-typescript` for `.ts` *and* `.tsx`, `tree-sitter-java`, `tree-sitter-go`,
   `tree-sitter-c-sharp`) — wheels, no compiler, grammar bundled. Python no longer parses out of
   the box, and that is the promise phase 2 knowingly traded away: one engine, at the cost of
   "zero Python dependencies". **Node is not used at all**:
   it is not required, not checked for, and not installed. The skill has no `package.json`. **Grammars are installed on demand, not shipped**: a repo with no Go pays nothing for
   Go.
   **Every dependency installs inside the skill folder, never into the user's environment.**
   `npm install` → `<skill>/node_modules`; `pip install --only-binary :all: --no-cache-dir --target
   vendor` → `<skill>/vendor`. Both are git-ignored, neither can collide with the user's own
   versions, and deleting the skill folder removes every trace. Keep all three pip flags:
   `--target` is the point, `--only-binary :all:` refuses to compile, `--no-cache-dir` stops pip
   writing wheels outside the folder. Because `vendor/` is built for one interpreter version, a
   Python upgrade breaks it — that must surface as a named message telling the user to re-run the
   install, never as an `ImportError` traceback.
   Every one of those is optional at runtime and must fail the same way: **warn by name, skip
   those files, still build the rest.** A missing parser may never be silent, because a graph that
   is smaller for want of a wheel is indistinguishable from a graph of a smaller codebase — which
   is why `manifest.py` records the installed grammar set and `check` reports a change to it as
   staleness, and why `brief` prints a `SKIPPED` block naming the exact `pip install`.
   This is a *narrowing* promise, tracked in `docs/ROADMAP_PLAN.md`: the end state is one engine
   (tree-sitter) with `ast` kept only as a test oracle and Node gone from the runtime entirely.
   Until then, do not add a fourth engine.
2. **Deterministic.** Same source in, same bytes out. AI text enters only through
   `apply_descriptions.py` (cached by source hash, docstring wins first, deterministic fallback
   last).
3. **Paths resolve from the skill root**, so every script runs from any working directory.
4. **The explorer is one self-contained file, with no network at all.** Data *and* the graph
   library are embedded inline; it opens from `file://` with the network disabled. `force-graph`
   is vendored at `templates/vendor/` (see its README) and inlined by `build_html.py` through the
   `__VENDOR_JS__` placeholder. Nothing may reintroduce a `<script src>`, `<link href>` or
   `@import` — `bin/cli.js --self-test` fails the build if one appears. URL-shaped *strings* are
   fine and unavoidable (SVG/XML namespaces are identifiers the browser never fetches), so assert
   on resource loads, never on the substring `http`.
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

Expected on the current sample (it carries three deliberate smells -- a hardcoded key, interpolated
SQL, an innerHTML sink -- plus a pytest/unittest file, a `.test.ts`, a `.tsx` with two React
components, four API frameworks, and three languages from the approximate tier with two deliberate
hard cases, so the review path, the test path, the component path, every route shape and the
"drop rather than guess" rule all have something to find):

- structure graph: **25 nodes / 22 edges** -- 7 Python, 6 JS/TS, 12 approximate (6 Java, 3 Go,
  3 C#), of which `OrderCard` and `StatusBadge` are `kind: component` / `layer: ui`
- flow graph: **52 nodes / 32 edges, 16 endpoints, 0 pending** descriptions; 24 nodes `approx`,
  one of them `declaration: true` (`PricingRule.price`)
- routes, one per framework shape: FastAPI `OrderController.create_order`; Flask `orders` with
  **two** entries (`GET` + `POST /legacy/orders`) and `order_detail` (`<int:order_id>`); Express
  `createOrderHandler` (named handler) and the endpoint node `GET /orders/:id/status` (inline
  arrow); Nest `OrdersController.{create,findOne}` under the `@Controller("nest/orders")` prefix;
  Spring `OrderApiController.{create,findOne}` under `@RequestMapping("/java/orders")`; ASP.NET
  `InvoiceController.{Create,Find}` under `[Route("cs/[controller]")]` -> `/cs/Invoice`; Go
  `handleOrderEvents` / `recordOrderEvent` (named) and `GET /go/healthz` (inline literal)
- traces: `create_order -> place_order -> {save, charge}`, `get_order -> find_order -> get`, the
  Flask handler `orders -> place_order -> save`, and one per approximate language --
  `OrderApiController.create -> OrderWorkflow.place -> OrderArchive.save`,
  `InvoiceController.Create -> InvoiceService.Issue -> InvoiceStore.Put`,
  `handleOrderEvents -> EventService.Events -> EventStore.List`
- cross-stack: `submitOrder -> createOrder -> OrderController.create_order -> ...`, and
  `loadOrderHistory -> getOrderEvents -> handleOrderEvents -> ...` all the way into Go; structure
  `OrderCard -> {ApiClientModule, StatusBadge}`
- `getOrderStatus -> GET /orders/:id/status` is the **suffix fallback**: the call is
  `/api/orders/:id/status`, the router registers `/orders/:id/status`, and it links because
  exactly one route matches
- the two deliberate approximate-tier hard cases, **one of which is now resolved**:
  - **interface dispatch — resolved to the declaration.** `OrderWorkflow.place` calls
    `pricing.price()` through the `PricingRule` interface, and the edge
    `OrderWorkflow.place -> PricingRule.price` now exists, because a declaration-only member is
    extracted as a node (`declaration: true`, empty body, `end` at the end of the signature).
    The edge stops at the interface: **no edge is emitted to `FlatRate.price` or
    `TieredRate.price`**, which is why those two stay orphans. Picking one impl would be a guess
    and emitting both would trade the precision guarantee for recall.
  - **overloads still collapse to one node.** `InvoiceService.Total` is an overload pair sharing
    one id, because ids carry no arity. It now records `signatures: ["Total(request)",
    "Total(unitPrice, units)"]` so the fold is visible rather than silent, and the last one
    scanned no longer just wins the display.
  - The structure map *does* show `OrderWorkflow -> PricingRule` -- a declared field is a real
    reference even when the dispatch is not resolvable.
- a `declaration: true` node is a signature, not code: `duplicates.py` skips it (no body, no token
  shape) and `analyze.py` never calls it dead code (there is nothing in it to delete). Both guards
  are load-bearing, not decorative -- an uncalled declaration has no caller and would otherwise be
  reported as an orphan.
- grades: structure **D (69)**, flow **D (68)**; 4 risk findings each; 2 debt markers. Structure
  fell from C(71) when the interface impls were added -- that is the hard case being honest, not a
  regression. Flow fell from D(69) when the planted clone below was added: nothing calls it, so it
  is one more orphan.
- duplicates: **1 cluster, 2 nodes, 4 duplicated lines** -- `createInvoice` is `createOrder` with
  every identifier renamed, planted in `frontend/api_client.ts` so the clone pass has something to
  find. Renaming a variable in one copy must keep them clustered; changing an operator must split
  them.
- tests: 2 test files, flow **4/48 nodes named by a test**, and the two test nodes carry
  `layer: test` with call edges into `OrderService.place_order` / `OrderRepository.get`
- 529 lines across 22 files (py 126, java 102, csharp 90, ts 90, go 66, js 28, tsx 27)
- `archaeologist.py check --src ./sample_src` -> `stale: false` right after a build

Every grammar is optional and each one degrades the same way -- rename it out of `vendor/`, and
the build must still succeed with **one** named warning carrying the exact install command:

| Grammar removed | Warning | Structure | Flow |
| --- | --- | --- | --- |
| `tree_sitter_javascript` + `tree_sitter_typescript` | `frontend skipped`, naming **both** wheels | 19 / 19 | 37 / 23 |
| `tree_sitter_python` | `python skipped`, **once** for the whole run, not once per map | 18 / 12 | 39 / 21 |

Two checks stand in for the extractors that were deleted:

```bash
python tools/check_py_oracle.py                                   # must print: OK   0 disagreements
python tools/check_py_oracle.py .agents/skills/code-archaeologist/scripts
```

and the byte-identity of the committed graphs — rebuild, then `git diff` on
`data/structure/graph.json` and `data/flow/flow_graph.json` must be empty. That is the strongest
check available and it is what proved every port in phase 2: the JS/TS one, the Python one, and
`metrics.py`, none of which moved a single byte of either graph.

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
  into `docs/USAGE.md` if it will be wanted again.

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
| `docs/USAGE.md` | a human running it by hand | any command's form or flags change |
| `templates/TAXONOMY.md` | anyone adding a field value | a `kind`/`layer`/severity/grade value changes |
| `docs/PRESENTATION.html` | someone being shown the project | Features, Architecture, Honest limitations or Commands drift |

**Append, never revise** — these are records of what was actually done and thought at the time;
editing them to match the present is the one way to make them worthless:

| File | Discipline |
| --- | --- |
| `docs/PROJECT_HISTORY.md` | extend with new phases; never rewrite a past entry to agree with the present |
| `docs/prompt.md` | append the turn verbatim at the end of every turn (principle 8) |

**This file is not exempt.** `CLAUDE.md` describes the repo to its next session, so when the repo
changes, `CLAUDE.md` changes in the same commit. It has drifted before precisely because it was
the one doc outside its own rule — its pipeline diagram lost `brief` and nobody noticed.

A new script also needs: a docstring saying what it is and why, a line in the README structure
tree **and** in this file's script layout, a numbered command in `SKILL.md` if the agent should
call it, and its command form in `docs/USAGE.md`.

The mechanical half of this rule is checked, so it cannot quietly rot:

```bash
python tools/check_docs.py
```

It verifies that every script is listed in `README.md` and named in `CLAUDE.md`, that every
`scripts/...` path quoted in any doc actually exists, and that every `kind`/`layer` value in
`taxonomy.py` is documented in `TAXONOMY.md`. It deliberately checks facts, never prose — keeping
the *words* honest is still the writer's job.

### 7. Fix what you find, or write it down — never just mention it
Implementing one thing surfaces others: a stale claim in a tooltip, a number that contradicts a
doc, an artifact that is not as deterministic as the constraint says. Saying so in a chat reply
and moving on is the one option that is always wrong — the observation is gone the moment the
session ends.

Two outcomes, and which one applies is decided by whether a person has to choose something:

- **Fixable without a decision — fix it now**, in the same commit, and say so. A claim that is
  simply false, a message that misdiagnoses, an orphan your own change created: there is one right
  answer, so asking for it is just latency. Principle 3 still binds — fix the thing you found, not
  its neighbourhood.
- **Needs a judgement call — record it in `docs/ROADMAP_PLAN.md`** under *Found while
  implementing*, with what it is, why it is not obviously fixable, and a recommendation. It is
  reviewed with the phase, not mid-flight. Anything that changes output format, drops a
  user-visible field, or trades one guarantee for another belongs here.

The test for which bucket: *if I fix this my way and the user disagrees, have I destroyed
something?* If yes, write it down. If no, fix it.

### 8. Log every exchange to `docs/prompt.md`
This repo keeps a running transcript of its own construction. **At the end of every turn, append
that turn to `docs/prompt.md`** — the user's prompt verbatim, then what you did and said.

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
- **Append it before you commit, never after.** The entry is part of the change, so it belongs in
  the same commit as the work it describes — `git add docs/prompt.md` alongside everything else. A
  log written after the push is a second commit that nobody makes, which is how turns go
  unrecorded; and even when it does land, the entry is then separated from the diff it explains.
  If a turn ends without a commit, the entry is still appended — the trigger is the end of the
  turn, not the commit.
- **Record the reasoning and the misses**, not just the diff — why an approach was chosen, what a
  verification actually returned, and anything that turned out wrong. Git already stores the diff;
  the log's value is everything git cannot show.
- **Number entries sequentially** and keep them in chronological order.
- It is a plain log, not a doc for a reader: no need to keep it in sync with behavior the way
  principle 6 requires of `SKILL.md` / `README.md` / `docs/USAGE.md`.
