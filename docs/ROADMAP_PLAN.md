# Implement the README roadmap, phase by phase

> ## Status: **all six phases are complete.** The plan below is kept as the record of what was
> intended; the commits and `docs/prompt.md` are the record of what was done.
>
> | Phase | State | Commit |
> | --- | --- | --- |
> | 0 — Categorize `scripts/`, docs-sync rule, `tools/check_docs.py` | **done** | `d18de81` |
> | 1 — Frontend entities in the structure map | **done** | `dfb84c0` |
> | — `firstDocLine` adjacency fix (follow-up) | **done** | `29ff85f` |
> | 2 — Route/framework coverage (Flask, Express, Nest) | **done** | `bd983c8` |
> | 3 — Graph extractors for Java, Go and C# | **done** | `10e0309` |
> | 4 — Fully offline viewer (vendor force-graph) | **done** | `7ce1ff2` |
> | 5 — Duplicate-code clusters | **done** | `e229280` |
> | 6 — Roadmap rewrite and final doc pass | **done** | |
>
> This file was moved into the repo at the end of phase 3 so the remaining phases can be
> picked up on another machine. The phase sections below are the **original plan as written**
> — they are not revised as phases land, so where the implementation departed from the plan,
> the commit and `prompt.md` are the record of what was actually done. Departures worth
> knowing when reading the phase bodies below:
>
> - Phase 0c put the doc checker at `tools/check_docs.py`, not `scripts/check_docs.py`: it
>   reads repo files (`README.md`, `CLAUDE.md`) that no installed skill has.
> - Phase 3 did **not** add node-collision handling to `build_flow.py`. Two classes sharing a
>   name across languages still collide (last wins); the sample avoids it by naming the
>   polyglot services for different slices of the domain. C# overloads collapsing to one node
>   is a documented approximation, exercised by `InvoiceService.Total`.
> - Phase 4's literal check (`grep -c 'https\?://' data/explorer.html` -> `0`) is **not
>   achievable and was not the right test**. SVG/XML namespace URIs (`http://www.w3.org/2000/svg`)
>   are identifiers a browser never fetches, and the vendored licence header carries an
>   attribution URL. The goal — nothing *loads* over the network — is met and is now asserted in
>   `bin/cli.js --self-test` against resource-loading references (`<script src>`, `<link href>`,
>   `<img src>`, `@import`, `url(http…)`), which is what actually causes a request.
>
> - Phase 5 did **not** derive source ranges inside `duplicates.py` as written. `review/` imports
>   nothing from `extract/` today, and doing so would have made `report.py` re-spawn the Node
>   extractor. Instead `build_flow.py` now records `end` on every node -- it already had the value
>   from all three tiers and was discarding it -- so `duplicates.py` reads ranges from the graph
>   like every other review pass. Synthetic route nodes have no range and are skipped.
>
> Everything each phase promises to verify has been verified; `CLAUDE.md`'s expected-numbers
> block is the current truth for the sample.

## Context

`git pull` brought in a rewritten `README.md` (the old `ROADMAP.md` was deleted and folded into it).
Its **Roadmap** section (README.md:253-258) lists four open items. This plan implements all four,
one phase per item, each self-contained and verified against `sample_src` before the next begins —
after a Phase 0 of housekeeping the user asked for. The final phase rewrites the Roadmap section
to reflect what shipped.

The four items, and what each actually is:

1. **Frontend entities in the structure map.** `build_flow.py` reads `.ts/.js` via `js_bridge.py`;
   `build_wiki.py` does not (`build_wiki.py:57` globs `*.py` only, and never imports `js_bridge`).
   The result is that `sample_src/frontend/*.ts` exists in the flow map and is invisible in the
   structure map. Fix: teach `build_wiki.py` to consume the same extractor.
2. **Wider route/framework coverage.** `_route_of` (`build_flow.py:157`) only matches
   `@<obj>.<verb>("path")` on **class methods**. Flask's normal `@app.route` on a module-level
   `def` is missed entirely (the module-function loop at `build_flow.py:269` never calls it), and
   Express/Nest have no route detection at all.
