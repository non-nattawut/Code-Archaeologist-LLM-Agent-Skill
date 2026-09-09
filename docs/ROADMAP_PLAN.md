# Graph as many languages as possible

> ## Status: **not started.** Three phases, in order. Phase 3 is a gate, not a feature.
>
> | Phase | What it is | State | Commit |
> | --- | --- | --- | --- |
> | 1 — Resolve the edges the textual extractor drops | semantics, no new dependency | not started | |
> | 2 — Port extraction onto a tree-sitter engine, remove `@babel/parser`, fixture every language | the structural change | not started | |
> | 3 — Full regression gate: nothing old may break | verification | not started | |
>
> **One decision is open and blocks 2b: does Python keep stdlib `ast`, or does everything move to
> a single engine?** Capability is proven either way — see the spike results. It is a trade, not a
> blocker, and it is recorded in 2e. Settle it before writing code, not during.
>
> The six phases of the previous roadmap are finished and this file has been rewritten for the
> next goal. Their record is **not** lost: `docs/PROJECT_HISTORY.md` carries the narrative and
> `docs/prompt.md` carries the turn-by-turn log, and both are append-only. Only this file — a
> working plan, never a record — was replaced.

## The goal

**Turn a project into a graph for as many languages as possible.** Today six languages get a
graph (Python, JS and TS parsed exactly; Java, Go and C# read textually) and eleven get the review
passes only — lines, complexity by file, risk scan, debt markers, test detection — but no nodes and
no edges.

Hand-writing an extractor per language does not reach that goal: `lang_extract.py` is 754 lines for
three languages, and each new one costs roughly the same again. tree-sitter is the one parser that
covers them all, so phase 2 replaces "another extractor" with "another query file".

### What tree-sitter does and does not buy

It must be said plainly here, because the whole plan depends on it: **tree-sitter equalizes
parsing, not resolution.** It hands back a concrete syntax tree. Deciding that `pricing.price()`
means `PricingRule.price` is a semantic question a syntax tree cannot answer, and it is exactly the
question the current extractor already answers — through declared types — for Java, Go and C#.

### Spike results — measured, not assumed (2026-09-09)

Run in a scratchpad against the real `sample_src`, before committing to any of this. Every claim
below is something the spike printed, not something believed:

| Question | Result |
| --- | --- |
| JSX detection for the `component` kind | **yes** — `jsx_element` x4 / `jsx_self_closing_element` x1 in `OrderCard.tsx`, and filtering functions by "contains JSX" picks out exactly `OrderCard` and `StatusBadge`, which is what Babel gives today |
| Type annotations for receiver resolution | **yes** — `type_annotation`, `required_parameter` (`id: string`, `body: object`) |
| Decorators for Nest routes | **yes** — `@Controller("nest/orders")`, `@Post()`, `@Get(":id")` read straight off the CST |
| Java annotations / C# attributes for Spring + ASP.NET routes | **yes** — `marker_annotation` (`@RestController`), `annotation` (`@RequestMapping("/java/orders")`), `attribute` (`Route("cs/[controller]")`) |
| Parse errors on any sample file | **none** — tsx, ts, py, java, cs all clean |

**Two findings that change the plan:**

1. **tree-sitter delivers phase 1a for free.** A Java interface method is simply a
   `method_declaration` whose `body` field is absent — the spike printed `body=NO  int
   price(OrderRequest request);` alongside the two implementations. No regex, no `throws` clause
   edge cases, no false-positive risk. See the sequencing note in phase 1.
2. **Runtime and grammars are ABI-coupled, and the convenient prebuilt source is stale.**
   `tree-sitter-wasms@0.1.13` is built with `tree-sitter-cli ^0.20.8` and **fails to load** under
   `web-tree-sitter@0.27` (`getDylinkMetadata` throws). The spike only ran after pinning the
   runtime back to `0.20.8`. Vendoring must therefore pin a *matched pair*, and the version we
   vendor is the version we are stuck on until someone rebuilds the grammars. See 2a.

Two consequences shape the phases:

1. **Phase 1 comes first and is independent of tree-sitter.** The edges being dropped today are
   dropped for semantic reasons, not parsing reasons. Fixing them on the current engine means the
   resolution logic is already correct and tested before it is ported. Porting first would mean
   debugging a new parser and new semantics at the same time.
2. **Graph quality after phase 2 will split by type system, not by grammar.** Languages that
   declare types (Kotlin, Rust, Swift, Scala, C, C++, and the existing Java/Go/C#) get real edges.
   Languages that do not (Ruby, PHP, Elixir, Lua) get nodes, files, structure and metrics but
   **sparse call edges**. That is still a large win against "no graph at all", and it must be
   labelled honestly rather than sold as exact — see phase 2d.

---

## Phase 1 — Resolve the edges the textual extractor drops

No new dependency, mostly one file. This is the phase that makes the Java/C# graphs actually
useful, and it is worth doing whether or not phase 2 ever happens.

> **Sequencing note, from the spike.** tree-sitter gives 1a for free (`method_declaration` with no
> `body` field), so the regex below is **throwaway work** — roughly 30 lines plus `throws`-clause
> and false-positive handling, all deleted in phase 2. Three honest options:
>
> - **Keep this order.** Accept the throwaway. You get working interface edges now, on an engine
>   that already works, and phase 1's resolution logic is proven before it is ported.
> - **Do 1b and 1c only**, and let phase 2 deliver 1a. Skips the throwaway regex, but nothing
>   improves until the port lands.
> - **Reorder**: port Java/C# to tree-sitter first, take 1a free, then do 1b on the new engine.
>   Fastest to the end state, but debugs a new parser and new semantics together — the exact thing
>   this plan was sequenced to avoid.
>
> Recommendation: **keep this order** unless phase 2 is starting immediately. 1b is the durable
> part and it is engine-independent; 30 lines of throwaway regex is a cheap price for having the
> resolution behaviour proven before the port.

### 1a. Extract declaration-only methods

`MEMBER_RE` (`extract/lang_extract.py:512`) ends, at line 518, with
`\((?P<params>[^)]*)\)[^;{=]*\{` — it **requires a body brace**. A Java interface method, an
`abstract` method and a C# interface member all end in `;`, so none of them ever match, and no node
is created.

That is the whole reason `OrderWorkflow.place -> PricingRule.price` is missing from the sample:
there is no `PricingRule.price` node to point an edge at. Verified against the built graph — the
flow map has `FlatRate.price` and `TieredRate.price` and no `PricingRule.price`.

- Add a sibling pattern matching the same modifiers/type/name/params terminated by `;`.
- Emit a node with an empty body, `end` equal to its start line, and a marker (`declaration:
  true`) so downstream passes can tell it apart.
- `duplicates.py` must skip these — a body-less node has no token shape. It already skips nodes
  with no recorded range; confirm that covers this rather than assuming it.
- `analyze.py` must not count them as dead code when an implementation exists. A declared method
  with implementations is the opposite of dead.

### 1b. Route calls through a declared interface type to the declaration

The receiver type is already resolved: `_params` and `_locals` give `pricing -> PricingRule`, and
the structure map already records `FlatRate -> PricingRule` and `TieredRate -> PricingRule`. Once
1a gives `PricingRule.price` a node, the existing resolver should find it with no new machinery.

- Verify this falls out of 1a rather than needing code. If it does not, the fix belongs in the
  same resolver that already handles declared types, not in a special case.
- **Do not** emit edges to every implementation. That would trade the precision guarantee — every
  edge shown is real — for recall, and the honest-limitations section promises the opposite.
- Optionally add an `implements` edge kind (`FlatRate.price -> PricingRule.price`) so the interface
  can be walked to its implementations in `trace_path.py`. If added it needs a colour in
  `LAYER_COLORS`/link styling and a line in `TAXONOMY.md`, in the same commit.

### 1c. Overloads

`InvoiceService.Total` is an overload pair collapsing to one node — a documented approximation and
a deliberate sample case. Decide one of:

- **Arity in the node id** (`InvoiceService.Total/1`, `/2`). Precise, but changes node ids, which
  are the join key for metrics, security findings, churn, notes and the vault. Every artifact keyed
  by id has to agree, and the committed sample data has to be regenerated.
- **One node, signatures recorded** as a field. Cheaper and non-breaking; the graph stays coarser
  but honest, and the note can list the signatures.

Pick the second unless the first proves necessary — it is the smaller change, and node identity is
load-bearing across seven artifacts.

### Verify

- `PricingRule.price` exists in the flow map; `OrderWorkflow.place -> PricingRule.price` is an edge.
- `FlatRate.price` and `TieredRate.price` are **no longer orphans** if 1b's `implements` edge is
  added; if it is not, they stay orphans and that stays documented.
- Structure map unchanged at 25/22 — this phase touches the flow map only.
- Every number in CLAUDE.md's expected-numbers block re-derived and updated: node/edge counts,
  grades (removing orphans will move them), orphan counts, duplicate clusters.
- The two hard cases in `sample_src` still behave as documented, with the documentation updated to
  say which one is now resolved.

---

## Phase 2 — Port extraction onto a tree-sitter engine

The structural change. Nothing here is worth starting until phase 1 is committed and verified.

### 2a. The bridge

Follow the `js_bridge.py` precedent exactly (`extract/js_bridge.py:74` — `shutil.which("node")`,
one clear warning, return `[]`, `frontend_degraded()` so callers do not prune state on a degraded
build).

- New `extract/ts_bridge.py` + `extract/ts_extract.js`, same shape.
- **Vendor the `.wasm` grammars** under `templates/vendor/` or a sibling, the way `force-graph` is
  vendored, rather than depending on `tree-sitter-wasms` — that bundle is 51.7 MB for 36 grammars
  and is a third-party convenience package, not the tree-sitter org's. Ship only the grammars we
  extract from, with a README recording version and provenance like the existing vendor README.
- **Pin the runtime and the grammars as a matched pair, and record both versions.** The spike hit
  this immediately: `tree-sitter-wasms@0.1.13` is built with `tree-sitter-cli ^0.20.8` and throws
  `getDylinkMetadata` under `web-tree-sitter@0.27`. Whichever pair is vendored is the pair the
  skill is pinned to; upgrading the runtime means rebuilding every grammar. Decide before
  vendoring whether to (a) pin to the stale prebuilt set, or (b) build current `.wasm` from the
  grammar repos with `tree-sitter build --wasm`, which needs Docker or emscripten **once**, at
  vendoring time, not on the user's machine.
- The official `tree-sitter-<lang>` npm packages compile native code (`node-gyp-build`). They are
  **not** an option: `@babel/parser` is pure JS today and install must stay compiler-free.

### 2b. Per-language queries

tree-sitter's query language means a new language is a `.scm` file plus resolution rules rather
than an extractor. One query set per language answering: what is a class, a method, a function, a
call, a field, an annotation/attribute.

Start with the languages that already have a graph, so the port can be checked against a known
answer: Java, Go, C#, then JS/TS. Only then add new ones.

**`@babel/parser` and `js_extract.js` are removed, not kept.** The spike proved parity on all three
things Babel is used for — JSX detection, type annotations, decorators — so once tree-sitter is in
the build for other languages, keeping Babel is purely additive: a second engine, a second code
path and 1.86 MB, for languages tree-sitter already covers. Neither argument that protects `ast`
applies to it: both need Node, so degradation is identical, and JS/TS ends up on exactly one engine
either way.

Port it **last** all the same. It is the only piece of phase 2 that replaces working, well-exercised
code for **zero user-visible gain** — every other port adds a language. Do it after the wins are
banked, and gate it on reproducing today's output: 6 JS/TS nodes, `OrderCard` and `StatusBadge` as
`kind: component` / `layer: ui`, the Nest and Express routes, and the `getOrderStatus ->
GET /orders/:id/status` suffix-fallback match.

### 2c. Receiver resolution per language

The part tree-sitter does not give us. For each language, how does `x.foo()` find a type — declared
parameter and local types, field declarations, constructor calls. This is where `lang_extract.py`'s
existing logic gets ported rather than rewritten; it is the valuable part of that file.

### 2d. Honest tiering — a schema change

Two tiers no longer describe reality. After the port there are three kinds of node:

| Tier | Meaning | Examples |
| --- | --- | --- |
| exact | parsed, receivers resolvable through declared types | Python, Java, C#, Go, Kotlin, Rust, TS |
| sparse | parsed exactly, but the source carries no types to resolve against | Ruby, PHP, Elixir, Lua |
| textual | the `lang_extract.py` fallback, when Node is absent | Java, Go, C# on a degraded build |

Replace the boolean `approx` with one three-valued field owned by `taxonomy.py`. It surfaces in
**six** places, all of which must move together: the graph, the vault note's front-matter
(`build_wiki.py`), `context.py`, `report.py`, `brief.py`, and the chip in `templates/viewer.html`.
`TAXONOMY.md` documents the values; `tools/check_docs.py` already enforces that.

### 2e. Python and `ast` — an open decision, not a foregone one

The stated goal is **one engine**. Capability is not the obstacle: the spike parsed
`order_service.py` cleanly (`function_definition`, `class_definition`, `call`, `attribute`, no
errors). So this is a trade, not a blocker, and it needs deciding before 2b starts rather than
during it.

**A correction to an argument made earlier in this plan's own history:** determinism was cited
against removing `ast`. That was wrong-headed. The determinism hazard is having *two possible*
engines for one language, where the same source yields different graphs depending on what is
installed. Removing `ast` outright gives Python exactly one engine and is therefore **more**
deterministic, not less. Determinism argues *for* consolidation.

What actually costs something:

| | Keep `ast` for Python | One engine (remove `ast`) |
| --- | --- | --- |
| Engines to maintain | 2 | **1** |
| Determinism | fine (one engine per language) | fine |
| No Node on the machine | Python graph still builds | **nothing builds** |
| README's "the Python side has **zero dependencies**" | true | **false** — must be rewritten |
| `SKILL.md:39` "If Node itself is missing, do not stop — build anyway" | stays | **deleted** |
| Hard constraint 1 | unchanged | **rewritten** |
| `metrics.py` (15 `ast.` call sites) | stays as-is | ported to CST |
| "Per-node metrics are Python-only" limitation | stays | **retired** |

Note the metrics row cuts both ways: CST-based complexity has to be written for the other languages
*regardless*, so keeping `ast` does not avoid that work — it only means Python keeps a second,
better implementation of it.

The one thing that genuinely gets worse is the bottom-left cell. The documented install path is
already `npx`, so Node is present for most users — but "works with Python and nothing else" is a
headline property of this skill, not an incidental one.

**Recommendation: keep `ast`.** It is free, always present, and it is what lets the tool run
where nothing else is installed. "One engine" is worth real money for Java/Kotlin/Ruby, where the
alternative is hand-written extractors; it is worth almost nothing for Python, where the
alternative is a stdlib module that costs zero bytes and never breaks.

**If the decision is one engine anyway** — a legitimate call, and the user's to make — then this
phase additionally: rewrites hard constraint 1 in `CLAUDE.md`, deletes the degradation instruction
in `SKILL.md`, corrects the README headline and the Requirements table, ports `metrics.py` to the
CST, and drops 2f entirely (no fallback engine to keep in sync). Record the decision here before
starting 2b; do not let it be settled by whichever code gets written first.

### 2f. `lang_extract.py` as the no-Node fallback — only if 2e keeps `ast`

Moot if 2e chooses one engine: with no Python fallback there is no point keeping a Java one.

If `ast` stays, then keeping `lang_extract.py` means this phase **adds** a code path rather than
replacing one. The question is sharper than "do the two engines agree?" — it is a **determinism**
question. Two engines for the same Java file means the same source produces different graphs
depending on whether Node is installed. That is worse than today's situation, where no Node means
JS/TS are simply *absent*: a subset, not a different answer.

The mitigation is the tier field from 2d: every node records which engine produced it, so the
difference is visible in the artifact rather than silent. Plus a test that runs both engines over
`sample_src` and diffs the node sets.

The alternative — delete `lang_extract.py` and let Java/Go/C# vanish without Node, exactly as
JS/TS do today — is simpler, honest, and consistent with how the skill already behaves. Prefer it
unless the textual fallback is genuinely wanted.

### 2g. A fixture that exercises every supported language

**Every language the skill claims to graph must have something in the repo that proves it does.**
Without this, adding a grammar is an unverified claim — and the failure is silent: a language whose
queries are subtly wrong produces zero nodes and nobody notices.

**Do not put them all in `sample_src/`.** That directory has a different job, and the two conflict:

- It **ships to every user** — `sample_src/` is in `package.json`'s `files` allowlist.
- It is the *readable worked example*: 22 files, 528 lines, seven languages, with the cross-stack
  traces (`submitOrder` all the way into Go) that make the point of the tool. Adding eleven more
  languages roughly triples it and it stops being readable.
- Its numbers are pinned by a **46-line** expected-numbers block in `CLAUDE.md`, in prose. Every
  language added perturbs node counts, edge counts, grades, orphan counts, LOC totals and the
  language-mix percentages — so each new language means rewriting all of it by hand.

Recommendation: **split the two roles.**

| | `sample_src/` | new `tests/fixtures/langs/<lang>/` |
| --- | --- | --- |
| Job | readable worked example | prove extraction works |
| Ships to users | yes | no — the `files` allowlist excludes it with no further action |
| Size | stays as it is | one small file per language |
| Expectations live in | CLAUDE.md prose | a JSON table asserted by a script |

Each per-language fixture is deliberately minimal and always the same shape, so the fixtures are
comparable and a new language is a copy-and-translate rather than a design exercise:

- one type with a method,
- a second type it calls **through a declared field or parameter**, so receiver resolution is
  actually exercised rather than just parsing,
- a route, where the language has a mainstream web framework,
- a test file, so `taxonomy.is_test_file` is exercised per language.

**The dynamically typed fixtures are the important ones.** Ruby, PHP, Elixir and Lua should assert
*sparseness* — nodes yes, edges few or none — because that is what proves the `sparse` tier from 2d
is telling the truth. A fixture that quietly returns zero edges and is never asserted is how the
honest-limitations section starts lying.

Expectations belong in a **JSON table plus a small runner**, not in CLAUDE.md prose (working
principle 5: push the work into a script). Then adding a language is one fixture file and one row,
and the assertion is `python tools/check_langs.py`, not a human re-reading 46 lines. A new script
also needs its README/CLAUDE.md entries and a line in `docs/USAGE.md`.

If the decision is to put everything in `sample_src/` anyway, that is a legitimate call — but then
the expected-numbers block has to be regenerated by a script rather than maintained by hand, or it
will rot within two languages.

### Verify

- Every language listed as supported has a fixture, and the runner asserts it — no language ships
  on the strength of "the grammar loaded".
- Java/Go/C# graphs built by tree-sitter match or beat the phase-1 numbers, with every difference
  explained in the commit message rather than absorbed silently.
- With `node_modules` renamed away: the build still succeeds, warns once, and falls back to
  `lang_extract.py` for Java/Go/C# and to Python-only for the rest.
- `bin/cli.js --self-test` still passes, including the offline assertion.
- Determinism: build twice, diff `data/`, only timestamps differ.

---

## Phase 3 — Full regression gate: nothing old may break

**Explicitly requested, and it is a gate rather than a feature: phases 1 and 2 are not done until
this passes.** Every capability the skill had before this roadmap must still work exactly as it
did, or be knowingly and visibly changed. Anything found broken is fixed here, not deferred.

Work through the whole surface, not a spot check:

**Pipeline** — `project`, `flow`, `both`, `report`, `check`, `brief` from the repo root and from a
different working directory (constraint 3).

**Query tools** — `search.py` by name/doc/layer/kind/lang/file and `--calls` / `--called-by` /
`--orphans`; `trace_path.py --from/--to`, `--impact-of`, `--impact-of-diff`; `context.py --node`
under its `--max-chars` budget. Every documented trace in CLAUDE.md still resolves, including the
cross-stack ones and the suffix-fallback route match.

**Review passes** — `analyze.py`, `scan_security.py`, `git_insights.py`, `metrics.py`, `debt.py`,
`tests_map.py`, `duplicates.py`. Grades, finding counts, churn, clone clusters.

**Language fixtures (2g)** — every supported language still extracts what its row claims, including
the dynamically typed ones whose rows assert sparseness. A language that silently drops to zero
nodes is the failure this gate exists to catch.

**Explorer** — map switch, all seven views, explorer filter, folder twisty, rail drag, blast
toggle, Tests checkbox, reset layout, tab drill-through, PNG export. Console clean. Classic-script
parse first.

**Degradation** — no Node at all; Node but no `node_modules`; a source root that has moved.

**Docs** — `tools/check_docs.py`, and every mirror-truth file updated: `CLAUDE.md` (pipeline,
script inventory, expected numbers, colour and layout rules), `SKILL.md`, `README.md`,
`docs/USAGE.md`, `templates/TAXONOMY.md`, `docs/PRESENTATION.html` — whose honest-limitations
section needs the new three-tier story and a corrected per-language claim.

### Verify

Every command in the block at the bottom of this file, plus a written note in `prompt.md` of
anything that broke and how it was fixed. A regression found and fixed is the point of this phase;
a regression found and left is a failure of it.

---

## Cross-cutting rules (from CLAUDE.md, applied every phase)

- **Zero Python dependencies, stdlib only.** Node remains the single exception and must keep
  degrading gracefully. Phase 2 widens what Node buys; it must not widen what its absence costs
  beyond what 2e and 2f allow.
- **Deterministic.** Same source in, same bytes out. Verified by building twice and diffing `data/`.
- **ASCII `print()` output** (cp874 console); `console.safe_stdout()` before echoing repo text.
- **Docs in the same commit.** Mirror-truth files (`CLAUDE.md`, `SKILL.md`, `README.md`,
  `docs/USAGE.md`, `templates/TAXONOMY.md`, `docs/PRESENTATION.html`) rewritten to match new
  behavior; append-only files (`docs/PROJECT_HISTORY.md`, `docs/prompt.md`) extended, never revised.
- **Regenerate committed sample data in the same commit** whenever `sample_src/` or the graphs change.
- **Append to `prompt.md` at the end of every turn** (working principle 7).
- One commit per phase, unless a phase splits cleanly into independently verifiable pieces.

## Verification run after every phase

```bash
python -m compileall -q .agents/skills/code-archaeologist/scripts
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./sample_src
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./sample_src
python .agents/skills/code-archaeologist/scripts/archaeologist.py check --src ./sample_src
python .agents/skills/code-archaeologist/scripts/archaeologist.py brief
python tools/check_docs.py
node bin/cli.js --harness claude --target <tmpdir> --self-test
```

Note `tools/check_docs.py`, not `scripts/check_docs.py` — it reads repo files (`README.md`,
`CLAUDE.md`) that no installed skill has.

Plus, for any `templates/viewer.html` change: extract the inline `<script>` and parse it as a
**classic script** (`new vm.Script(code)`) — `node --check` wraps input in a CommonJS function and
would accept top-level `return` that a browser rejects. Then open `data/explorer.html` in a real
browser and exercise map switch, all seven views, explorer filter, blast toggle and tab
drill-through.
