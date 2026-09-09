# Graph as many languages as possible

> ## Status: **not started.** Three phases, in order. Phase 3 is a gate, not a feature.
>
> | Phase | What it is | State | Commit |
> | --- | --- | --- | --- |
> | 1 — Resolve the edges the textual extractor drops | semantics, no new dependency | not started | |
> | 2 — Port extraction onto a tree-sitter engine | the structural change | not started | |
> | 3 — Full regression gate: nothing old may break | verification | not started | |
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
- The official `tree-sitter-<lang>` npm packages compile native code (`node-gyp-build`). They are
  **not** an option: `@babel/parser` is pure JS today and install must stay compiler-free.

### 2b. Per-language queries

tree-sitter's query language means a new language is a `.scm` file plus resolution rules rather
than an extractor. One query set per language answering: what is a class, a method, a function, a
call, a field, an annotation/attribute.

Start with the languages that already have a graph, so the port can be checked against a known
answer: Java, Go, C#, then JS/TS. Only then add new ones.

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

### 2e. Python stays on stdlib `ast` — non-negotiable

If tree-sitter owned Python parsing too, then "no Node" would mean **no graph at all**, where today
it means "no JS/TS, still a Python graph". That would break hard constraint 1's degradation
promise. Python keeps `ast`.

### 2f. `lang_extract.py` stays as the no-Node fallback

Which means this phase **adds** a code path rather than replacing one, and the two must agree.
Accept that cost explicitly, or decide the opposite explicitly — do not let it happen by accident.
If it stays, a test that runs both engines over `sample_src` and diffs the node sets is the only
thing that will keep them honest.

### Verify

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