3. **Graph extractors for Java / Go / C#.** Today these languages get line counts, complexity,
   risk scan, debt markers and test detection — but an empty graph, so `trace_path`, `search`,
   `context` and `analyze` return nothing for them.
4. **Duplicate-code clusters.** Does not exist.

Plus the second half of roadmap bullet 3, **a fully offline viewer**: `viewer.html:230` is the one
external resource in the whole product (`force-graph@1.43.5` from jsdelivr). Without network, five
of seven views render an empty box.

The user then added three structural requirements that come **before** the feature work, because
all five phases add scripts and change documented behavior — doing them afterwards means touching
everything twice:

5. **Categorize `scripts/`.** It is a flat folder of 22 files today and every phase below adds
   more. `paths.py`, `lang_extract.py` and `duplicates.py` would make it 25.
6. **`CLAUDE.md` must keep itself in sync with the project** — it is currently outside the
   docs-sync rule it defines.
7. **`PRESENTATION.html`, `README.md`, `PROJECT_HISTORY.md`, `USAGE.md`, `prompt.md` must stay in
   sync too.**

**Decisions taken with the user before planning:**

| Question | Decision |
| --- | --- |
| How far do frontend structure entities go? | Mirror Python's rule **+ React components** (`kind: component`, `layer: ui`) |
| Offline viewer | **Vendor** `force-graph.min.js` into the repo and inline it at build time |
| Which languages get graphs? | **Java + Go + C#, both maps**, as a documented approximate tier |

---

## Phase 0 — Categorize `scripts/`, and make the docs-sync rule real

Two independent pieces of housekeeping, done first so the five feature phases land in a structure
that holds and under a sync rule that covers every doc.

### 0a. Script layout

The dependency graph is already clean and already matches how `README.md`'s structure tree groups
these files visually — this phase just makes the grouping physical:

```
scripts/
├── archaeologist.py          the only entrypoint (stays at root)
├── paths.py                  one definition of where things live            [new]
├── core/      taxonomy.py  console.py  manifest.py
├── extract/   build_wiki.py  build_graph.py  build_flow.py
│              js_bridge.py  js_extract.js  apply_descriptions.py
├── review/    analyze.py  scan_security.py  git_insights.py  metrics.py
│              debt.py  tests_map.py  report.py  brief.py
└── query/     trace_path.py  context.py  search.py  build_html.py
```

Later phases then have an obvious home: `extract/lang_extract.py` (Phase 3),
`review/duplicates.py` (Phase 5).

**One finding to fix while moving:** `manifest.py` is documented in the README tree as part of the
extract group ("freshness hashes"), but it is imported by `scan_security`, `git_insights`,
`metrics`, `debt`, `tests_map` and `brief` for `SOURCE_EXTS` / `SKIP_DIRS` / `_rel_key` /
`rel_roots`. It is really the shared vocabulary for "what is a source file", so it belongs in
`core/` — and the README tree should say so.

**Mechanics.** Every script opens with the same four lines and 14 of them add
`sys.path.insert(0, SCRIPT_DIR)`:

```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)          # <- wrong once the file moves down a level
DATA_DIR = os.path.join(SKILL_ROOT, "data")
sys.path.insert(0, SCRIPT_DIR)
```

Replace it with one new `scripts/paths.py` that owns the layout and, as an import side effect,
puts every category directory on `sys.path`:

```python
SCRIPTS_ROOT = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT   = os.path.dirname(SCRIPTS_ROOT)
DATA_DIR     = os.path.join(SKILL_ROOT, "data")
TEMPLATES_DIR = os.path.join(SKILL_ROOT, "templates")
CATEGORIES   = ("core", "extract", "review", "query")
# ... insert SCRIPTS_ROOT and each category dir into sys.path
```

