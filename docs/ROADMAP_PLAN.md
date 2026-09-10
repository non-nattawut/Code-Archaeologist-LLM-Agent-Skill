# Graph as many languages as possible

> ## Status: **phase 1 done; phase 2's deletion order is complete — one engine, six of six steps.** Phases 3 and 4 are verification, not features.
>
> | Phase | What it is | State | Commit |
> | --- | --- | --- | --- |
> | 1 — Resolve the edges the textual extractor drops | semantics, no new dependency | **done** | `e8464f8` |
> | 2 — Port to tree-sitter, delete the three old extractors, fixture every language | the structural change | **all 6 deletion steps done**; 2d and 2g remain | `8974c27`, `67d4df4`, `e7bfb09`, `fd9c7d8`, `df5fb0b`, this commit |
> | 3 — Full regression gate: nothing old may break | does it still run | not started | |
> | 4 — Audit every graph and node feature for silent wrongness | is what it produced right | not started | |
>
> ### Where phase 2 actually stands
>
> The deletion order in 2e has six steps. **Nothing has been deleted yet**, which is correct — each
> old engine is the reference its replacement is checked against.
>
> | Step | What | State |
> | --- | --- | --- |
> | 1 | Java/Go/C# ported to tree-sitter, matching the phase-1 numbers | **done** — `8974c27` |
> | 1b | Move the install into `<skill>/vendor/` instead of the user's Python | **done** — `67d4df4` |
> | 2 | delete `lang_extract.py` | **done** — `e7bfb09` |
> | 3 | JS/TS ported, diffed against `js_extract.js` | **done** — `fd9c7d8`; the diff is `tools/diff_js_extractors.py`, reporting **identical output** on all 6 files |
> | 4 | delete `@babel/parser`, `js_extract.js`, `js_bridge.py`, the skill's `package.json` | **done** — this commit; `node_modules/`, `package-lock.json` and `tools/diff_js_extractors.py` went with them |
> | 5 | Python ported; `ast` oracle reports 0 disagreements | **done** — this commit; `tools/check_py_oracle.py` reports **0 disagreements** over 34 files |
> | 6 | drop `ast` from the build path (it stays forever as the oracle) | **done** — with step 5; no shipped script imports `ast`, only `tools/check_py_oracle.py` does |
>
> **Also done, outside the step list** (step 1 pulled these in because a per-language grammar is a
> new way for a graph to be quietly wrong): `core/grammars.py`; the installed grammar set recorded
> in the manifest; `check` reporting a grammar change as staleness; a `SKIPPED` block in `brief`;
> the exact install command in every message; and hard constraint 1 rewritten, since "zero external
> Python dependencies" stopped being true.
>
> **What 1b shipped**, all three states verified rather than reasoned about: `paths.VENDOR_DIR`
> prepended to `sys.path` (vendored wins over site-packages); `vendor/` git-ignored beside
> `node_modules/`; `grammars.install_hint()` emitting the full
> `--only-binary :all: --no-cache-dir --target` command; `grammars.origins()` answering which copy
> is actually in use; and `grammars.runtime()` / `runtime_error()` turning an unloadable wheel into
> one named sentence. `SKILL.md` no longer tells the agent to ask permission before installing,
> because the install no longer touches anything of the user's.
>
> **1b did not** change `bin/cli.js` (the wheels are interpreter-specific and the installer does
> not know which Python will run the skill — decided in 1b's requirements), and did not vendor
> anything for JS/TS, which already had this shape.
>
> **What steps 5 and 6 shipped:** `extract/py_extract.py` (the `ast` helpers translated
> node-for-node), `build_flow.py`, `build_wiki.py` and `metrics.py` moved onto it, and
> `tools/check_py_oracle.py` as the permanent second opinion. Both graphs came out
> **byte-identical**, and every metric -- complexity, depth, params, LOC -- unchanged. `ast` is off
> the build path entirely, which is step 6, so the two landed together.
>
> **What step 3 shipped:** `extract/js_ts_extract.py` (JS/JSX/TS/TSX on tree-sitter) behind the
> Node extractor's exact contract, `tools/diff_js_extractors.py` as the equivalence check, and
> `javascript` / `typescript` / `tsx` registered in `grammars.py`. The graphs came out
> **byte-identical** to the ones Babel produced, which is the strongest form the gate could take.
> Note it did **not** need 2b's `TAGS_QUERY` route: the extractor walks the tree directly, the same
> way `ts_extract.py` does, so the thin-tags problem never arose.
>
> **Not done, and not started** — none of this is blocked, it simply has not been reached:
> 2b's supplementary query for TypeScript (its shipped `TAGS_QUERY` yields zero captures on real
> implementation files) — now moot for JS/TS, see above; 2c beyond the ported languages; **2d's `approx` -> `exact`/`sparse`
> tier rename**, deliberately deferred so step 1 could be verified by equivalence; 2f; and **2g's
> per-language fixtures and `tools/check_langs.py`, which no language yet has**. Every one of the
> eight open concerns below is still open — resolution parity for Python (concern 1) is the one
> that gates step 5, and node id collisions (concern 2) is the one that gets more expensive the
> longer it is left.
>
> Languages added since the port began: **none.** Step 1 was a like-for-like port of the three that
> already had graphs, which is what made it checkable; the goal of graphing *more* languages is not
> advanced until 2g's fixtures exist to keep the supported list honest.
>
> **Phase 2, step 1 outcome — Java/Go/C# ported, nothing deleted.** `ts_extract.py` replaced
> `lang_extract.py` behind the *same* `find_lang_files` / `extract_lang_files` contract, so both
> graph builders were a one-line import change and the port could be verified by diffing the graph
> rather than by reading code. Result: **identical node ids and identical edges** on both maps
> (25/22 and 52/32), same grades, same traces, deterministic.
>
> Four differences, all of them the new engine being more correct, none of them structural:
> `EventStore.Append.ext` 0 -> 1 (a real `append(...)` builtin call the regex missed), and three
> docs that are now the *whole* comment block instead of its first line.
>
> Bugs the diff caught in my own port, worth recording because none would have failed loudly:
> Go's receiver `parameter_list` was fed to a helper expecting a declaration (methods silently
> became free functions); C#'s field type was read as `InvoiceStore _store` (type *and* name);
> and `map[string]string` was being squeezed into a type called `mapstringstring` — a bracket
> strip turns a constructed type into something that *looks* like an identifier, so the obvious
> "is it an identifier" guard passed it.
>
> Also landed here, because a per-language grammar is a new way for a graph to be quietly wrong:
> `core/grammars.py`, the grammar set recorded in the manifest, `check` reporting a grammar change
> as staleness, a `SKIPPED` block in `brief`, and the exact `pip install` in every message.
>
> Deliberately **not** done in this step: the `approx` -> `exact`/`sparse` tier rename (2d). It
> touches six surfaces and would have destroyed the equivalence property that made this step
> verifiable. The wording everywhere was corrected from "read textually" to "parsed exactly,
> resolved approximately", which is now what `approx: true` means.
>
> **One thing step 1 got wrong**, corrected in the plan and scheduled as step 1b: it told the agent
> to `pip install` into the user's own Python environment. It should install into
> `<skill>/vendor/`, exactly as `@babel/parser` installs into `<skill>/node_modules`. See
> "Install into the skill directory" under 2a. The packages installed during step 1 are on the
> system Python and stay working either way -- 1b prefers a vendor directory and falls back to
> site-packages.
>
> **Phase 1 outcome.** 1a and 1b landed together and 1b needed no code, exactly as predicted: once
> `PricingRule.price` exists as a node, the existing resolver finds it. Flow map 51/31 -> 52/32,
> structure unchanged at 25/22, both grades unchanged. 1c took the cheap option — one node, every
> signature recorded — so no node id changed and no artifact needed re-keying. The optional
> `implements` edge was **not** added: it needs a colour, a taxonomy entry and explorer work for a
> traversal nobody has asked for yet, so `FlatRate.price` / `TieredRate.price` stay orphans and
> stay documented as such. The ~30 lines of throwaway regex the sequencing note predicted came to
> about 25, and phase 2 deletes them.
>
> **Decided (2026-09-09): one production engine, tree-sitter, via the Python binding — no Node at
> runtime.** `@babel/parser`, `js_extract.js`, `js_bridge.py`, `lang_extract.py` and the skill's own
> `package.json` are all deleted; `ast` leaves the build path and stays only as a test oracle. Node
> survives solely as the `npx` installer (`bin/cli.js`). The accepted cost is
> `pip install tree-sitter tree-sitter-<lang>` — wheels, no compiler, grammar bundled per language,
> ~9.4 MB for five — where the skill previously needed nothing. See 2a and 2e.
> *(Amended 2026-09-10: those wheels go into `<skill>/vendor/`, not the user's environment.)*
>
> **Nothing is deleted before the port that replaces it is verified against it** — the old engine
> is what proves the new one correct, so the deletion order in 2e is structural, not cautious.
>
> **Read "Open concerns" before writing code.** Eight items, none blocking, all of them cheaper to
> decide now than to discover mid-port — node id collisions across twenty languages and the
> unproven resolution parity being the two that would hurt most.
>
> The six phases of the previous roadmap are finished and this file has been rewritten for the
> next goal. Their record is **not** lost: `docs/PROJECT_HISTORY.md` carries the narrative and
> `docs/prompt.md` carries the turn-by-turn log, and both are append-only. Only this file — a
> working plan, never a record — was replaced.

## The goal

**Turn a project into a graph for as many languages as possible.** Six languages get a graph
(Python via `ast`, JS/TS via `@babel/parser`, and — since phase 2 step 1 — Java, Go and C# via
tree-sitter) and eleven get the review passes only — lines, complexity by file, risk scan, debt
markers, test detection — but no nodes and no edges.

Hand-writing an extractor per language does not reach that goal: `lang_extract.py` was 754 lines
for three languages, and each new one cost roughly the same again. tree-sitter is the one parser
that covers them all, so phase 2 replaces "another extractor" with "another table row". Step 1
proved the shape: the three ported languages now share one consumer, and what differs per language
is a `SPEC` entry plus its receiver rule.

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

**Re-run through the Python binding, same results** (spiked via `tree-sitter-language-pack`, which
2a then rejects for a packaging reason, not a capability one)**:** JSX x4/x1,
all three Nest decorators, C# attributes x4, Java `interface_declaration` and the `body=NO`
declaration-only method, Go `function_declaration` x3 in `router.go`, no parse errors anywhere.
And the `ast` oracle run entirely in-process: **6 files, 0 disagreements.** So the Python route is
proven to the same depth as the Node one, which is why 2a chooses it.

**Two findings that change the plan:**

1. **tree-sitter delivers phase 1a for free.** A Java interface method is simply a
   `method_declaration` whose `body` field is absent — the spike printed `body=NO  int
   price(OrderRequest request);` alongside the two implementations. No regex, no `throws` clause
   edge cases, no false-positive risk. See the sequencing note in phase 1.
2. **The Node route is ABI-coupled and its prebuilt grammars are stale — which is part of why it
   lost.** `tree-sitter-wasms@0.1.13` is built with `tree-sitter-cli ^0.20.8` and **fails to load**
   under `web-tree-sitter@0.27` (`getDylinkMetadata` throws); the Node spike only ran after pinning
   the runtime back to `0.20.8`. Vendoring would mean pinning a matched pair and being stuck on it
   until someone rebuilt every grammar. The Python packages have no such coupling — one version,
   one install. See the comparison in 2a.

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

### 2a. The Python binding — no bridge, no Node

**Decided: the Python library, not the Node one.** Both were spiked; the Python route wins on every
axis except that it is a `pip install`.

```python
from tree_sitter_language_pack import get_parser
tree = get_parser("java").parse(source_bytes)
```

**Use the per-language wheels, not `tree-sitter-language-pack`.** The pack looked ideal — 371
languages, 5.9 MB — until `language_count()` returned **6**: it *downloads grammars on demand* into
a user cache at first use. That means a network call at first run and nothing vendored, which is
worse than the Node route it was beating. The individual `tree-sitter-<lang>` wheels bundle their
grammar in the wheel: measured at **9.4 MB for runtime + 5 languages**, parsing correctly with the
cache untouched. A supported language is then a line in the dependency list, which is exactly the
honesty property 2d wants.

| | **Python: `tree-sitter` + `tree-sitter-<lang>` wheels** | Node: `web-tree-sitter` + `.wasm` |
| --- | --- | --- |
| Install size | **9.4 MB** for 5 languages, grammar bundled per wheel | 56 MB (4.7 runtime + 51.7 grammars) |
| Network at first run | **none** — grammars ship in the wheel | none |
| Of our 18 | **18 — Groovy included** | 17 — no Groovy |
| Integration | an `import` | subprocess + JSON bridge |
| Version pinning | one package | runtime/grammar ABI pair; the prebuilt set is built with `tree-sitter-cli 0.20.8` and **fails to load** under `web-tree-sitter 0.27` |
| Languages in this codebase | **Python only** | Python **and** JavaScript |
| Compiler needed to install | **no** — `pip install --only-binary :all:` succeeds | no |

This is the better promise to break. The skill is a Python tool: asking a Python user for one
`pip install` is ordinary, while asking them to install Node to analyse their Python is not. It
also deletes a whole layer — `js_bridge.py`, `js_extract.js`, the subprocess, the JSON marshalling
and the "did Node run?" error paths all go, rather than being replaced by equivalents.

**Node leaves the runtime entirely and stays only as the installer.** Two `package.json` files
exist and they have nothing to do with each other:

| File | Job | Fate |
| --- | --- | --- |
| root `package.json` + `bin/cli.js` | the `npx` installer | **stays** |
| `.agents/skills/code-archaeologist/package.json` + lock | declares `@babel/parser`, nothing else — its own description says "the Python pipeline needs none of this" | **deleted**, with `node_modules/` and the skill's `.gitignore` entry |

So `npx github:...` still installs the skill; the skill itself never shells out to Node again.
`bin/cli.js --self-test` stays and gets simpler: no `npm install` step, no degraded-backend path.

#### Install into the skill directory, not the user's Python — decided 2026-09-10

**Step 1 shipped this wrong and it is step 1b's job to fix.** It told the agent to
`pip install tree-sitter …`, which mutates the environment the user runs everything else in. The
skill already had the right pattern sitting next to it: `@babel/parser` installs into
`<skill>/node_modules`, git-ignored, and deleting the skill folder removes every trace of it.
Python packages can do exactly the same thing:

```bash
pip install --only-binary :all: --no-cache-dir --target <skill>/vendor tree-sitter tree-sitter-java
```

then `paths.py` puts `<skill>/vendor` on `sys.path` ahead of site-packages, and `grammars.py`
imports as it already does.

**Verified, not assumed (2026-09-10):** installed into a scratch `--target` directory, confirmed
`tree_sitter.__file__` resolves inside it, and parsed a real sample file with `has_error: False`.
**0.7 MB** for the runtime plus one grammar. Re-verified for containment the same day: `pip list`
returned **117 packages before and 117 after**, and the target directory held exactly
`tree_sitter/`, `tree_sitter_go/` and their two `dist-info` directories. Nothing entered the user's
environment.

**`--no-cache-dir` is part of the command, not an optimisation.** Without it pip writes the
downloaded wheels to its own HTTP cache (`%LOCALAPPDATA%\pip\cache` on this machine, `~/.cache/pip`
elsewhere) — outside the skill folder, and therefore not removed when the skill folder is deleted.
That cache is pip's own and harms nothing, but it is the difference between "leaves nothing behind"
being true and being nearly true, and the whole point of installing into the skill is that the
claim is exact. The cost is re-downloading 0.7 MB on a reinstall. Take it.

Why this is the better shape:

| | `pip install` (step 1, wrong) | `--target <skill>/vendor` |
| --- | --- | --- |
| Touches the user's environment | **yes** | no |
| Uninstall | `pip uninstall`, remembered by nobody | delete the skill folder |
| Version conflict with the user's project | possible | **impossible** — separate path |
| Matches how JS/TS already works | no | **yes**, exactly |
| Agent may install without asking | no — it is their environment | **yes**, like `npm install` |

That last row is the practical win: `SKILL.md` currently has to say "ask the user before running
`pip install`", which puts a prompt in the middle of a build. Installing into the skill's own
folder is the skill managing its own dependencies, so the agent can just do it.

**The one real cost, and it is not hypothetical.** The `tree-sitter` runtime wheel is
version-locked to the interpreter (`tree_sitter-0.26.0-cp314-cp314-win_amd64.whl`); the grammar
wheels are `abi3` and portable across Python versions (`cp39-abi3`, `cp310-abi3`) — but **not
across operating systems**, the full tag being `cp39-abi3-win_amd64`. (Corrected 2026-09-10; see
"Node `web-tree-sitter` instead of the Python wheels" under 2e, where it was measured.) So a vendored runtime breaks
if the user switches Python minor versions — the same failure `node_modules` has when the platform
changes, and it needs the same treatment: catch the `ImportError` and print *"vendored tree-sitter
was built for a different Python; re-run the install"*, never a raw traceback.

Requirements for 1b:

- `<skill>/vendor/` added to the skill's `.gitignore`, next to `node_modules/`. It must **never**
  be committed — it is platform- and interpreter-specific binary code.
- `paths.py` prepends it to `sys.path` if it exists, so this is one place, not one per script.
- Prefer vendored over site-packages, but **fall back to site-packages** if no vendor dir exists —
  someone who already ran a plain `pip install` (as step 1 told them to) keeps working.
- `bin/cli.js` should not do the install: the wheels are interpreter-specific and the installer
  does not know which Python will run the skill. `SKILL.md`'s preflight stays the place it happens.
- `grammars.py` reports **which** path a grammar was loaded from, so "why is this version
  different" is answerable.
- **Nothing is written outside `<skill>/vendor`.** This is the requirement the whole step exists
  for, so it is verified rather than assumed: `pip list` before and after must be identical, and
  deleting the skill folder must leave no trace of the install anywhere. That is what
  `--no-cache-dir` is for.

#### Grammars are installed on demand, not all up front

A base install carries `tree-sitter` plus a small core set. When the agent meets a language it has
no grammar for, **`SKILL.md` tells it to install that one wheel** rather than the skill shipping
twenty. The language list becomes a per-repo cost instead of a fixed one, and a repo that is pure
Go never pays for Scala.

Requirements on that instruction, because an agent running `pip install` is a real action on the
user's machine:

- **Name the exact package**, in the same vendored form as the base install
  (`pip install --only-binary :all: --no-cache-dir --target <skill>/vendor tree-sitter-ruby`),
  and say it is one wheel, no compiler. An on-demand grammar must land where the base ones
  did — a wheel that goes to site-packages because the short command was easier to type puts
  the skill back in the user's environment one language at a time.
- **Ask before installing**, or tell the user the command — do not have the agent install silently.
- **Degrade clearly**: a file whose grammar is absent is *skipped with a named warning*, never
  silently dropped. The build still succeeds, exactly as JS/TS skipping does today.
- **Record what was available in the manifest.** This is the determinism problem returning in a new
  costume: the same repo on two machines with different grammars installed yields different graphs.
  `manifest.py` must record the grammar set alongside the source hashes, `check` must report a
  change in it as staleness, and `brief` must say which languages were skipped. A graph that is
  smaller because a wheel was missing must never look like a graph of a smaller codebase.

### 2b. One shared consumer, and where a language still costs work

Every `tree-sitter-<lang>` wheel ships a **`TAGS_QUERY`** — the standard definitions/references
query, the one GitHub uses for code navigation — and the capture names are shared across grammars.
Measured across Java, Python and Go: `definition.class`, `definition.interface`,
`definition.method`, `definition.function`, `reference.call`, `reference.implementation`,
`reference.type`, `name`, `doc`.

So **one consumer reading standard capture names can read every language**, and declarations cost
nothing per language. That is the right architecture and it should be the default path.

**But it does not cover everything, and three gaps are measured, not guessed:**

1. **Receiver resolution is absent.** `reference.call` says "a call named `save` occurs", not
   "it is `OrderArchive.save`". That is the entire edge-building problem and it stays per-language
   semantics — the same conclusion as "tree-sitter equalizes parsing, not resolution".
2. **Coverage is uneven.** TypeScript's shipped `TAGS_QUERY` matches only `function_signature`,
   `method_signature` and `abstract_method_signature` — ambient *declarations*, not
   implementations — so `orders.controller.ts` yields **zero** captures. Any language whose tags
   query is thin needs our own query as a supplement.
3. **Framework routes are not in tags at all.** `@Controller("nest/orders")`,
   `@RequestMapping`, `[Route(...)]` have to be read from the tree directly.

Also note `name` alone is ambiguous: Go's captures include `ResponseWriter`, `"net/http"` and
`byte` because references and definitions share it. Pair every `@name` with the definition or
reference capture it belongs to rather than reading the list flat.

**So the per-language cost is: nothing for declarations where tags is good, plus resolution rules,
plus routes, plus a supplementary query where tags is thin.** Far below the ~250 lines an extractor
costs today, and far above zero. 2d's README rules exist because of exactly this gap. One query set per language answering: what is a class, a method, a function, a
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

Two values, not three: the `textual` tier dies with `lang_extract.py` (2f). Replace the boolean
`approx` with this field, owned by `taxonomy.py`.

#### What the README may and may not claim

**Do not write "supports any language tree-sitter supports."** It is the natural sentence to reach
for and it is an overclaim. A grammar yields a parse tree; a *graph* additionally needs a query
naming which node types are classes, methods and calls, plus receiver-resolution rules. The pack
ships 371 grammars — the skill will support the ones queries were written for.

The honest claim is stronger anyway, because it is specific and checkable:

- **Say** which languages are supported, as a list, and let 2g's fixture runner be what keeps that
  list true. A language with no fixture does not go on it.
- **Say** that adding a language is a query file rather than a hand-written extractor — that is the
  real architectural win, and it is verifiable by anyone who looks at the diff for the last one
  added.
- **Say** the tier split plainly: statically typed languages get real call edges; dynamically typed
  ones get nodes, files, structure and metrics with sparse edges. Burying that would put the README
  at odds with the honest-limitations section, which is the one thing this project has consistently
  refused to do.
- **Never** let the supported-language list and `taxonomy.LANG_BY_EXT` drift. `tools/check_docs.py`
  already enforces that kind of agreement for `kind`/`layer` values; extend it to this list rather
  than trusting prose. It surfaces in
**six** places, all of which must move together: the graph, the vault note's front-matter
(`build_wiki.py`), `context.py`, `report.py`, `brief.py`, and the chip in `templates/viewer.html`.
`TAXONOMY.md` documents the values; `tools/check_docs.py` already enforces that.

### 2e. One engine — decided

**The end state is a single production parser: tree-sitter.** `@babel/parser` and `js_extract.js`
are deleted. `ast` is deleted from the build path and retained *only* as the differential oracle
below. Decided 2026-09-09; the trade accepted is spelled out under "What this costs".

Capability was never the obstacle — the spike parsed `order_service.py` cleanly
(`function_definition`, `class_definition`, `call`, `attribute`, no errors).

#### Node `web-tree-sitter` instead of the Python wheels — asked and rejected 2026-09-10

Asked because 1b's goal is "install into the skill, not the user's machine", and npm has always
done that. Measured both rather than argued about them; **both parse the sample Java file with
`hasError: false` and return exactly `create, findOne`.**

| | Python `tree-sitter` + wheels | Node `web-tree-sitter` (WASM) | Node `tree-sitter` (native) |
| --- | --- | --- | --- |
| Installs inside the skill | **yes** — `pip install --target <skill>/vendor` | yes — `<skill>/node_modules` | yes |
| Compiler needed | no | no | **yes / prebuilds** — fails constraint 1 |
| Footprint, runtime + 1 grammar | **749 KB** | ~780 KB (12 MB installed; the grammar tarball ships its C source too) | n/a |
| Portable across Python versions | **no** — `cp314-cp314-win_amd64` | yes | yes |
| Portable across OS | no — grammars are `cp39-abi3-**win_amd64**` | **yes** — `.wasm` is universal | no |
| Runtimes the skill needs | **one (Python)** | **two, permanently** | two |
| The bridge | deleted at step 4 | **permanent, and carries every language** | permanent |

**Rejected on the last two rows, not on size.** Every script in this skill is Python — all ~20 of
them. Moving the parser to Node does not remove a runtime, it freezes two in place: Python for
every pass, Node for every parse. And `js_bridge.py`, which step 4 exists to delete, would instead
become the path *all* languages take rather than just JS/TS. Worse than the subprocess cost, a
tree cannot be held across that boundary: either the whole CST is serialised to JSON per file, or
the analysis moves into JavaScript, which is the entire skill.

That is the exact opposite of what 2e decided. **The premise does not require it either** —
`pip install --target` already installs into the skill and nowhere else; verified 2026-09-10 by
installing to a scratch directory and confirming `tree_sitter.__file__` resolved inside it
(749 KB, sample parsed clean). Node buys nothing here that Python does not already have.

**What the WASM option really wins is portability, and it is worth being honest about the size of
that.** A `.wasm` grammar never needs reinstalling; the wheels are locked to both the interpreter
minor version *and* the OS. Note this corrects the claim under 1b that the grammar wheels are
"far more portable": `abi3` makes them portable across Python versions only —
`tree_sitter_java-0.23.5-cp39-abi3-win_amd64.whl` is still Windows-x64-only. So the vendor
directory is per-machine on two axes, not one. It is git-ignored either way, and the failure is
loud and fixable with one command, which is what makes the trade acceptable — but "portable" was
the wrong word and is withdrawn.

Reopen this only if the skill's own scripts ever stop being Python. Nothing else changes the
answer.

#### Nothing is deleted before its replacement is proven — and that ordering is structural

This is not caution, it is the only order that works: **the old engine is what verifies the new
one.** `ast` *is* the oracle that proves the Python port correct, and `js_extract.js` is the
reference the JS/TS port gets diffed against. Neither can be removed before the port it validates.
So the sequence is forced:

| Step | Delete | Only after |
| --- | --- | --- |
| 1 | nothing | Java / Go / C# ported and matching phase-1 numbers |
| 2 | `lang_extract.py` | step 1 verified |
| 3 | nothing | JS/TS ported; output diffed against `js_extract.js` — 6 nodes, `OrderCard` + `StatusBadge` as `kind: component`, Nest and Express routes, the suffix-fallback match |
| 4 | `@babel/parser`, `js_extract.js`, `js_bridge.py`, the skill's `package.json` + lock + `node_modules/` | step 3 verified — Node leaves the runtime here |
| 5 | nothing | Python ported; the `ast` oracle reports **0 disagreements** across `sample_src` |
| 6 | `ast` **from the build path only** | step 5 verified — the oracle itself stays forever |

A port that cannot be verified against the thing it replaces does not get to delete it.

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

#### A third option, and the best one: `ast` as a differential oracle

Neither column above is the only shape available. **One production engine, with `ast` retained as
an independent test oracle** gets most of both:

- tree-sitter is the single engine that builds the graph — the "one engine" goal, satisfied, with
  determinism intact because Python has exactly one production parser.
- `ast` never runs at build time. It runs in the test suite, as a **second opinion** on
  tree-sitter's Python: parse the same files both ways, diff the set of module-level defs, classes
  and direct methods, and fail on any disagreement.

This is not a parallel extractor — that would reintroduce the cost the port is meant to remove. It
is one invariant, roughly 40 lines each side, asserting the two parsers agree on *what exists*.

**Proven, not assumed.** A prototype oracle was run against `sample_src/` and **caught a real bug
on its first execution**: `order_routes.py` and `order_controller.py` disagreed, ast=2/ts=0 and
ast=4/ts=2. The cause was a subtly wrong query — a decorated function is wrapped in
`decorated_definition`, so `@app.route` handlers are **not** direct `function_definition` children
and were silently missing. Unwrapping the decorator took the run to 6 files, 0 disagreements.

That failure is exactly the one 2g worries about, and it is worth dwelling on: the port would have
silently dropped every Flask route handler, the build would have succeeded, and the only symptom
would have been a slightly smaller graph. Hand-written fixtures might not have caught it. A free
second parser caught it immediately.

So Python ends up with the **strongest** test of any language, at zero runtime cost — and the other
languages, which have no oracle available, are exactly the ones that need 2g's hand-written
fixtures. The two mechanisms are complementary rather than alternatives.

**The oracle does not rescue the zero-install property**, and that is the accepted cost, not an
oversight — the oracle runs in tests, not at build time.

#### What this costs, accepted knowingly

**The cost changed when 2a chose the Python binding, and it changed for the better.** The old
worry — "Python but no Node builds nothing" — simply stops existing, because nothing at runtime
needs Node any more. What replaces it is smaller and more ordinary: the skill needs
`pip install tree-sitter` plus one `tree-sitter-<lang>` wheel per supported language (no compiler,
grammar bundled, ~9.4 MB for five) where today it needs nothing.

So the promise being broken is **"zero Python dependencies"**, not "works without Node". For a
Python tool that is the right one to give up, and the tool ends up *more* portable than before: one
`pip install` replaces "install Node, then `npm install` in the skill directory".

Because it still reverses a stated promise, step 6 above must land in the same commit as all of:

- **`CLAUDE.md` hard constraint 1** rewritten: from "stdlib only, with Node as the single
  exception" to "two pinned Python packages, and no Node at runtime at all".
- **`SKILL.md:39`** deleted: "If Node itself is missing, do not stop — build anyway" describes a
  situation that no longer exists.
- **README** — the "the Python side has **zero dependencies**" headline, the Requirements table,
  and the "Scanning JS/TS? Run `npm install` first" note, which is simply gone.
- **`metrics.py`** ported to the CST (its 15 `ast.` call sites). This is not extra work created by
  the decision: CST complexity is needed for the other languages regardless.
- **`docs/PRESENTATION.html`** — the requirements/architecture claims.

Two arguments made earlier against this decision are recorded as **withdrawn**, so nobody
re-litigates them from the plan's own text:

- *Determinism* — backwards. The hazard is having two *possible* engines for one language; one
  engine always is strictly more deterministic. Determinism argues **for** consolidation.
- *Metrics* — a wash, per the `metrics.py` bullet above.

### 2f. `lang_extract.py` is deleted, not kept as a fallback

Settled by 2e: with no Python fallback there is no reason to keep a Java one, and keeping it would
mean the same Java file yields different graphs depending on whether Node is installed — a
determinism problem, not merely a duplication one.

It goes at **step 2** of the deletion order, after the tree-sitter Java/Go/C# port matches the
phase-1 numbers. Until then it is the reference the port is checked against, exactly like `ast` and
`js_extract.js` are for their languages.

Note what this simplifies: the `textual` tier in 2d disappears with it, leaving two values
(`exact` / `sparse`) rather than three.

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

Where a language has a free second parser available, prefer the differential oracle in 2e over
hand-written expectations — it caught a real query bug on its first run that a fixture might have
encoded as correct. Python is the only language that gets one; the rest need fixtures precisely
because they do not.

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
- With the two packages uninstalled: the build fails with **one clear, actionable message** naming
  the `pip install`, rather than a traceback or a silently empty graph. This replaces the old
  "no Node, degrade gracefully" path, which no longer exists.
- `bin/cli.js --self-test` still passes, including the offline assertion, and no longer references
  `npm install` or a degraded backend-only build.
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

## Phase 4 — Audit every graph and node feature for silent wrongness

**Phase 3 asks whether everything still runs. This asks whether what it produced is right.** They
are different questions and the second one has never been asked systematically. A command that
exits 0 and writes a graph proves nothing about whether that graph is true.

### Why this is its own phase, and not a spot check

Every bug worth recording in this project so far had the same shape: **the build succeeded.** No
crash, no traceback, no error line. The graph was quietly smaller, or quietly wrong, and the only
symptom was a number nobody was checking.

| Found | Silent failure | How it was caught |
| --- | --- | --- |
| phase 2 | Go's receiver was passed to a helper expecting a declaration -- **every Go method became a free function** | diffing the port against the old extractor |
| phase 2 | C# field types read as `InvoiceStore _store` (type *and* name), so every receiver through a field failed to resolve | same diff |
| phase 2 | `map[string]string` collapsed to a type named `mapstringstring`; the "is it an identifier" guard **passed it**, because stripping brackets is what made it identifier-shaped | same diff |
| phase 2 | the old extractor missed a real `append(...)` call for the graph's whole life | same diff |
| phase 1 | `duplicates.py` did not skip body-less declarations; it was saved only by a token minimum, i.e. by luck | asking the question the roadmap told me to ask |
| phase 1 | `analyze.py`'s orphan guard could not be tested by the sample at all -- the one declaration node in it has a caller | building a fixture the sample cannot produce |
| the spike | `@app.route` handlers are wrapped in `decorated_definition`, so **every Flask route** was missing from the tree-sitter query | the `ast` differential oracle, on its first run |
| earlier | deleting a sibling skill removed the only `@babel/parser`; the flow graph dropped 15 -> 11 nodes and overwrote the committed data | a number contradicting CLAUDE.md |
| earlier | reports embedded absolute machine paths, so the same source produced different bytes elsewhere | reading a committed diff |
| earlier | `brief` reported a confident **false** STALE in the one command an agent is told to trust | two commands disagreeing |

Ten failures, ten silent. Not one was found by running the thing and watching it work. That is the
case for this phase: **the skill's own promise is that an agent can trust the graph instead of
reading the source, and nothing currently checks that the graph deserves it.**

### The method: name the silent failure, then write what catches it

For every node field, every edge kind and every derived feature, answer three questions in this
order. The second is the one that is usually skipped.

1. What does it claim?
2. **What would it look like if it were wrong?** If the answer is "the same, but with a smaller
   number", it needs an assertion, not an eyeball.
3. What assertion fails when that happens?

An assertion that cannot fail is worse than none, because it converts an unknown into a false
assurance. **Every check written here must be shown to fail on a deliberately broken input before
it is trusted** -- the negative test that proved the phase-1 guards were not vacuous is the
pattern, and it is cheap.

### Surface to cover

Enumerable, so there is no "did we get everything". Node fields, from `TAXONOMY.md`: `id`, `layer`,
`kind`, `cls`, `signature`, `signatures`, `doc`, `source`, `end`, `lang`, `ext`, `approx`,
`declaration`, `routes`, `http`. Edge kinds: `references`, `calls`, `http`.

Per-field questions worth stating outright, because each has a plausible silent failure:

- **`source` / `end`** -- do they point at the real declaration? An off-by-one here silently
  mis-attributes every security finding, churn number and clone range that lands on that node.
  Assert by reading the range back out of the file and checking the name occurs in it.
- **`id` uniqueness** -- collisions are last-wins and invisible (open concern 2). Assert no two
  source locations map to one id, and report it as a finding rather than a crash.
- **`routes`** -- a framework whose shape stops matching yields *fewer* routes, never an error.
  Assert the count per framework in the sample, per language.
- **`ext`** -- currently unverifiable by eye. It is the one field whose wrongness has already been
  proven twice (the missing `append`, and the bare-call path).
- **`approx` / `declaration`** -- assert they appear on exactly the nodes that should carry them,
  not merely that they appear somewhere.
- **edges** -- the precision promise ("every edge shown is real") is asserted nowhere. Sample it:
  for a set of edges, confirm the call text actually occurs in the caller's source range.

Derived features, each with its own silent mode: cycle detection (a missed back-edge just reports
zero), orphans, layer violations, hubs, god objects, the health score, per-node metrics, security
attribution, churn/ownership, debt markers, test mapping, clone clusters, BFS paths, blast radius,
`--impact-of-diff`, context packs under budget, and every explorer view that derives from the graph
rather than displaying it.

### `tools/check_graph.py` -- the invariants, as a script

Working principle 5: this must not be a checklist a human re-walks. One script, runnable against
**any** built graph, asserting the structural invariants that do not depend on a particular repo:

- every edge endpoint exists as a node; no dangling references
- no duplicate node ids; `source` unique per id
- `end >= source` line, and the range is inside the file's length
- every `kind` / `layer` / `lang` value is one `taxonomy.py` knows
- `declaration` nodes have no calls; `approx` nodes are only from approximate-tier languages
- `routes` entries have a method and a path; `http` edges join a caller to a routed node
- counts in the report agree with the graph they were computed from

Repo-specific expectations stay in 2g's per-language fixture table. This script is for the
invariants that must hold everywhere, which is what makes it useful on a user's codebase and not
only on `sample_src`.

### Use the techniques that actually worked

Not a new methodology -- the three that have already caught real bugs here, applied deliberately:

- **Differential oracle.** Two independent implementations, diffed. Found the Flask decorator bug
  on its first execution. Python has `ast` for free; JS/TS has `js_extract.js` until step 4 deletes
  it, so **the diff must be captured before then** (see 2e step 3).
- **Equivalence diffing.** Port behind an unchanged contract, then diff the output. Found three
  bugs in step 1 that no test suite existed to catch.
- **Negative testing.** Break the input on purpose, confirm the check fails. The only way to know
  an assertion is load-bearing.

### Fix, do not catalogue

Anything found here is fixed here. A phase that produces a list of known-wrong behaviours and ships
them is worse than not having looked, because the list becomes the excuse. Where a fix is genuinely
out of scope, it goes in the README's *What's next* and the honest-limitations section in the same
commit -- visible to a user, not only to whoever reads this file.

### Verify

- `tools/check_graph.py` passes on both maps of `sample_src`, and **is shown to fail** on a graph
  broken on purpose (a dangling edge, a duplicate id, an out-of-range `end`).
- Every check in it has a recorded negative test. No exceptions -- an unfalsifiable check is a bug.
- The `ast` oracle reports 0 disagreements on `sample_src`, and the JS/TS diff against
  `js_extract.js` is recorded before step 4 deletes the reference.
- Every silent failure in the table above has a regression case, so none of them can return
  unnoticed.
- Every fix is named in the commit message with what it was producing before, and appended to
  `docs/prompt.md`. A silent bug that is fixed silently teaches nobody anything.

---

## Found while implementing

Things noticed while building a step that were **not** obviously fixable — each needs a decision,
so each waits for review rather than being settled mid-flight (working principle 7). Anything that
*was* obviously fixable is not here; it was fixed in the commit that found it.

### 1. A fresh install now parses nothing until grammars are added — found in step 5

**What.** Python used to need nothing installed. Since step 5 it needs `tree-sitter-python` like
any other language, so `bin/cli.js --self-test` on a clean target now builds **12 nodes / 9 edges**
instead of 25 / 22, with two warnings naming the wheels to install. The self-test passes and the
messages are exact -- this is honest degradation, not a bug -- but the demo that exists to show
what the tool does now shows a third of it.

**Why it is not just a fix.** The obvious answer is to have `--self-test` install the grammars
first, and for that path it is defensible: the installer has *already resolved an interpreter* (it
prints `Python 3.14 found`), so the objection recorded in 1b -- "the installer does not know which
Python will run the skill" -- does not hold for `--self-test` specifically. But that reverses a
decision this plan took deliberately, and an installer that silently pip-installs is a bigger
change than it looks.

**Options, in the order I would try them:** (a) `--self-test` installs the grammars with the
interpreter it just found, and says so; (b) it prints one line up front saying the demo will be
partial and gives the command; (c) leave it. Doing nothing is the only one that leaves a new user
looking at a graph that misrepresents the tool.

---

### 2. Report artifacts are not byte-reproducible — found in step 1b

**What.** Constraint 2 says "same source in, same bytes out". The graphs honour it exactly: two
builds of identical source produce byte-identical `graph.json` and `flow_graph.json`. The
**reports do not** — 12 files under `data/report/` differ between runs, entirely because five
scripts stamp `"generated": <now>` (`report.py:287`, `metrics.py:191`, `debt.py:122`,
`duplicates.py:175`, `tests_map.py:84`).

**Why it is not just a bug to delete.** The timestamp is surfaced: `report.py:120` puts it in the
markdown header, and `brief.py:65` reads it back as `reported`. Removing it drops a field a user
can currently see, which is a decision about what the artifacts contain rather than a defect fix.

**Cost of leaving it.** The repo commits `data/` as its worked example, so every rebuild dirties
twelve files with no semantic change — which trains the reader to skim exactly the diffs that
would show a real regression.

**Recommendation: remove the field.** Freshness is already answered properly and by something
better: `check` compares source hashes through `manifest.py` and returns `stale: true/false`, which
is what `brief` should cite. A wall-clock stamp is a weaker duplicate of that, and it is the only
thing standing between the reports and a constraint the rest of the pipeline already meets.
Alternative if the stamp is wanted: keep it out of the committed artifacts and print it at the
console instead.

---

## Open concerns — review these before implementing

Collected while planning, none of them blocking, all of them things that will bite if nobody
decides them deliberately. Ordered by how much damage they do if ignored.

**1. Resolution parity is unproven.** The spikes proved *declaration* parity for Python (oracle:
6 files, 0 disagreements) and the presence of every node type the routes need. They did **not**
prove *resolution*: `build_flow.py` uses `ast` at 41 call sites for `__init__` type hints,
assignments, typed params and locals. That is the bulk of what `ast` actually does here. Standard
CST work, but nobody has demonstrated it, and step 5 of the deletion order is where it has to hold.
Spike it before starting 2c, not after.

**2. Node id collisions get worse with every language.** `CLAUDE.md` already records that two
classes sharing a name across languages collide in `build_flow.py` — last wins — and that the
sample dodges it by naming the polyglot services for different slices of the domain. At six
languages that is a documented wart. At twenty it is a bug: `Client`, `Config`, `Handler`, `User`
and `Server` will collide constantly in any real polyglot repo. Decide the id scheme (language
prefix? file-relative?) **before** porting, because node ids are the join key for metrics, security
findings, churn, notes, the vault and the explorer, and changing them later means regenerating
every artifact.

**3. `metrics.py` needs a per-language branch table.** Cyclomatic complexity counts branch nodes.
On `ast` that is a fixed set of typed nodes; on a CST it is a per-grammar list of node type names
(`if_statement`, `while_statement`, `case_clause`, `catch_clause`, …), and they differ per language.
So "port `metrics.py` to the CST" is not one job — it is one small table per language, and a
language with no table silently reports complexity 1 for everything. Guard it in 2g's fixtures.

**4. Byte offsets, not character offsets.** tree-sitter operates on bytes and returns byte ranges;
the current extractors read text with `errors="replace"` and count characters. Any file with
non-ASCII content will shift line/column numbers unless the conversion is deliberate. Every
artifact keyed by `source: file:line` — the vault, security findings, churn, duplicates — depends
on that number being right. Add a non-ASCII file to 2g's fixtures.

**5. Grammar versions drift independently.** Each `tree-sitter-<lang>` wheel is versioned on its
own, and a grammar release can rename node types. A query written against the old names then
matches nothing, silently, and the language quietly reports zero nodes. Pin every grammar version
exactly, and let 2g's fixture runner be the thing that catches a bad upgrade — that is its main
long-term job, more than proving the initial port.

**6. The explorer needs colours and taxonomy entries for eleven new languages.** `LANG_COLORS` in
`viewer.html` and the language table in `README.md` both enumerate languages. The colour rules in
`CLAUDE.md` require a distinguishable colour per value, added in the same commit as the value —
and eleven more is enough that "pick something distinguishable on a dark background" stops being
easy. Consider whether the legend should group rather than list.

**7. Performance is unmeasured.** Twenty grammars over a large repo, all in-process now. Probably
fine — tree-sitter is fast and the subprocess overhead disappears — but nobody has timed it, and
the skill's value proposition is that it is cheaper than reading the source. Measure once on a real
repo before claiming anything.

**8. JSX/`component` detection is bespoke logic that must survive the port.** The `kind: component`
/ `layer: ui` classification is "a function that returns JSX", currently done on Babel's AST. The
spike proved the CST exposes `jsx_element`, but the *classification rule* is ours and has to be
re-implemented, not just re-queried. It is exercised by `OrderCard` and `StatusBadge`.

## Cross-cutting rules (from CLAUDE.md, applied every phase)

- **Pinned Python dependencies, and no Node at runtime** (was: stdlib only with Node as the single
  exception). `tree-sitter` plus one `tree-sitter-<lang>` wheel per supported language — grammars
  bundled, no compiler, no download at first run. Nothing else may be added without the same
  scrutiny these got, and `tree-sitter-language-pack` is rejected on record because it fetches
  grammars over the network at first use.
- **Deterministic.** Same source in, same bytes out. Verified by building twice and diffing `data/`.
- **ASCII `print()` output** (cp874 console); `console.safe_stdout()` before echoing repo text.
- **Docs in the same commit.** Mirror-truth files (`CLAUDE.md`, `SKILL.md`, `README.md`,
  `docs/USAGE.md`, `templates/TAXONOMY.md`, `docs/PRESENTATION.html`) rewritten to match new
  behavior; append-only files (`docs/PROJECT_HISTORY.md`, `docs/prompt.md`) extended, never revised.
- **Regenerate committed sample data in the same commit** whenever `sample_src/` or the graphs change.
- **Append to `prompt.md` at the end of every turn** (working principle 8), **before committing** —
  the entry rides in the same commit as the work it describes.
- **Update this file's status ledger in the same commit as the work.** The block at the top is the
  only place that says what is done and what is not; a step finished without moving its row is a
  step nobody can see is finished, and a row marked done without the code is worse — it is a lie
  that the next session will act on. Both have already happened here: `e37f8fb` reads "Install the
  wheels into the skill" and changed no code (it scheduled 1b, it did not build it), and phase 4
  was written into this file with the header above it still announcing three phases. So, every
  commit that advances a step: move the row, and move anything it pulled in out of the "not done"
  list. **A step is done when its row says so, not when the code lands.** The *state* moves in the
  work commit; the **hash cannot** — a commit cannot contain its own id — so the row says "this
  commit" and the id is filled in by the next one. That is the only part that may lag, and it lags
  by design rather than by neglect.
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