so each script's preamble becomes two lines:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import SKILL_ROOT, DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
```

**The payoff: every existing sibling import is untouched.** All ~35 `import taxonomy` /
`from manifest import ...` lines keep working exactly as they do now, because the category dirs
are on `sys.path`. Net change is 4 preamble lines → 2, with one definition of the layout.

**The cost, stated plainly:** every documented command path changes —
`scripts/trace_path.py` → `scripts/query/trace_path.py`. That is ~27 references in `USAGE.md`,
~28 in `SKILL.md`, plus `README.md`. `archaeologist.py` stays at the root, so the primary
documented commands (`both`, `report`, `check`, `brief`) are unaffected — and so is
`bin/cli.js`, whose `copyDir` (`bin/cli.js:148`) is already recursive via `fs.cpSync` and whose
self-test only invokes `scripts/archaeologist.py`.

Rejected alternative: leaving 20 two-line shims at the scripts root to preserve the old paths.
That reintroduces exactly the flat clutter this phase removes.

### 0b. The docs-sync rule (working principles 6 and 7)

Rewrite `CLAUDE.md` principle 6 to cover every document, and — the important part — to distinguish
the **two different sync disciplines**, because collapsing them would destroy the two files whose
whole value is that they are never rewritten:

**Mirror current truth** — rewrite freely so the file matches how the skill behaves today:

| File | Reader | Goes stale when |
| --- | --- | --- |
| `CLAUDE.md` | the next session working on the skill | pipeline, script inventory, constraints, colour/layout rules, or the expected-numbers verify block change |
| `SKILL.md` | the agent using the skill | a command or operating rule changes |
| `README.md` | a human evaluating/installing | features, language table, requirements, structure tree change |
| `USAGE.md` | a human running it by hand | any command's form or flags change |
| `templates/TAXONOMY.md` | anyone adding a field value | a `kind`/`layer`/severity/grade value changes |
| `PRESENTATION.html` | someone being shown the project | Features, Architecture, Honest limitations, or Commands sections drift |

**Append, never revise** — these are records, and correcting them retroactively destroys the only
reason to keep them:

| File | Discipline |
| --- | --- |
| `PROJECT_HISTORY.md` | extend with new phases; never rewrite past entries to match the present |
| `prompt.md` | append the turn verbatim at the end of every turn (principle 7, already written) |

`CLAUDE.md` gains an explicit self-referential clause: *this file describes the repo to its next
session; when the repo changes, this file changes in the same commit.* It is already drifting —
its pipeline diagram (`CLAUDE.md:23`) lists `project | flow | both | check | report` and omits
`brief`, which `README.md:220` does list.

### 0c. `scripts/paths.py`-backed doc check (small, and the reason the rule will hold)

A rule with no check is what let that diagram drift. Per working principle 5 ("push the work into
a script"), add a ~60-line `scripts/check_docs.py` that verifies only mechanical facts, never
prose:

- every `*.py` / `*.js` under `scripts/` appears in `README.md`'s structure tree **and**
  `CLAUDE.md`'s pipeline inventory;
- every `scripts/...` path quoted in `SKILL.md`, `USAGE.md`, `README.md` and `PRESENTATION.html`
  points at a file that exists;
- every `kind` / `layer` value in `taxonomy.py` appears in `templates/TAXONOMY.md`.

It joins the per-phase verification run below. Cut it if it feels like scope creep — but then the
sync rule is a wish rather than a check.

### Verify

- `python -m compileall -q .agents/skills/code-archaeologist/scripts` (recurses into the new dirs).
- Full pipeline + report on `sample_src` produces **byte-identical** `data/` to before the move —
  this is a pure refactor, so `git diff` on `data/` must be empty.
- Every script still runs standalone from its new path, from an unrelated working directory
  (constraint 3): spot-check `query/trace_path.py`, `review/debt.py`, `extract/build_wiki.py`.
- `node bin/cli.js --harness claude --target <tmpdir> --self-test` passes with no `cli.js` change.
- `check_docs.py` passes.

---

## Phase 1 — Frontend entities in the structure map

**Goal:** the structure map covers `.js/.jsx/.ts/.tsx` the same way the flow map already does.
Verify: `sample_src` structure graph goes 6 nodes → 9+, with a `OrderPageModule → ApiClientModule`
edge, and `OrderCard` present as `kind: component` / `layer: ui`.

This phase also introduces the **seam Phase 3 reuses**: `build_wiki.py` stops being "the Python
scanner" and becomes "the thing that renders normalized entity records", whatever produced them.

### Changes

(Paths below are post-Phase-0.)

- **`scripts/extract/js_extract.js`** — extend the emitted record:
  - add `endLine` (`node.loc.end.line`) to every class, method and function. Cheap here, and it is
    the missing piece behind `metrics.py`'s stated Python-only limitation (`metrics.py:20-22`) and
    behind Phase 5 covering JS.
  - add `jsx: true` on a function whose body contains a `JSXElement`/`JSXFragment` return, so the
    Python side can classify components without re-parsing.
  - keep `imports` (already extracted at `js_extract.js:118`, currently read by nobody).
- **`scripts/extract/build_wiki.py`** — the real work:
  - split `extract_entities()` into `extract_py_entities(roots)` and a new
    `extract_js_entities(roots)` that calls `js_bridge.find_js_files` / `extract_js_files` and
    returns the **same entity dict shape** already used at `build_wiki.py:135-144`
    (`{name, kind, source, bases, decorators, doc, methods, imports}`).
  - JS mapping, mirroring the Python rules at `build_wiki.py:106-118`:
    - a `class` → one entity, `bases` from `extends`.
    - all remaining top-level functions in a file → one `<Name>Module` entity via the existing
      `_module_entity_name()` (`build_wiki.py:121`).
    - **exception (React):** in `.jsx`/`.tsx`, a top-level function with `jsx: true` becomes its
      own entity with `kind: "component"` and layer `ui` — `taxonomy.KINDS` already allows
      `component` (`taxonomy.py:33`) and nothing has ever assigned it.
  - **import resolution is better than Python's, and should be**: Python matches import *names*
    against known entity names (`build_wiki.py:174-176`). JS `import ... from "./api_client"`
    names a *file*, so resolve the specifier to a path and emit an edge to that file's entities.
    Fall back to name matching for bare package specifiers.
  - **name collisions** (a JS `OrderService` and a Python `OrderService` both want
    `vault/OrderService.md`): deterministic first-wins with Python ordered first, and a printed
    `! skipped duplicate entity` warning. Must be deterministic — constraint 2.
  - layer for JS entities: `infer_layer(f"{name} {stem}")`, matching `build_flow.py:348`.
- **`templates/wiki_page_template.md`** — add a `lang:` front-matter field.
- **`scripts/extract/build_graph.py`** — copy `meta.get("lang", "py")` into the node dict at
  `build_graph.py:88-94`. Front-matter keys that are not explicitly copied are dropped today.
  This also fixes `report.py:76`, which currently counts every structure node as Python.
- **`sample_src/frontend/OrderCard.tsx`** — new, small: two components, one calling the other, so
  the `component` rule is actually exercised by the committed worked example.
- Docs: `README.md` (structure/flow table + language table), `USAGE.md`, `templates/TAXONOMY.md`
  (`component` is now assigned; `lang` now appears on structure nodes).

### Verify

```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./sample_src
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./sample_src
```
- `data/structure/graph.json` contains `ApiClientModule`, `OrderPageModule`, `OrderCard`.
- `OrderPageModule → ApiClientModule` edge present.
- `OrderCard` has `kind: component`, `layer: ui`, `lang: js`.
- `order_page.test.ts` entity carries `layer: test`.
- Re-run twice, `git diff` on `data/` is empty the second time (determinism).
- With `node_modules` temporarily renamed: build still succeeds, warns, emits Python-only vault.

---

## Phase 2 — Route / framework coverage (Flask, Express, Nest)

**Goal:** frontend→backend `http` edges resolve for Flask, Express and Nest, not just FastAPI.

### Schema change (do this first)

`route` is a single dict (`build_flow.py:264`), but Flask's `methods=["GET", "POST"]` is one
handler serving several verbs — and `_route_of` silently drops all but `elts[0]`
(`build_flow.py:174-177`). Replace `route: {method, path}` with **`routes: [{method, path}]`**.

Consumers to update in the same commit: `build_flow.py` (`_route_of`, `_api_edges`, `write_graph`,
`write_vault`), `analyze.py:148` (entry-point test), `report.py:72-89` (route census),
`context.py:123,156,177`, `templates/viewer.html` (route line in `renderFile`),
`templates/TAXONOMY.md:36-37`.

### Python (`build_flow.py`)

- Call `_route_of` in the **module-level function loop** (`build_flow.py:269-282`) — the single
  biggest gap; plain `@app.route("/orders")` on a `def` is the normal Flask shape.
- `_route_of` returns a **list**: every verb in `methods=[...]`, and every stacked route decorator
  on one function, not just the first match.
- Accept bare-name decorators (`ast.Name`, e.g. `@get("/x")`) alongside `ast.Attribute`.

### JS/TS (`js_extract.js` + `build_flow.py`)

- **Express** — a new top-level pass for `ExpressionStatement > CallExpression` shaped
  `<obj>.<verb>("/path", handler)`. Emit `routes: [{method, path, handler, line, endLine, doc,
  calls, http}]`. In `build_flow.py`: if `handler` names a function in that file, attach the route
  to that node; if it's an inline arrow, create an `endpoint` node id `"POST /orders"` and run its
  `calls` through normal resolution.
- **Nest** — enable babel's `decorators-legacy` plugin (`js_extract.js:28-34`) and read
  `node.decorators`. `@Controller('orders')` on the class gives a prefix; `@Get(':id')` /
  `@Post()` on a method give verb + suffix; join them. Class decorators also feed
  `infer_layer(...)` as real decorator names, closing the gap noted at `build_flow.py:348` where
  JS gets only `name + filename stem`.
- **axios instances** — track `const api = axios.create(...)` per file and treat `api.get(...)`
  like `axios.get(...)`. Deterministic, no guessing at arbitrary identifiers.

### Matching (`_api_edges`, `build_flow.py:196`)

- Index **every** verb of every route.
- Add a documented **unique-suffix fallback**: if the exact `(METHOD, path)` key misses, match a
  route whose normalized path is a suffix of the call's path (`/api/orders` → `/orders`) — **only
  when exactly one route matches**, so a mount prefix links but an ambiguous one does not.
- `_norm_path` (`build_flow.py:182`) also handles Flask converters `<int:id>` and Nest `:id?`.

### Sample + docs

Add `sample_src/api_flask/` (one `@app.route` module-level handler with `methods=["GET","POST"]`)
and `sample_src/api_express/` (one `router.post` with a named handler, one inline arrow). Keeping
FastAPI + Flask + Express in one sample is what proves "wider coverage" — a claim with nothing
exercising it is not a feature. Update `README.md`, `USAGE.md`, `templates/TAXONOMY.md`, and
`CLAUDE.md`'s expected-numbers block.

### Verify

- `sample_src` flow graph: endpoints from all three frameworks present with correct `routes`.
- New `type: "http"` edges from the new frontend calls to the new handlers.
- The Flask handler shows **two** entries in `routes`.
- Suffix fallback: a `/api/...` frontend call links; add a deliberately ambiguous pair and confirm
  it does **not** link.

---

## Phase 3 — Graph extractors for Java, Go and C#

**Goal:** point the skill at a Java/Go/C# codebase and get a real structure map and flow map, so
`trace_path`, `search`, `context` and `analyze` do something. Accuracy is roughly 95% for
structure (it reads declarations, which are textual) and ~85% for flow (overloads, interface
dispatch and lambdas are unresolvable without a type checker) — so **every node and edge from this
tier is marked `approx: true` and the report says the grade rests on approximate edges.**

This is the phase that changes a stated product promise. `README.md:125` currently reads "No
heuristic text parsing of source." That sentence must be rewritten, not quietly left standing.

### New: `scripts/extract/lang_extract.py`

One module, three dialect tables. It emits the **same normalized record shape `js_extract.js`
emits** (extended with `fields` and `params`), so `build_wiki.py` and `build_flow.py` gain a
second producer rather than a second code path:

```
{file, lang, imports: [...], classes: [{name, bases, decorators, doc, line, endLine,
  fields: {name: Type}, methods: [{name, doc, line, endLine, params: {name: Type},
  calls: [...], routes: [...]}]}], functions: [...]}
```

Technique, in order — this is what keeps it deterministic and keeps false positives low:

1. **Blank out comments and string literals first** (replace with same-length placeholders,
   preserving line numbers). Most naive-regex failure modes die here.
2. **Brace-match** to find class and method body ranges. Go and C# use `{}`; all three are
   brace languages, which is why these three and not Ruby/PHP/Python-likes.
3. **Per-language declaration regexes** over the blanked text:
   - **Java** — `class|interface|enum|record Name extends X implements Y, Z`; methods as
     `modifiers Type name(params) {`; fields as `modifiers Type name;`; annotations
     (`@RestController`, `@Service`, `@GetMapping("/orders")`) into `decorators` + `routes`.
   - **Go** — no classes: `type X struct {...}` is the entity, `func (r *X) Save(...)` is its
     method, `func Foo(...)` is a module function grouped into `<Name>Module` like Python.
     Routes: `mux.HandleFunc`, chi `r.Get`, gin `router.GET`.
   - **C#** — Java-shaped: `class X : Y, IZ` (all treated as `bases`), attributes
     `[ApiController]`, `[HttpGet("orders")]`, `[Route("api/[controller]")]`, properties
     `public Foo Bar { get; set; }` as fields.
4. **Call resolution mirrors the Python resolver** (`build_flow.py:385`) exactly:
   `this.field.m()` / `field.m()` → field's declared type; `param.m()` → param type; `var x = new
   Foo()` → local type; bare `m()` → same class. **Unresolved calls are dropped and counted in
   `ext`, never guessed** — same rule as today (`build_flow.py:423`).
   Constructor injection (Spring, ASP.NET DI) resolves for free here, because these languages
   declare parameter types mandatorily — the same trick `_self_attr_types` (`build_flow.py:110`)
   already uses on Python `__init__` annotations, but more reliable.

### Wiring

- **`scripts/core/taxonomy.py`** — own the `ext → lang` table (`LANG_BY_EXT`) alongside test detection,
  and consolidate `metrics.py`'s own language detection onto it. One definition of "what language
  is this file", the same way taxonomy already owns "is this a test file".
- **`build_wiki.py`** — third producer alongside Python and JS, through the Phase 1 seam.
- **`build_flow.py`** — `_analyze_lang(roots)` beside `_analyze_js`, merging into the same
  `methods` / `edges` structures.
- **`analyze.py`** — approximate edges still count toward the grade (excluding them would make the
  grade meaningless for a Java repo), but `report.py` adds a line to the health section whenever
  any node is `approx`, and `brief.py` says so too.
- **`templates/viewer.html`** — an "approx" marker on such nodes in `renderFile`. `lang` chips
  already render (`viewer.html:1104`); `java`/`go`/`cs` need no new colour, so the colour rules in
  `CLAUDE.md` are untouched.
- **`manifest.py`** — `SOURCE_EXTS` already covers `.java/.go/.cs`, so `check` works unchanged.

### Sample + docs

Extend `sample_src` into a polyglot example: `sample_src/services/orders_java/` (Spring:
`@RestController` → `@Service` → repository, constructor-injected), `orders_go/` (struct +
methods + `mux.HandleFunc`), `orders_cs/` (`[ApiController]` + DI). Same domain as the Python
side so traces read as one story. Regenerate all committed data and update `CLAUDE.md`'s
expected-numbers block.

Docs: `README.md` — the language table gains a **Graphs (approximate)** row, and the "No heuristic
text parsing" bullet at README.md:125 is rewritten to state exactly which tier is exact and which
is approximate. `SKILL.md` — tell the agent to surface the approximation when answering about an
approximate-tier repo. `USAGE.md`, `templates/TAXONOMY.md` (`approx`, new `lang` values).

### Verify

- Trace end-to-end inside each new service, e.g.
  `trace_path.py --from OrderController.create --to OrderRepository.save --graph .../flow_graph.json`.
- `search.py --lang java` returns the Java nodes; `context.py --node <java node>` renders.
- Structure map shows `extends`/`implements` edges.
- Re-run twice → byte-identical `data/`.
- Deliberate hard cases in the sample (an overload, a lambda, an interface with two impls) and
  confirm the extractor **drops** rather than invents those edges.

---

## Phase 4 — Fully offline viewer

**Goal:** `data/explorer.html` renders every view with the network disabled. Removes the single
carve-out in `CLAUDE.md` hard constraint 4.

- Vendor `force-graph@1.43.5` `dist/force-graph.min.js` (MIT) to
  `templates/vendor/force-graph.min.js`, with `templates/vendor/README.md` recording the exact
  source URL, version and licence, and the licence text preserved in the file header.
- `templates/viewer.html:230` — replace the `<script src=…>` with a `__VENDOR_JS__` placeholder.
- `scripts/query/build_html.py:123-125` — third substitution, reading the vendored file. It already
  does exactly this shape of work for `__TITLE__` / `__MAPS_DATA__`.
- Packaging needs **no change**: root `package.json` ships `.agents/` wholesale, and
  `bin/cli.js`'s `copyDir` (`bin/cli.js:148`) is recursive, so `templates/vendor/` rides along.
  Extend `--self-test` to assert the built page contains no `http` reference.
- Docs: `CLAUDE.md` constraint 4 (drop the CDN exception), `README.md` (the explorer section and
  the Requirements table), `USAGE.md`.

### Verify

- `grep -c 'https\?://' data/explorer.html` → `0`.
- Open in a browser with DevTools offline: all seven views, map switch, explorer filter, blast
  toggle, tab drill-through.
- Note the size delta in the commit message; confirm the page stays comfortably usable.

---

## Phase 5 — Duplicate-code clusters

**Goal:** find copy-pasted functions even when identifiers were renamed, and surface them in the
report and the explorer.

### New: `scripts/review/duplicates.py`

Modeled directly on `debt.py` / `tests_map.py`, which share one skeleton: module docstring →
`SCRIPT_DIR`/`SKILL_ROOT`/`DATA_DIR`/`DEFAULT_GRAPH`/`DEFAULT_OUT` → sibling imports with
`# noqa: E402` justifications → `build(roots, graph_path, out_path) -> dict` → `main()`. Same five
CLI flags (`--src`, `--graph`, `--out`, `--top`, `--format`), same `console.safe_stdout()`,
same exit-2 on a missing root, same `manifest.rel_roots()` in the payload.

Method:

1. Get each node's source line range. Python: `ast`, as `metrics.py:115-125` does — but store
   `end_lineno`, which it currently computes and discards. JS/TS: the `endLine` added in Phase 1.
   Java/Go/C#: the `endLine` from Phase 3.
2. Normalize the body to a token stream: strip comments and whitespace, replace every identifier
   with `ID`, every literal with `LIT`, keep keywords, operators and punctuation.
3. `sha1` the normalized stream. Group nodes by hash; a group of ≥2 is a clone cluster.
4. Floor at ~30 tokens so trivial getters and one-line delegates do not flood the output.

Payload (`data/report/<map>/duplicates.json`):
```
{generated, roots, graph, summary: {clusters, nodes_involved, duplicated_loc},
 clusters: [{hash, tokens, loc, nodes: [{id, source, layer, kind}]}]}
```

### Wiring

- **`report.py`** — the five-step checklist the other passes follow: import (`report.py:38-44`),
  one `dupes = duplicates.build(...)` line (`report.py:253-258`), a `data["duplicates"]` key
  (`report.py:260-266`), a conditional `## Duplicate code` section in `to_markdown` built with the
  existing `_table()` helper, and a console line.
- **`query/build_html.py:91-98`** — `report_for()` currently keeps only `analysis`/`files`/`security`/
  `insights`, which is why `metrics`, `debt` and `tests` never reach the page. Add a trimmed
  `duplicates` key (cluster summaries only, node ids not bodies) so the payload stays small.
- **`templates/viewer.html`** — a "Duplicate code" group in `renderPatterns()`
  (`viewer.html:1202-1230`) via the existing `push(title, items, render)` helper, each row using
  `nodeItem(id)` so `data-goto` drill-through works for free. Include it in the Patterns tab badge
  count (`viewer.html:1029`).
- Docs: `README.md` (Review table + structure tree), `SKILL.md` (numbered command), `USAGE.md`
  (command form), `templates/TAXONOMY.md`.
- Deliberate clone in `sample_src` — a renamed copy of an existing function — so the pass has
  something to find in the worked example, matching how the sample already carries three
  deliberate security smells.

### Verify

- `duplicates.py --src ./sample_src --format json` finds exactly the planted cluster.
- Renaming a variable in one copy keeps them clustered; changing an operator splits them.
- The cluster appears in `architecture_report.md` and in the explorer's PATTERNS tab, and clicking
  a row selects the node.

---

## Phase 6 — Roadmap rewrite and final doc pass

- Rewrite `README.md:253-258` to describe what shipped rather than what is planned, leaving a
  short, honest list of what is still open (Django URL-table routes, graphs for dynamic languages
  like Ruby/PHP/Elixir, duplicate detection below function granularity).
- `PRESENTATION.html` — a full pass over its Features, Architecture, Honest limitations and
  Commands sections. "Honest limitations" in particular must now say that Java/Go/C# graphs are
  approximate.
- `PROJECT_HISTORY.md` — **append** a new phase section covering this arc. Do not revise earlier
  entries.
- Run `check_docs.py` and fix whatever it reports across `README.md` / `USAGE.md` / `SKILL.md` /
  `templates/TAXONOMY.md` / `CLAUDE.md` / `PRESENTATION.html`.

---

## Cross-cutting rules (from CLAUDE.md, applied every phase)

- **Zero Python dependencies, stdlib only.** `lang_extract.py` is hand-written for exactly this
  reason. Node + `@babel/parser` remains the single exception, and must keep degrading gracefully.
- **Deterministic.** Same source in, same bytes out. Every collision, ordering and fallback rule
  above is specified to be deterministic; verified by building twice and diffing `data/`.
- **ASCII `print()` output** (cp874 console), `console.safe_stdout()` before echoing repo text.
- **Docs in the same commit, per the Phase 0b rule** — mirror-truth files (`CLAUDE.md`, `SKILL.md`,
  `README.md`, `USAGE.md`, `templates/TAXONOMY.md`, `PRESENTATION.html`) updated to match new
  behavior; append-only files (`PROJECT_HISTORY.md`, `prompt.md`) extended, never revised.
- **Regenerate committed sample data in the same commit** whenever `sample_src/` changes.
- **Append to `prompt.md` at the end of every turn** (working principle 7).
- One commit per phase.

## Verification run after every phase

```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./sample_src
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./sample_src
python .agents/skills/code-archaeologist/scripts/archaeologist.py check --src ./sample_src
python .agents/skills/code-archaeologist/scripts/check_docs.py
python -m compileall -q .agents/skills/code-archaeologist/scripts
node bin/cli.js --harness claude --target <tmpdir> --self-test
```

Plus, for any `templates/viewer.html` change: extract the inline `<script>` and parse it as a
**classic script** (`new vm.Script(code)`) — `node --check` wraps input in a CommonJS function and
would accept top-level `return` that a browser rejects. Then open `data/explorer.html` in a real
browser and exercise map switch, all seven views, explorer filter, blast toggle and tab
drill-through.
