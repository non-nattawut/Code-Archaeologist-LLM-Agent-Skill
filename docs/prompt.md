# prompt.md — running transcript

Every exchange in this repo, appended one turn at a time. See CLAUDE.md working principle 7.

> **Note on entries 1–20.** They were written *at the end* of the session, from the conversation
> still in context — not contemporaneously. They are faithful in substance, decisions and outcomes,
> but the assistant responses are condensed rather than verbatim. Entry 21 onward is written at the
> end of each turn, as the rule intends.

---

## [1] 2026-09-08 — Session resumed with no memory

**Prompt**
> continue where you left off due to token limit

**Response**
Checked for a memory file at the session memory path — none existed. Checked `git status`: working
tree clean, no stashes, HEAD at `c4e802e`. With no memory file, no in-progress work and a clean
tree, there was nothing to infer.

Said so plainly rather than guessing, and asked what we had been working on. **Claude retains
nothing between sessions**, so a session that opens with "continue" has no continuity unless the
repo itself carries the state.

---

## [2] 2026-09-08 — Same prompt repeated

**Prompt**
> continue where you left off due to token limit

**Response**
Re-checked; the answer was unchanged. Restated that there was no memory or in-progress state to
resume from, and asked for a one-line description of the task.

---

## [3] 2026-09-08 — Make `npx code-archaeologist-skill` work

**Prompt**
> I want you to make this project register to node that user can npx code-archaeologist-skill

**Response**
Read `package.json` and `bin/cli.js`. Found the actual bug: the package is named
`code-archaeologist-skill` but `bin` only mapped **`code-archaeologist`**. `npx <pkg>` looks for a
bin matching the package name, so the documented command was not reliably resolvable.

- Added `"code-archaeologist-skill": "bin/cli.js"` as the first bin entry, keeping the shorter
  alias.
- `npm view code-archaeologist-skill` → **E404**: never published.
- `npm whoami` → **ENEEDAUTH**: not logged in.

Explained the three steps (`npm login`, `npm publish --access public`, test) and deliberately did
**not** run `npm publish` — publishing is public and effectively irreversible, so it needed explicit
authorisation.

---

## [4] 2026-09-08 — How to publish an update

**Prompt**
> so if npm publish --access public how do I update my package? just use npm publish --access public again?

**Response**
Explained that npm rejects republishing the same version, so the version must be bumped first:
`npm version patch|minor|major` (which also creates a commit and tag), then publish. Noted
`--access public` is only strictly required on a scoped package's first publish; harmless otherwise.

---

## [5] 2026-09-08 — Adding another author

**Prompt**
> how to add another author

**Response**
Explained the `contributors` array alongside `author`, with both formats. Noted these fields are
metadata only — publishing rights belong to the npm account that runs `npm publish`, not to
anything in `package.json`.

---

## [6] 2026-09-08 — Add a contributor

**Prompt**
> Peerapon
> Chanthachaem
>
> add this one to contributor without email

**Response**
Added `"contributors": ["Peerapon Chanthachaem"]` to `package.json`, name only as asked.

---

## [7] 2026-09-08 — npm 403, 2FA required

**Prompt**
> npm error code E403 … Two-factor authentication or granular access token with bypass 2fa enabled is required to publish packages.

**Response**
Explained the two routes: a one-off `--otp=<code>` from an authenticator app, or an Automation
Token that bypasses 2FA by design and is the better choice for repeat publishing.

---

## [8] 2026-09-08 — Where the OTP comes from

**Prompt**
> how do I get my OTP? its dont send me to email

**Response**
Clarified that npm 2FA uses an **authenticator app, not email** — so no message was ever coming.
Pointed at the account's 2FA settings and noted the Automation Token path avoids the OTP entirely.

---

## [9] 2026-09-08 — Avoiding npm altogether

**Prompt**
> ok I think this is annoying any way to provide user install without npm?

**Response**
Yes — `npx` installs straight from a GitHub repo. Proposed
`npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill`: no npm account, no 2FA, no publish,
and tag-pinnable. Gave the trade-off honestly (longer command, not searchable on npmjs.com) and
noted publishing later remains possible.

---

## [10] 2026-09-08 — Switch install docs to GitHub

**Prompt**
> ok so do it with github that user install from it

**Response**
Updated the install command in three places: the README Installation section, the `bin/cli.js`
JSDoc examples, and the CLI's `HELP` usage line. All flags unchanged — only the invocation.

---

## [11] 2026-09-08 — Feature recommendations

**Prompt**
> reccommend feature that you think good this skill should have *(asked three times)*

**Response**
Read the skill's scripts and `SKILL.md` first so the suggestions were grounded rather than generic,
then recommended three that fit the project's constraints (deterministic, stdlib-only, token-cheap):

1. **Staleness guard** — every answer silently depended on the graph being fresh, and nothing
   enforced it. The most important of the three, because it protects the correctness of everything
   else.
2. **Git-diff blast radius** — makes it a PR-review tool, reusing the existing reverse traversal.
3. **Architectural smell detection** — cycles, orphans, layer violations; nearly free on an
   explicit graph.

Recommended shipping the staleness guard first.

---

## [12] 2026-09-08 — Build all three + restructure the directories

**Prompt**
> ok do all of it but please make our skill more better directory stucture too, for now it messy

**Response**
Investigated before moving anything, and found two hard constraints:

- **`scripts/` must stay flat.** Every script computes `SKILL_ROOT = dirname(SCRIPT_DIR)` and
  imports siblings via `sys.path.insert`. Moving them breaks all cross-imports and ~40 documented
  paths for no real gain.
- **`data/` was the actual mess** — two maps plus caches dumped flat together.

Asked which `data/` layout to adopt (the doc blast radius was large). The question went unanswered,
so I proceeded with the recommended "group by map" option and said so.

Delivered:
- `data/` → `structure/`, `flow/`, `cache/`; path constants updated in all 7 scripts, `cli.js`,
  `.gitignore`, `.npmignore` and every doc.
- **`manifest.py`** — SHA-1 content snapshot + `archaeologist.py check`.
- **`trace_path.py --impact-of-diff`** — git diff → nodes → unioned impact.
- **`analyze.py`** — Tarjan SCC cycles, orphans, layer violations.

Verification caught **two false positives** I then fixed: cross-stack `http` edges were flagged as
layer violations (a frontend client calling a backend controller is the *correct* direction), and
`__init__` was reported as an orphan. Full pipeline, traces and installer self-test all passed.

---

## [13] 2026-09-08 — Commit and push

**Prompt**
> commit & push

**Response**
Confirmed branch (`main`), last commit and remote. Turn ended before committing.

---

## [14] 2026-09-08 — README, then commit and push

**Prompt**
> update README then commit & push

**Response**
Found the real gap: the Features list mentioned the new capabilities but the **Usage** section had
no runnable examples for them. Added `check`, `--impact-of-diff` and `analyze.py` blocks.

Unstaged `.idea/claudeCodeTabState.xml` (IDE state) to keep the commit focused.

**Miss:** used PowerShell here-string syntax (`@'…'@`) in the *Bash* tool, which leaked a literal
`@` into the commit subject. Caught it in the output, amended with a proper heredoc before pushing.
Pushed `c4e802e..f5828d7`.

---

## [15] 2026-09-08 — Write the project history; do you have old memory?

**Prompt**
> create 1 .md file that how I create this project until this time from start, do you have old session memory? since I saw that this session are not continue from the start

**Response**
Answered the memory question directly: **no.** The memory directory was empty at session start,
which is why turn 1 had to ask what we were doing.

The git log confirmed the user's suspicion concretely: **44 commits**, and this session had
contributed exactly **one** (`f5828d7`, 09-04), with **30 later commits** from sessions I had no
record of.

Built `PROJECT_HISTORY.md` from the git log rather than recollection — commit bodies in this repo
record reasoning and verification, making them a far better source. Added a provenance note so a
reader knows what it is based on. Verified its claims (22 scripts, `code-wiki` untracked).

---

## [16] 2026-09-08 — Fetch latest

**Prompt**
> fetech git to make sure that you pull the latest

**Response**
`git fetch origin`. Local and remote both at `3bc603b`, 0 ahead / 0 behind — already current, so
the history doc was built on the latest state. Listed the three untracked items.

---

## [17] 2026-09-08 — Delete the stale code-wiki folder

**Prompt**
> ok so now we have code-achaeoligist skill that newer/ latest skill right then can we delete the old stale code-wiki

**Response**
Verified before deleting: `code-wiki` held **zero source** — 8 `.pyc` caches (all corresponding
`.py` present in the live skill), one gitignored `manifest.json`, and `node_modules`. Untracked by
git, referenced by nothing. Deleted it.

**Then it bit me.** A verification rebuild produced **11 flow nodes instead of 15** — that
`node_modules` had held the machine's only copy of `@babel/parser`, so JS/TS parsing silently
degraded and the demo data got overwritten with a backend-only graph. Caught it only because the
numbers contradicted CLAUDE.md. Ran `npm install` in the live skill, rebuilt, restored 15/11.

Also discovered committed reports embedded **absolute machine paths**
(`F:\Work\Programming\…` — a different machine), breaking the determinism constraint. Reverted the
reports rather than commit this machine's paths, and flagged both issues.

---

## [18] 2026-09-08 — Fix both issues; audit the skill name

**Prompt**
> ok fix those 2 then we can delete old one right?
>
> recheck for make your integrated skill name is correct

**Response**
Clarified that `code-wiki` was already deleted the previous turn.

**Fix 1 — determinism.** `metrics.py`, `debt.py`, `tests_map.py` all wrote
`os.path.abspath(r)`. Added `rel_roots()` to `manifest.py` (which already owns portable path
handling and documents "no absolute paths") and pointed all three at it. Roots now store as
`"sample_src"`. Verified `brief.py` still resolves freshness.

**Fix 2 — silent degradation.** The real hazard was that a degraded build *looked successful*.
The counts line now carries `(BACKEND ONLY - frontend skipped)` plus a WARNING block. Tested both
paths.

**Name audit:** clean — 0 `code-wiki` references in tracked files, correct SKILL.md frontmatter, all
5 harness dirs, both package names, and the installer self-test installs as `code-archaeologist`.

---

## [19] 2026-09-08 — Separate commits, then push

**Prompt**
> separate commit and push the different jobs

**Response**
Three commits, one job each: `dcf60f5` (portable roots + regenerated reports), `2507cb3` (degraded
build warning), `b2894a5` (`PROJECT_HISTORY.md`). Pushed `3bc603b..b2894a5`.

Noted the `code-wiki` deletion produced **no commit** — it was untracked, so git had nothing to
record; it lives in `PROJECT_HISTORY.md` instead.

---

## [20] 2026-09-08 — Rewrite README; build a presentation page

**Prompt**
> after finish rewrite README.md make it easier to understand/read
>
> also create the .html that summary all features of this project to let me can present to audience correctly, that html will show all feature and if I click that it will tell how it works what technique it use to do it, add all things that I need to understand to answer audience question correctly

**Response**
**README:** the problem was a 25-bullet wall with no hierarchy. Moved Quick start to position 3,
converted the bullet list into three scannable question→command tables (Navigate / Review / Trust),
put a concrete trace example in the first ten lines, added an architecture diagram and a
language-support table. 282 → 261 lines, far more navigable.

**PRESENTATION.html:** self-contained, 43.5 KB, no external requests. 25 features in 5 categories;
each card opens a panel with *how it works*, *named technique*, *command*, and anticipated audience
questions — **53 in total** — plus a 7-item honest limitations section (heuristic call resolution,
name-based coverage, regex-not-dataflow scanning, Python-only per-node metrics).

Invoked the dataviz skill since the page uses stat tiles, and ran its palette validator against the
project's layer colours. **It failed CVD separation:** test green `#57ab5a` vs ui orange `#f0883e`
is ΔE 3.6 for protanopia, well under the floor. Reported it as a real accessibility finding rather
than silently working around it, and made sure the presentation never encodes identity by colour
alone.

Verified: JS parses as a classic script, tags balanced, dialog has `role`/`aria-modal`. Stated
plainly that I **could not visually render** the page in this environment.

---

## [21] 2026-09-08 — Start logging every exchange

**Prompt**
> edit CLAUDE.md from now on save prompt input and your output append to prompt.md
>
> initially save this session all input/output in that file

**Response**
Added **working principle 7** to CLAUDE.md: append every turn to `prompt.md`, with an entry format
and four rules — append never rewrite, write contemporaneously, record reasoning and misses (git
already stores the diff), number sequentially. Placed it as a working principle so it is read as a
standing behaviour, and exempted it from principle 6's doc-sync requirement since it is a log.

Created this file and backfilled entries 1–21. Flagged in the header that 1–20 are **reconstructed
at end-of-session**, not contemporaneous — the substance and outcomes are accurate but the
assistant text is condensed. Included the misses (the `@` in the commit subject, the deleted
`@babel/parser`) because those are the parts git cannot show.

---

## [22] 2026-09-08 — Remove ROADMAP.md and assess USAGE.md

**Prompt**
> roadmap.md can be deleted right?
>
> and I think uasge.md has same data as skill.md since skill.md need to tell Agent how to use this skill right? if yes remove it

**Response**
Checked both before deleting anything:

**ROADMAP.md:** Safe to remove. All 5 near-term goals and 3 of 4 backlog items had shipped;
`PROJECT_HISTORY.md` now covers finished work. One backlog item was still live (duplicate-code
clusters via normalized token hashing) — moved it into `README.md`'s Roadmap section before
deleting the file via `git rm`. Documented the removal in `PROJECT_HISTORY.md`.

**USAGE.md:** Pushed back against deletion. While 79% of command forms overlap with `SKILL.md`,
they target different audiences and deleting it has real costs:
1. `SKILL.md` is for the agent (loaded into LLM context every session, kept minimal); `USAGE.md` is
   for human operators running commands manually.
2. `README.md` links directly to it for the full command reference.
3. `package.json` ships `USAGE.md` to users in `files[]`.
4. `USAGE.md` contains a 66-line worked example with real outputs (33% of the file).
5. Deleting it would require either losing reference material or bloating `SKILL.md` again.
Recommended keeping it intact (or trimming only duplicate command forms if desired).

---

## [23] 2026-09-08 — Continue Claude job within prompt scope

**Prompt**
> continue claude job, dont do out of scope just my prompt scope

**Response**
Kept strictly within prompt scope:
- Left `USAGE.md` intact as recommended (no unnecessary trimming or deletion).
- Maintained determinism and doc-sync across `README.md`, `PROJECT_HISTORY.md`, `CLAUDE.md`, and
  `prompt.md`.
- Appended turns 22 and 23 to `prompt.md` in accordance with working principle 7.
- Separately committed the completed jobs to git:
  1. README rewrite (`README.md`)
  2. Presentation page (`PRESENTATION.html`)
  3. Obsolete ROADMAP removal and history update (`ROADMAP.md`, `PROJECT_HISTORY.md`)
  4. Logging setup (`CLAUDE.md`, `prompt.md`)


## [24] 2026-09-08 — Phase 0: categorize scripts/, and make the docs-sync rule checkable

**Prompt**
> git pull then plan to implement all the roadmap in README.md phase by phase after finish all update README.md

(then, across the same arc)

> 1. also now script is plain in the future it will bloat so categorize it
> 2. edit CLAUDE.md that it should always sync it self to the project
> 3. PRESENTATION.html, README.md, PROJECT_HISTORY.md, USAGE.md, PROMPT.md should always sync too

> after finish each phase test and fix until polished then commit and push
>
> then I will prompt you to continue since you might hit limit due to many features add

**Response**

Planned all four README roadmap items as one phase each, preceded by a Phase 0 of the housekeeping
above — done first deliberately, because all five feature phases add scripts and change documented
commands, and doing the reorganization afterwards means touching every doc twice.

Decisions the user made during planning, after asking for explanations rather than accepting a
proposal: frontend structure entities mirror Python's rule **plus React components**; the offline
viewer **vendors** force-graph rather than being skipped; graphs extend to **Java + Go + C#, both
maps**.

The Java/Go/C# question was the interesting one. The user asked why the dozen-language passes
(lines, complexity, risk, debt, tests) work everywhere but graphs do not. The honest answer is that
those passes are *local, independent, per-line observations* — an error is contained and visible —
whereas a graph is *relational*, and its errors compound through BFS, blast radius, cycle detection
and the A–F grade, where a 90%-accurate graph looks exactly like a correct one. Splitting that into
two separable bets (structure graphs ~95%, read from declarations; flow graphs ~85%) is what made
the decision possible.

This turn implemented Phase 0.

**0a — script layout.** `git mv`'d 21 scripts into `core/` (taxonomy, manifest, console),
`extract/` (build_wiki, build_graph, build_flow, js_bridge, js_extract.js, apply_descriptions),
`review/` (analyze, scan_security, git_insights, metrics, debt, tests_map, report, brief) and
`query/` (trace_path, context, search, build_html). `archaeologist.py` stays at the scripts root
because it is the only entrypoint.

The move breaks every file's path preamble, which was `SKILL_ROOT = os.path.dirname(SCRIPT_DIR)` —
one `dirname` too few once a file sits a level deeper. New `scripts/paths.py` owns the layout once,
and putting `scripts/` plus all four category dirs on `sys.path` as an import side effect is what
keeps all ~35 existing bare sibling imports (`import taxonomy`) working untouched. Preambles went
from four lines to two.

Two special cases: `extract/js_bridge.py` keeps a `SCRIPT_DIR` of its own (it needs the directory
holding `js_extract.js` for `cwd=`, not the skill root) and its `SKILL_DIR` became `SKILL_ROOT`
from `paths`; `archaeologist.py` needs one `dirname`, not two. `build_html.py` turned out not to
import `sys` at all — the bootstrap needed it added.

**Verification.** The reproducibility baseline was captured *before* the move: full pipeline on
`sample_src`, `git status` on `data/` clean. After the move, the only diff in `data/` was
`"generated"` timestamps — confirmed by diffing with timestamp lines filtered out — so this is a
pure refactor and `data/` was reverted rather than committed. Numbers still match CLAUDE.md:
structure 6/9 grade C (75), flow 15/11 grade D (68), 3 endpoints, 0 pending, `check` → stale false.
`compileall` clean; `trace_path`, `debt`, `search` and `context` all still run standalone from
`C:\Users\User` (constraint 3); `node bin/cli.js --self-test` passes with no `cli.js` change,
because `copyDir` was already recursive.

**0b — the docs-sync rule.** Rewrote CLAUDE.md principle 6 around the distinction that actually
matters: **mirror-truth** files (CLAUDE.md, SKILL.md, README.md, USAGE.md, TAXONOMY.md,
PRESENTATION.html) get rewritten to match today's behavior, while **append-only** records
(PROJECT_HISTORY.md, prompt.md) are extended and never revised — "syncing" the latter by rewriting
would destroy the only reason they exist. Added the self-referential clause: CLAUDE.md is not
exempt from its own rule. Also added a "Where the scripts live" section documenting the new layout,
the one-way dependency direction, and the two-line preamble.

**0c — the check.** A rule with no check is a wish, which is exactly how CLAUDE.md's pipeline
diagram silently lost `brief`. New `tools/check_docs.py` verifies three mechanical facts only:
every script is listed in README.md's tree and named in CLAUDE.md; every `scripts/...` path quoted
in any doc exists; every `kind`/`layer` value in `taxonomy.py` appears in TAXONOMY.md. It sits in
`tools/`, not in the skill's `scripts/` — a deliberate deviation from the plan, because it reads
repo files that are not part of an installed skill and would error out immediately in a user's
install.

It found real drift on its first run: `console.py`, `js_bridge.py` and `paths.py` were mentioned
nowhere in CLAUDE.md. Fixed, along with the missing `brief` in the pipeline diagram.

**Doc paths.** 20 references in USAGE.md, 27 in SKILL.md and one each in PRESENTATION.html and
TAXONOMY.md rewritten to the categorized form, and README's structure tree redrawn around the four
categories.

## [25] 2026-09-08 — Phase 1: frontend entities in the structure map

**Prompt**
> continue phase 1

**Response**

Roadmap item 1. `build_flow.py` already read `.ts/.js` through `js_bridge`; `build_wiki.py` globbed
`*.py` only and never imported the bridge, so `sample_src/frontend/*.ts` existed in the flow map and
was invisible in the structure map. Fixed by making `build_wiki.py` stop being "the Python scanner":
`extract_entities` is now an orchestrator over `extract_py_entities` + `extract_js_entities`, both
returning the same entity dict, and the renderer below them never learns which producer ran. That is
the seam Phase 3's Java/Go/C# extractor plugs into.

**`js_extract.js`** gained `endLine` on every class, method and function (cheap here, and the piece
Phase 5 and `metrics.py` both need) and a `collectJsx` pass emitting `jsx: true` plus the
capitalized JSX tag names a function renders.

**React components.** A function that returns JSX becomes its own entity with `kind: component` and
`layer: ui` — `taxonomy.KINDS` has allowed `component` since the beginning and nothing had ever
assigned it. Detection is by the `jsx` flag, not the file extension: a `.ts` file cannot contain JSX
(the parser gets no jsx plugin), so there is nothing to gain from restricting it to `.jsx`/`.tsx`
and a plain `.js` React file is common. The same flag now types the flow map's nodes too — one
meaning, one kind, whichever map you are reading.

**Import resolution.** Python can only match import *names* against entity names; a JS specifier
names a *file*, which is better information, so `./api_client` is resolved back to a path (fixed
extension order, so it is deterministic) and becomes an edge to whatever that file defines.

**The correction worth recording.** The first version attributed the whole file's imports to every
entity in it, mirroring what the Python side does. Rebuilding showed the cost immediately:
`StatusBadge`, which renders a `<span>` and calls nothing, got an edge to `ApiClientModule` because
its *sibling* component used `getOrder`. So each JS entity now carries the set of names it actually
calls or renders, and an import attaches only to the entities that use it. `StatusBadge` came back
with no references, `OrderCard` with exactly two. Python's file-level rule was left alone — changing
it is not this phase's business and would have broken the byte-identical baseline.

**Orphans.** The new frontend roots dropped the sample from C(75) to D(65), because nothing in the
graph renders a top-level component. But nothing in the graph calls a route handler either, and
`analyze.py` has always exempted `kind: endpoint` for exactly that reason: the caller is outside the
graph, so a missing incoming edge says nothing. Added `component` to that same exemption — narrow on
purpose. Widening it to `layer: ui` would also have exempted `OrderPageModule`, and an unused
exported helper in a page module *is* dead code. Flow-map dead nodes came back to 2, the same count
as before this phase, which is the check that the exemption was narrow enough.

**Verification.** structure 6 nodes/9 edges -> **10/12**, grade C (70); flow 15/11 -> **17/12**,
3 endpoints, 0 pending, grade D (69). `langs` in the structure census reports js 4 / py 6, where it
previously reported everything as Python — `report.py` was already asking for `lang` and
`build_graph.py` was dropping it. Built twice, `data/` differs only in `generated` timestamps.
Cross-stack trace still runs `submitOrder → createOrder → OrderController.create_order →
OrderService.place_order → OrderRepository.save`. With `node_modules` renamed away the build still
succeeds and falls back to exactly the old 6/9 — and `build_wiki.py` now prints the same
`(BACKEND ONLY - frontend skipped)` banner the flow map has always printed, because a structure map
silently missing its frontend looks complete.

Opened the built explorer in a browser: all seven views paint, the map switch works, and clicking
`OrderCard` shows `component · ui · js` chips over `sample_src/frontend/OrderCard.tsx · 37 lines`.
No viewer change was needed — colours key off `layer`, and `ui` orange already existed.

**Not done, and worth stating:** the plan's verify list expected an `order_page.test.ts` entity with
`layer: test`. There is none, because that file's top level is `describe(...)`/`it(...)` calls, not
declarations, so the extractor finds nothing to make an entity from. The code path exists and is
exercised on the Python side (`OrderRepositoryTest`, `TestOrdersModule`); the sample just does not
reach it from JS. Also noticed but deliberately left alone: `firstDocLine` attributes a file's
header comment to the first exported symbol, which is why `createOrder`'s summary reads "Thin HTTP
client for the orders backend." Pre-existing, affects both maps, and out of this phase's scope.

## [26] 2026-09-08 — Fix firstDocLine's comment attribution

**Prompt**
> fix it -> I noticed but left alone: firstDocLine
>
> then continue phase 2

**Response**

`js_extract.js`'s `firstDocLine` took the last of a node's `leadingComments` unconditionally. Babel
hands the first statement in a file every comment that precedes it, so a file header became the
summary of whichever symbol happened to be declared first — which is why `createOrder`'s
description read "Thin HTTP client for the orders backend.", a sentence about the file, not about
that function.

Fixed with an adjacency test: a comment documents a node only when it ends on the line directly
above the node starts. A header separated by a blank line, or one sitting above an `import`,
belongs to the file. Verified against all three frontend sample files — `createOrder`, `getOrder`,
`submitOrder` and `loadOrder` now report no docstring, while `StatusBadge` and `OrderCard`, whose
comments really do sit directly above them, keep theirs.

The knock-on was the interesting part: `createOrder` had been living off that borrowed sentence, so
removing it left the node with no description and the build correctly reported **1 pending**. That
is the hybrid description pipeline doing its job — docstring first, cached AI second, nothing
invented. Wrote the summary, ran it through `apply_descriptions.py`, rebuilt: back to **0 pending**,
now 11 docstring / 6 cached-AI rather than 12 / 5.

Grades unchanged (structure C 70, flow D 69) and two consecutive builds differ only in `generated`
timestamps. The `data/` diff against the previous commit also carries new `git_insights` churn for
`OrderCard.tsx` — that file has a commit now, which it did not when the last report was generated.

Used the Edit tool rather than a bash heredoc after the heredoc silently collapsed `\n` to `\n`
inside the replacement string, exactly as CLAUDE.md constraint 5 warns.

## [27] 2026-09-08 — Phase 2: route and framework coverage

**Prompt**
> (same turn) then continue phase 2

**Response**

Roadmap item 2. Before this, `_route_of` only matched `@<obj>.<verb>("path")` on **class methods**,
which is the FastAPI shape and almost nothing else.

**Schema first: `route` -> `routes`.** A single dict could not represent what handlers actually do.
Flask's `methods=["GET", "POST"]` is one handler serving two verbs and the old code kept `elts[0]`
and dropped the rest, so a POST call to a dual-verb handler never linked. Migrated every consumer
in the same commit: `build_flow` (`_route_of`, `_api_edges`, `write_graph`), `analyze.py`'s
entry-point test, `report.py`'s census, `context.py` (which now prints "Routes:" plural when there
is more than one), `viewer.html`, and `TAXONOMY.md`.

**Python.** `_route_of` now returns every verb of every route decorator, accepts bare-name
decorators (`@get("/x")`) alongside attribute ones, handles `add_url_rule`, and — the single
biggest gap — is called in the **module-level function loop**. Flask's normal shape is a decorator
on a plain `def`, so the whole framework was invisible.

**JS/TS.** Enabled babel's `decorators-legacy` everywhere (a file without decorators parses
identically with it on). Added three passes: **Express** reads top-level `<obj>.<verb>("/path",
handler)` registrations only, so a `.get()` inside application logic is never mistaken for a route;
**Nest** joins the `@Controller` prefix to the method's `@Get`/`@Post` suffix, and its class
decorators now feed `infer_layer`, which is better evidence than the class name and file stem a JS
class used to offer; **axios instances** track `const api = axios.create(...)` so `api.get(...)` is
recognised as HTTP, which is how most apps really call an API.

A named Express handler attaches its route to that function's own node. An inline arrow has no node
to attach to, so the registration itself becomes an endpoint node — `GET /orders/:id/status`, with
the route as its signature, because `nid()` reads as nonsense.

**Matching.** Every verb is indexed. When the exact `(METHOD, path)` misses, one documented
fallback: a route whose path is a trailing run of **whole segments** of the call's path, and only
when exactly one route matches. `_norm_path` also learned Flask's `<int:id>` and Nest's `:id?`, and
strips a query string.

**The finding that changed the sample.** First build with Flask and Express added produced **zero**
`http` edges — worse than before. Cause: all three frameworks were serving `POST /orders`, so every
match was ambiguous and the uniqueness rule correctly refused all of them. The rule was right; the
sample was pathological. Real repos do not have three frameworks fighting over one path, so each
sample app now owns a prefix (`/legacy`, `/api`, `/nest`) and the FastAPI controller keeps `/orders`
for the frontend to call. Exercised the fallback deliberately instead: the Express router registers
`/orders/:id/status` the way a real router does — relative to its mount — and `getOrderStatus`
calls `/api/orders/:id/status`.

Tested the guard rails directly rather than committing a pathology: an ambiguous suffix does not
link, a non-boundary suffix (`/myorders` vs `/orders`) does not link, a verb mismatch does not
link, and all five param syntaxes normalize together. Also confirmed a *pre-existing* gap while
there: a hardcoded id (`/orders/7`) never matches `/orders/{id}`, on the exact path as much as the
fallback. Left alone — treating a numeric segment as a param is a guess, and `/orders/2024` could
be a real collection route.

**One taxonomy fix.** `order_routes.py` landed in `layer: unknown` while `order_router.js` landed in
`controller`, because the rule matched `router` but not `routes`. Same thing in two languages, two
different layers. Changed the pattern to `route`, which covers all three spellings.

**Verification.** structure 10 nodes/12 edges -> **13/13**, grade C (71); flow 17/12 -> **25/16**,
**9 endpoints**, 0 pending, grade D (69). Route census lists all four frameworks; `orders` carries
two entries; `orders -> OrderService.place_order -> OrderRepository.save` traces through Flask; the
explorer renders both of a handler's routes on separate lines. Two builds differ only in
timestamps. `check_docs`, `compileall`, `node --check`, `check --src` and the installer self-test
all pass, and the degraded (no `@babel/parser`) build still succeeds with the loud banner.

## [28] 2026-09-08 — Phase 3: Graph extractors for Java, Go and C#

**Prompt**
> continue phase 3
>
> after finish phase 3 dont push yet but move plan file to project and tell in that file current finsih phase is 0 - 3 I will tell you continue phase 4 from different PC

**Response**

Roadmap item 3. Java, Go, and C# are brought into both the structure map and the flow map as a
documented **approximate tier** (`approx: true`), giving polyglot repos real graphs, traces, and
architecture reports without requiring native compilers or external AST tooling.

**Extractor (`lang_extract.py`).** Hand-written declaration extractor (Python stdlib only) emitting
the normalized entity/method shape matching `js_extract.js`:
- Comments (block and line) and string literals blanked with spaces first (preserving line numbers).
- Brace matching identifies class and method body spans across Java, Go, and C#.
- Per-language regexes extract classes/structs, methods, functions, bases/implements,
  decorators/annotations, fields, and typed parameters.
- Call resolution mirrors `build_flow.py`: receivers resolved through field types, parameter
  types, constructor injection, local allocations, or bare same-class/function calls. Unresolvable
  calls are dropped and counted in `ext`, never guessed.
- Framework routes: Spring (`@RequestMapping`, `@GetMapping`, `@PostMapping`), ASP.NET
  (`[Route]`, `[HttpGet]`, `[HttpPost]`), and Go (`mux.HandleFunc`, `http.HandleFunc`, Chi/Gin routers)
  with `ANY` fallback for verb-less registrations.

**Integration.**
- `taxonomy.py`: Added centralized `LANG_BY_EXT` and `lang_of()`, consolidating `metrics.py`.
- `build_wiki.py`: Added `extract_lang_entities()` as the third producer.
- `build_flow.py`: Added `_analyze_lang()` alongside `_analyze_js()`, sharing `_attach_routes()`.
- Approximate tier surfacing: `approx: true` flag set on graph nodes, notes, and front-matter;
  surfaced in `context.py`, `brief.py`, `report.py` (warning in report header and census count), and
  `viewer.html` (`approx` chip).

**Polyglot sample & cross-stack wiring.**
- Added `sample_src/services/orders_java/` (Spring REST controller, service, repository, interface
  implementation), `orders_go/` (HTTP handler, event service, event store), and `orders_cs/` (ASP.NET
  controller, service with overloads, store).
- Added `getOrderEvents` and `loadOrderHistory` in `sample_src/frontend/` connecting frontend calls
  into the Go service.
- Exercised deliberate hard cases: `OrderWorkflow.place` calls interface `PricingRule` with two
  implementations (`FlatRate`, `TieredRate`) remaining unlinked (no false edges); `InvoiceService.Total`
  overloads collapse cleanly.

**Documentation & Plan.**
- Updated `CLAUDE.md` (expected numbers: 25 structure nodes / 22 edges, 50 flow nodes / 31 edges /
  16 endpoints / 0 pending), `README.md`, `SKILL.md`, `USAGE.md`, `TAXONOMY.md`, `PRESENTATION.html`.
- Relocated plan file into the repository at `docs/ROADMAP_PLAN.md` with status table documenting
  Phases 0–3 as completed and Phase 4 as next.
- Rebuilt and verified all sample data in `.agents/skills/code-archaeologist/data/`. All tests
  (`compileall`, `check_docs.py`, `check --src`, installer self-test, viewer script check) pass.

## [29] 2026-09-08 — Push Phase 3 to remote

**Prompt**
> ok commit and push now

**Response**
Pushed Phase 3 to `origin/main`. All tests verified, documentation synced, and roadmap status marked complete through Phase 3.


---

## [30] 2026-09-09 — Phase 4: fully offline viewer

**Prompt**
> git pull and continue phase 4 in /doc/roadmap

*(and, after the first `git pull` was declined and re-issued)*
> git pull

**Response**
Pulled 5 commits from another machine — `scripts/` regrouped into `core/extract/review/query`, new
`paths.py`, `lang_extract.py`, `docs/ROADMAP_PLAN.md`, `tools/check_docs.py`, and a much larger
polyglot sample. HEAD `a11c414` -> `10e0309`.

Phase 4 = vendor `force-graph` so `data/explorer.html` needs no network, removing the last
carve-out in hard constraint 4.

Done as planned:
- Vendored `force-graph@1.43.5` to `templates/vendor/force-graph.min.js` via `npm pack` (not a CDN
  grab — pins the version and brings the LICENSE), MIT text preserved in the file header, plus
  `templates/vendor/README.md` recording source URL, version, licence and the update procedure.
- `viewer.html:230` `<script src=…>` -> `<script>__VENDOR_JS__</script>`.
- `build_html.py`: `VENDOR_JS_PATH`, `load_vendor_js()`, third substitution, docstring corrected.
- `bin/cli.js --self-test`: asserts the built page loads nothing remote.
- Docs: CLAUDE.md constraint 4, SKILL.md notes, README (explorer + requirements + roadmap),
  USAGE.md. `tools/check_docs.py` -> OK.

**The plan's verification was wrong, and I did not follow it.** It specified
`grep -c 'https\?://' data/explorer.html` -> `0`. That is unachievable: SVG/XML namespace URIs
(`http://www.w3.org/2000/svg`) are *identifiers a browser never fetches*, and the vendored licence
header carries an attribution URL — 4 such strings remain. Hitting zero would mean mangling the
library. The real goal is that nothing *loads*, so the assertion checks resource-loading references
(`<script src>`, `<link href>`, `<img src>`, `@import`, `url(http…)`) instead. That returns **none**.
Recorded the departure in the roadmap's header.

Verification worth keeping:
- Vendored bytes are **byte-identical** to what the CDN served (sha256 match after stripping my
  header) — so runtime behaviour is unchanged by construction. This mattered because executing the
  UMD bundle in a Node sandbox kept failing on missing DOM globals; stubbing a fake DOM would have
  proven nothing, whereas byte-equality proves everything.
- Both inline scripts parse as classic scripts (159 KB vendor + 94 KB app); `document.scripts[1]`
  is still the app script, so CLAUDE.md's preview note stays accurate.
- **Negative test**: injected a remote `<link>` into a built page and confirmed the self-test
  detects it. A passing assertion that cannot fail is worthless.
- Installer self-test on a fresh install passes and prints "Explorer is fully offline";
  `templates/vendor/` rides along through `copyDir` with no packaging change, as the plan predicted.
- Sample numbers match CLAUDE.md exactly: structure 25/22, flow 50/31, 16 endpoints, 0 pending,
  both grades **D (69)**, 4 risk findings, 2 test files, 4/46 named, `stale: false`, and all four
  traces (cross-stack, Java, C#, Go) intact.

Size delta: explorer.html **109 KB -> 272 KB (+163 KB)**, entirely the vendored library.

Two things I hit worth remembering: Python here is native Windows, so it cannot read Git Bash `/tmp`
paths — `pwd -W` first. And a `git pull` was declined the first time; re-run when re-issued.

---

## [31] 2026-09-09 — Move the long-form docs into docs/

**Prompt**
> @USAGE.md @prompt.md @PROJECT_HISTORY.md @PRESENTATION.html
>
> move these file to /docs

**Response**
`git mv`'d all four into `docs/`, leaving only `README.md` (repo front page) and `CLAUDE.md` (loaded
by path convention) at the root.

The move itself was trivial; the references were not. Found them before touching anything, because
a blind `git mv` would have broken three things silently:

- **`package.json` `files[]`** listed `USAGE.md`, so the npm package would have shipped without the
  command reference -> `docs/USAGE.md`. Verified with `npm pack --dry-run`: present, 12.1 kB.
- **`tools/check_docs.py` `DOCS`** reads docs by repo-relative path; `USAGE.md` and
  `PRESENTATION.html` would have raised FileNotFoundError on the next docs check.
- **`docs/USAGE.md`'s own outgoing link** to `SKILL.md` was repo-root-relative and needed `../`.
  The `python .agents/skills/...` strings in it are commands run from the repo root, not links, so
  they correctly stay as they are.

Also updated the README pointer and nine references in CLAUDE.md (both doc tables, principle 5's
"copy it into USAGE.md", principle 7's heading and body, and the principle-6 exemption line).

Deliberately left alone: `docs/prompt.md`'s earlier entries and `docs/ROADMAP_PLAN.md`'s phase
bodies still name the old root paths. Both are append-only records of what was true at the time —
CLAUDE.md is explicit that editing them to agree with the present is what makes them worthless.
Confirmed ROADMAP_PLAN contains mentions only, no markdown links, so nothing dangles.

Verified: `check_docs.py` OK, zero broken relative links across README/CLAUDE/USAGE/PROJECT_HISTORY,
no stale references left outside the append-only files, npm package correct, and the pipeline
unchanged (structure 25/22, flow 50/31).

---

## [32] 2026-09-09 — Phase 5: duplicate-code clusters

**Prompt**
> ok continue phase 4 in ROADMAP_PLAN

*(resumed after a token limit with: "continue where you left off due to token limit")*

**Response**
Phase 4 was already done (`7ce1ff2`, previous turn) and the roadmap marked phase 5 next, so I read
"continue" as continue the roadmap, said so, and did phase 5. Also filled in phase 4's empty commit
cell in the status table.

**Departure from the plan, deliberate.** The plan had `duplicates.py` derive source ranges itself
(ast for Python, `endLine` from the extractors for the rest). Checking the import graph first showed
`review/` imports nothing from `extract/` — doing so would have been a new cross-category edge *and*
would have made `report.py` re-spawn the Node extractor on every report. Instead `build_flow.py` now
records `end` on every node: it already had the value at all four construction sites and was
throwing it away (CLAUDE.md even notes the waste). `duplicates.py` then reads ranges from the graph
like every other review pass. 49/50 nodes got an end line; the one without is `GET /go/healthz`, a
synthetic inline-route node with no body — correctly skipped.

`review/duplicates.py`, modelled on `debt.py`'s skeleton: normalize each body to a token shape
(identifiers -> `ID`, literals -> `LIT`, comments and whitespace dropped, keywords and operators
kept), sha1, group, floor at 30 tokens. Wired into `report.py` (import, build call, `data` key,
markdown section, console line), `build_html.report_for()` (cluster summaries only — ids, never
bodies), and `viewer.html` (a Patterns group via the existing `push`/`nodeItem` helpers, plus the
tab badge count; `DUPES` is bound in `loadMap`, not a top-level const, per the front-end rule).

Verified as the plan asked, at two levels. Unit: a pure rename keeps the shape identical, an
operator swap changes it. End-to-end on the sample: renaming a variable inside the planted copy
kept the cluster (1 cluster), changing an operator split it (0 clusters). Also confirmed the
markdown section renders and the cluster reaches the embedded explorer payload for the flow map
only — structure legitimately has 0, since its nodes are classes rather than functions.

**One thing I found and left alone**: a docstring counts as a token, so documenting one copy and not
the other hides the pair. Every rule I tried for stripping leading docs was fragile enough to risk
clustering functions that merely start alike. A false positive costs more than a miss here, so it
stays conservative and the module docstring says so outright.

Planted `createInvoice` in `frontend/api_client.ts` — `createOrder` with every identifier renamed,
the most realistic clone shape there is (a copy-pasted fetch wrapper). It adds one orphan, which
dropped the flow grade D(69) -> D(68); that is the honest consequence, not a regression, and
CLAUDE.md now says so.

Numbers now: structure 25/22 D(69) unchanged; flow **51/31**, 16 endpoints, 0 pending, **D(68)**,
tests **4/47**, 528 lines, **1 duplicate cluster / 4 duplicated lines**, `stale: false`, all traces
intact. Installer self-test passes; on a fresh install duplicates reads 0 because there is no
`node_modules`, so the TS clone is skipped — phase 4's degradation behaviour, working.

---

## [33] 2026-09-09 — Phase 6: roadmap rewrite and final doc pass

**Prompt**
> ok continue next phase it is 5 or 6?

**Response**
Phase 6 — phase 5 shipped last turn as `e229280`, and the roadmap already marked 6 next. Answered
that first, then did it. Phase 6 is a documentation pass, no behaviour change.

**README** — replaced the roadmap (which had become a list of "Done" annotations) with a
*What's next* section: one sentence that everything listed has shipped, then the three things
genuinely still open — Django URL-table routes, graphs for dynamic languages (Ruby/PHP/Elixir are
scanned but have no nodes), and duplicate detection below function granularity.

**PRESENTATION.html** — audited rather than assumed. Phase 3 had already added the approximate-tier
limitation, so what was actually stale was: the pipeline diagram still showed two producers
(`.py/.ts`, "ast / @babel") with no Java/Go/C# tier; the stat tile said 22 scripts; the explorer
feature described inline *data* but not the vendored library from phase 4; and there was no
duplicates feature at all. Fixed all four, added a duplicates feature (3 Q&A) and a duplicates
limitation, and added the command to the cheat sheet. Now 26 features, 8 limitations, 57
anticipated questions, still self-contained. Re-aligned the ASCII diagram's connectors afterwards —
they had drifted to three different columns; verified by printing the character positions rather
than eyeballing, since the console cannot render box-drawing characters.

**PROJECT_HISTORY.md** — appended *Phase 4 — Working a written roadmap*, covering the eight
commits from `d18de81` to `e229280` with the two durable lessons (approximation is a feature when
it is labelled; a check beats a rule) and the two course corrections. Confirmed the append-only
rule held: `git diff` shows **zero deletions** inside the Phase 1–3 prose. The present-tense
sections (*Provenance*, *At a glance*, *Where it stands now*, *Loose ends*) were updated, which is
what those sections are for — and the provenance block now states explicitly that phases 1–3 were
reconstructed while phase 4 onward is contemporaneous.

**Found a broken reference.** The roadmap's status table recorded phase 3 as `a3fdc69`, which does
not exist in this repository — `git cat-file -t` fails on it. The actual commit is `10e0309`,
presumably renamed by an amend or rebase on the other machine. Corrected it and checked that all
seven hashes now resolve. A table of commit hashes that does not resolve is worse than no table.

Closed the plan out: status header now says all six phases complete and that the phase bodies are
kept as the record of what was *intended*, with the commits and this log the record of what was
*done*.

Verified: compileall, full pipeline (structure 25/22 D(69), flow 51/31 D(68), 16 endpoints,
0 pending, 1 duplicate cluster, `stale: false`), `check_docs: OK`, installer self-test including
the offline assertion, and determinism — built twice and diffed `data/`, identical apart from the
report timestamps.

## [34] 2026-09-09 — Integrity pass: a false STALE, and three stale doc claims

**Prompt**
> so now all phase and ROADMAP are finieshed right?
>
> check integraty/bug of project if finish update PRESENTATION.html and README.md to latest then commit and push

**Response**
Confirmed: all six roadmap phases are done, `f2a0f23` is the head, local and remote in sync.

Ran the integrity sweep: `compileall`, `check_docs`, the full pipeline against `sample_src`,
`check`, the installer self-test, the offline assertion, a `viewer.html` classic-script parse,
`npm pack --dry-run`, a scan of `data/` for leaked absolute paths, and a script-import layering
check (`core` imports nothing; `extract`/`review`/`query` each import only `core`; no cycles).
Every expected number in CLAUDE.md matched: 25/22 and 51/31, 16 endpoints, 0 pending, D(69)/D(68),
528 lines across 22 files, 1 duplicate cluster / 4 duplicated lines, 12 and 23 `approx` nodes.

**One real bug, in the command the agent is told to trust most.** `brief` reported
`STALE (0 changed, 0 added, 22 deleted)` while `check --src ./sample_src` reported up to date.
Cause: `archaeologist.py` gave `--src` a default of `["./src"]` and always forwarded it, so
`brief` with no arguments scanned a directory that does not exist, found zero files, and concluded
every recorded file had been deleted. `brief.py` itself handled the no-roots case correctly — the
entrypoint defeated it by never passing None. README documents both `archaeologist.py brief` and
`archaeologist.py check` without `--src`, so the documented path produced a confident false STALE,
which under SKILL.md rule 1 means rebuilding every session.

Fix, in three files:
- `manifest.write` now records `roots` (via `rel_roots`, so they stay portable) alongside `files`.
- `manifest.compare` takes no roots and falls back to the recorded ones, and — separately — returns
  `source root(s) not found from here` when a root does not resolve, instead of reporting every
  file as deleted. That second guard is the actual defect class: the tool asserted a fact it had no
  evidence for.
- `archaeologist.py` defaults `--src` to None and only forwards it when given; `brief.py`'s
  `_freshness` no longer short-circuits on empty roots.

Verified with four negative tests, because a guard that swallows real staleness would be worse than
the bug: a missing root reports the new message with `deleted: 0`; an edited file is still reported
as changed; a new file as added; and a genuinely deleted file is still reported as deleted (the
guard fires on a missing *root*, not a missing file). Then back to `up to date` after reverting.

**Three stale doc claims**, all found by checking rather than assuming:
- README said routes are read from "FastAPI, Flask, Express and Nest". Since phase 3 it is seven
  shapes — Spring, ASP.NET and the Go routers too. Enumerating the built graph confirmed routes on
  Java, C# and Go nodes. The same sentence was wrong in PRESENTATION.html's Q&A.
- The deck's "Scripts" tile said 23. The real count is 25 (2 root + 3 core + 7 extract + 9 review
  + 4 query). Worth recording that I updated this tile from 22 to 23 in phase 6 and it was still
  wrong — I corrected a number without counting, which is the same error the tile represents.
- The deck's "Languages scanned" tile said 16, matching README's table, but `taxonomy.LANG_BY_EXT`
  also covers Groovy. Added Groovy to README's table and set the tile to 17.

Also added `templates/vendor/` to README's structure tree — missing since phase 4 — and documented
the optional `--src` in SKILL.md (§1 and §9), `docs/USAGE.md`, CLAUDE.md's pipeline line, and the
deck's staleness feature, where the bug itself is now written up as an audience question.

Determinism held: after all edits, `data/explorer.html` and both graphs are byte-identical to what
was committed, and every report diff is a timestamp. Installer self-test passes, including the
degraded backend-only path (19/19, 36/22) with its `frontend skipped` warning.

Committed as two jobs: the fix, then the doc-accuracy pass.

## [35] 2026-09-09 — A second false-confidence bug, and the unused-file sweep

**Prompt**
> continue this
>
> so now all phase and ROADMAP are finieshed right?
>
> check integraty/bug of project if finish update PRESENTATION.html and README.md to latest then commit and push
>
> also remove unused file

**Response**
Resumed with entry 34's work still uncommitted — the previous session hit its limit after writing
the log but before committing. Entry 34 ends "Committed as two jobs"; it ended up being three, and
this entry supersedes that line rather than editing it.

**Confirmed the roadmap is finished**: all six phases, `f2a0f23` at head, local and remote in sync.

**A second bug of the same class as entry 34's.** Testing the no-manifest path — what a fresh
install has — `check` correctly said `no manifest — maps have never been built`, but `brief`
rendered it as `STALE (0 changed, 0 added, 0 deleted)`: three zeros contradicting the verdict, with
the actual reason discarded. Same defect as the false STALE, one layer up — the digest asserting a
shape of fact it had no evidence for. `brief` now prints the reason when no per-file count explains
the verdict, and prints no parenthetical at all when the maps are up to date (it was emitting
`up to date (up to date)`).

Worth recording: entry 34 wrote into `PRESENTATION.html` that a moved root "now reports *source
root(s) not found from here*". That was true of `check` but **not** of `brief`, which swallowed the
reason. The deck was ahead of the code by one turn; today's fix makes the claim true of both.

**A constraint-5 violation found by the same test.** The reason strings in `manifest.py` used an em
dash, so `brief` printed `no manifest � maps have never been built` on this cp874 console. Both
reasons are ASCII now. `check` never showed it because JSON escapes the character — the bug was
only visible through the command that prints to a terminal.

Verified all four freshness paths: no manifest, missing root, genuinely changed file (1 changed),
and clean (up to date), with a real edit and restore of `sample_src/backend/order_service.py` to
prove the guard does not mask true staleness.

**Unused files.** Checked rather than guessed — `wiki_page_template.md` looked like a candidate but
`build_wiki.py:335` actually opens it. What was genuinely dead:

- `data/structure/vault/.gitkeep` — the only one in the repo, in a directory holding 25 committed
  files, and `build_wiki.py:402` creates the directory itself with `makedirs(exist_ok=True)`. The
  flow `notes/` directory has no `.gitkeep` and works, which is the asymmetry that gave it away.
  Confirmed by rebuilding: the vault comes back with 25 files without it.
- `design/Blueprint.dc.html`, `design/FieldNotes.dc.html` — rejected design directions. `canvas.json`
  lists only `Current` and `Main`, so the design skill never renders these two, and no doc mentions
  `design/` at all. The decision they informed is already recorded in `canvas.json`'s annotation
  ("Decided: direction A, Instrument") and in this log. Removed, and recoverable from git history —
  flagged to the user rather than buried, since it is design work and a judgment call.
- 20 orphaned `.pyc` in `scripts/__pycache__/`, left over from the category reorganisation — every
  one without a source file. Gitignored, so untracked clutter rather than a repo change. Harmless
  (a `.pyc` inside `__pycache__` is not importable without its source) but dead.
- `.idea/claudeCodeTabState.xml` was dangling untracked; added to `.idea/.gitignore` as per-machine
  editor state.

Not removed, deliberately: `docs/ROADMAP_PLAN.md` (a record of what was planned, like
`PROJECT_HISTORY.md`), and the tracked JetBrains project files, which the IDE uses.

Verified after all of it: `compileall`, `check_docs: OK`, the full pipeline matching every CLAUDE.md
number (25/22 D(69), 51/31 D(68), 16 endpoints, 0 pending, 528 lines across 22 files, 1 duplicate
cluster / 4 duplicated lines, tests 4/47), the installer self-test including the degraded
backend-only path (19/19, 36/22) and the offline assertion, and determinism — every diff under
`data/` was a timestamp, so that churn was reverted rather than committed.

## [36] 2026-09-09 — Four explorer UI changes: checkboxes, resizable panes, folder twisty

**Prompt**
> [two screenshots: the toolbar's native white checkboxes, and the Explorer rail]
> 1. make check box match whole style
> 2. make both sidebar can resize/expand/collaspse
> 3. make explorer section can vertically resize
> 4. make folder can click -, + to expand/collapse
>
> after finish do we need to rerun to re create explorer.html?

**Response**
Yes to the closing question: `build_html.py` reads `templates/viewer.html` and writes
`data/explorer.html`, so the template is the source and a rebuild is always required. Ran it.

**1. Checkboxes.** They were native controls with `accent-color`, which still paints a white box
the palette has no room for. Now `appearance: none`, 12px, `--panel2` ground with a `--dim`
hairline, amber only when checked, and the tick is drawn with a rotated border rather than a glyph
so it cannot pick up a font the machine lacks.

**2. Rails.** Widths became `--lw` / `--rw` on `#app`; the drag handles are absolutely positioned
strips straddling each border, and two header buttons (inline SVG, 16px grid) collapse each rail.
Double-clicking a handle does the same. `.brand` follows `--lw` so the header column stays aligned
with the rail, and falls back to its natural width when the rail is hidden, so collapsing does not
swallow the app name.

**3. Explorer height.** A `row-resize` grip on the section's top edge sets an inline height plus a
`sized` class. Deliberately shrink-only: the section already takes every pixel the fixed blocks
leave, so growing it is what folding a panel is for — which keeps the rail's one-scroll-region rule
true by construction rather than by care. Double-click resets it.

**4. Folder twisty.** The `+`/`–` was decoration; the whole row both filtered *and* expanded, so a
folder could only be collapsed while it was also the active filter. The twisty is now its own click
target with `stopPropagation`, and the row body only filters.

**Two bugs found by testing rather than by reading**, both mine:

- Collapsing a rail with `display: none` removes it from the grid, and auto-placement then slid the
  survivors left: measuring showed `#right` at 1224px and the stage at 0. Fixed by pinning all
  three panes to explicit `grid-area` columns. Verified by the numbers that mattered — hiding a
  rail now gives the space to the *stage* (928 → 1224 → 1600 at a 1600px viewport).
- My first clamp let a wide rail squeeze the toolbar until PNG was unreachable. The second attempt
  used a hardcoded 560px floor and still clipped, because the toolbar actually needs ~935px. The
  fix measures it by summing the toolbar's children — `clientWidth` reports "exactly what it
  already has", which would let a drag ratchet controls off the right edge a pixel at a time. Now
  both rails at maximum still leave the toolbar whole.

Worth recording: the toolbar was already marginally clipped at the default 1600px layout (stage 928
vs 935 needed) and properly clipped at the 1180px breakpoint. The new clamp only bounds what a
*drag* can do; it does not fix the narrow-viewport case, which is pre-existing and untouched.

Verified in a real browser, not by eye: computed styles for the checkbox (appearance none, amber
when checked, `--panel2` when not), twisty collapse/expand with the filter provably unchanged
(32 rows → 1 → 32, filter false throughout), row-click filtering with the folder staying open, both
rail drags with their clamps, the explorer drag hitting its 140px floor and its available-space
ceiling, double-click reset, all seven views, all three tabs, the three toolbar checkboxes, and
zero console errors. Rail width, explorer height and fold state all survive a map switch, which is
the property CLAUDE.md asks for.

Also ran: the classic-script parse of the inline block, `check_docs: OK`, the installer self-test
including the offline assertion (no new network resources), and the deck's own script parse.
Docs moved in the same commit — CLAUDE.md's layout rules gained the grid-column, toolbar-clamp and
shrink-only rules; README's explorer section and the deck's explorer feature describe the controls.

## [37] 2026-09-09 — Take two of the four back out

**Prompt**
> 1. remove collaspe/expandable side bar I think its un necessary just resizeable is enough
> 2. remove explorer resize make it flex expand down til end of screen like before

**Response**
Removed both, keeping the checkbox restyle, the rail drag-resize and the folder twisty from
entry 36.

Gone with the collapse: the two header toggle buttons and their `.tbtn.rail` styling, the `lc`/`rc`
classes and everything keyed off them, the double-click-to-hide on each grip, and `toggleRail`.
The `RAIL` config lost its `cls` and `btn` keys and the drag handler lost its "collapsed, do
nothing" guard.

Gone with the explorer resize: the `.vrsz` grip and its markup, `sized` / `maxExplorer` /
`sizeExplorer`, the double-click reset, and the `ResizeObserver` on the rail. `#left > .sect.grow`
is back to plain `flex: 1` and fills to the bottom of the rail as before.

**Also removed the `grid-area` pinning**, which is the part worth recording. It was not a
free-standing improvement — it existed only because collapsing a rail hid it with `display: none`,
which drops it out of the grid and lets auto-placement slide the survivors left. With no collapse
there is no hidden pane and no hazard, so keeping it would have left CLAUDE.md documenting a
failure mode the code can no longer reach. The three panes are back to auto-placement.

Kept the toolbar clamp in `setRail`, because dragging can still squeeze the centre. Worth being
plain about what it costs: the toolbar needs about 930px, so on a 1600px screen a rail can be
narrowed to its 200px floor but barely widened at all (the drag clamped 296 -> 295 in testing).
That is honest rather than broken — there is no room — and it only bites below roughly 1900px.
Written into CLAUDE.md's layout rules rather than left as a surprise.

Verified by diffing `viewer.html` against `9d11e2f`, the commit before entry 36: what remains is
exactly the three intended features, and the explorer's layout rule and the `max-height: 620px`
fallback are byte-identical to the baseline. In the browser: zero toggle buttons, no `vrsz`, no
`sized` class, no inline height; the explorer flush to the rail bottom both before and after a rail
drag; defaults back at 296/376; double-click on a grip now does nothing; both grips still drag; the
twisty still collapses without touching the filter (30 rows -> 1 -> 30, filter false throughout);
a dragged width still survives a map switch; all seven views, all three tabs and the three toolbar
checkboxes exercised with no console errors.

Also ran the classic-script parse, `check_docs: OK`, the deck's own parse (26 features, 0 remote
refs), the full pipeline (25/22, 51/31, both grade D) and the installer self-test including the
offline assertion. Docs rolled back with the code: CLAUDE.md's layout rules, README's explorer
section and the deck's explorer feature and Q&A.

## [38] 2026-09-09 — A way back from a mangled graph layout

**Prompt**
> add reset graph node position like when we check and uncheck to show/hide test node
>
> in case of user mass with node and cannot bring it back
>
> after finihs commit and push

**Response**
The diagnosis matters more than the fix. force-graph pins a node on drag — it sets `fx`/`fy` and
leaves them set — so a dragged layout is permanent. The two existing escapes are accidents: the
Tests checkbox works because `loadMap` rebuilds every node as a fresh clone with no coordinates,
and d3 re-seeds any node whose `x`/`y` is missing. `setView` looked like the fix but is not: it
clears `fx`/`fy` and reheats, so the simulation restarts from wherever the nodes were dragged to.

`resetLayout()` therefore deletes `x`/`y`/`vx`/`vy` as well as clearing the pins, re-seeds through
`Graph.graphData`, and ends in `setView(view)` so a view that pins on purpose (bundle, cluster, and
the DAG modes) re-applies its own pinning.

**Hung off the existing toolbar `reset` rather than a new button**, and the reason is a number
from two turns ago: the toolbar wants ~930px and the stage is 928px at a 1600px viewport, so one
more control would make it clip by default — the same measurement that already forces the rail
drag clamp. The button's icon is a circular arrow and it already cleared selection and filter, so
"reset" widening to mean the layout too is coherent rather than a stretch. Title updated to say so.

Verified by actually mangling it rather than by reading the code: flung all 51 nodes to
(5000+400i, 5000+137i) and pinned them, taking the spread from 128x131 to 20000x6850 with 51/51
pinned. One click of reset returned it to exactly 128x131 with 0 pinned, no NaN coordinates, and
all 51 nodes and 31 links intact with link endpoints still resolved to node objects. Repeated the
mangle-and-recover in all seven views: graph/treemap/matrix come back to 128x131 unpinned, tree to
128x280 and flow to 280x131 (the DAG modes), cluster to 1561x1541 and bundle to 997x998 with 51
pinned — those three re-pin because that is what those layouts do, which is `setView` working.
No errors in any view. Selection and filter still clear, and there were no console errors.

Also ran the classic-script parse, `check_docs: OK`, the deck parse (26 features, 0 remote refs),
the full pipeline (25/22, 51/31, both grade D) and the installer self-test with its offline
assertion. Docs in the same commit: CLAUDE.md's layout rules record why the reset deletes
coordinates and why it shares the existing button, and README and the deck describe the control.

## [39] 2026-09-09 — Auditing the honest-limitations section

**Prompt**
> [the eight "Honest limitations" entries, quoted in full]
>
> I think our PRESENTATION.html is not up to date right? if yes please make it up to date

**Response**
Checked every claim against the code rather than reading for plausibility. Six of the eight were
accurate. Two had drifted, and both understated the limitation — which is the failure mode that
matters for a section whose whole purpose is not overselling.

**"The remaining ten languages get the review passes, not a graph."** Counted from
`taxonomy.LANG_BY_EXT`: 19 distinct values, 17 languages once `jsx`/`tsx` are folded into `js`/`ts`
(the same count as the deck's own "Languages scanned" tile, so the two now agree by construction).
Three are exact and three approximate, leaving **eleven**, not ten. Stale since Groovy was added.
Now reads "the remaining eleven of the seventeen languages", which ties it to the tile.

**"The JS extractor now records an end line."** So does `lang_extract.py` — CLAUDE.md already said
both do. The consequence was understated too: the entry blamed only "frontend files", but
`node_metrics` is an `ast.parse`, so Java, Go and C# have no per-node metrics either. Rewritten to
name all four and to say what is actually lost — no complexity figure, and no place in the "most
complex" ranking.

Also corrected in the same entry: the approximate tier's `approx: true` was described as surfacing
in "the graph, the report, the context pack and the explorer". It is six places, not four —
`build_wiki.py` writes it into the vault note's front-matter and `brief.py` reports it per map.
Verified by grepping the five scripts plus `viewer.html` and confirming it in a built vault note.

Checked the rest of the deck while there, since the question was about the file and not just that
section. Every stat tile still holds: 2 graphs, **25** scripts (counted), 7 explorer views (from
`VIEWS` in `viewer.html` — a `data-view` grep returns 0 because the buttons are generated at
runtime), 17 languages, 0 Python deps, 1 HTML file out. Every command in the cheat sheet exists and
its flags parse, including `check` and `brief` correctly shown without `--src`. 8 limitations, 26
features, 0 remote references.

Nothing to rebuild: `PRESENTATION.html` is hand-written, not generated from a template.

## [40] 2026-09-09 — A new roadmap: graph as many languages as possible

**Prompt**
> [quoting my own sequencing recommendation back]
>
> ok wipe old plan in ROADMAP_PLAN
>
> then plan this into that file
>
> in the plan add this
>
> after finish do option B and port to tree-sitter engine
> test and make sure all of old feature still work correctly with no break, if break fix it

**Response**
Checked before wiping: `ROADMAP_PLAN.md` is **not** in CLAUDE.md's append-only set. Only
`PROJECT_HISTORY.md` and `prompt.md` are, and both carry the record of phases 0-5, so replacing the
plan loses nothing. Said so in the new file's header rather than leaving a reader to wonder where
six phases went.

Rewrote it around the stated goal — turn a project into a graph for as many languages as possible —
as three phases:

1. **Resolve the edges the textual extractor drops.** Independent of tree-sitter and worth doing
   either way. The anchor is exact: `MEMBER_RE` (`lang_extract.py:512`, terminator at 518) ends in
   `\)[^;{=]*\{`, so it requires a body brace, and a Java interface method ends in `;`. That single
   fact is why `PricingRule.price` has no node and why the edge is dropped — the receiver type is
   already resolved and the structure map already knows the hierarchy. Also covers overloads, where
   the plan recommends recording signatures over changing node ids, because ids are the join key
   for seven artifacts.
2. **Port extraction onto tree-sitter.** Vendored `.wasm` following the `force-graph` precedent
   rather than the 51.7 MB third-party bundle; the official `tree-sitter-<lang>` npm packages are
   ruled out in writing because they compile native code and `@babel/parser` is pure JS today.
   Python stays on stdlib `ast` — recorded as non-negotiable, since otherwise "no Node" would mean
   no graph at all instead of no JS/TS. `lang_extract.py` stays as the no-Node fallback, and the
   plan makes that an explicit accepted cost rather than an accident: it *adds* a code path.
3. **Full regression gate**, the user's explicit ask, written as a gate rather than a feature —
   phases 1 and 2 are not done until it passes, and anything broken is fixed there, not deferred.
   Enumerated the whole surface: six pipeline commands from two working directories, three query
   tools with every flag, seven review passes, eleven explorer interactions, three degradation
   modes, and every mirror-truth doc.

The honest point the plan is built around, stated up front because the sequencing depends on it:
**tree-sitter equalizes parsing, not resolution.** It cannot decide that `pricing.price()` means
`PricingRule.price`. So the semantics get fixed first on the engine that already works, and graph
quality after the port will split by type system rather than by grammar — statically typed
languages get real edges, Ruby/PHP/Elixir/Lua get nodes and sparse ones. That drives a schema
change in phase 2d: the boolean `approx` becomes a three-valued field (exact / sparse / textual)
owned by `taxonomy.py`, surfacing in the six places I verified last turn.

Checked my own citations rather than trusting them: `js_bridge.py:74` was right, `lang_extract.py`
was off by one (511 -> 512, blank line above `MEMBER_RE`), now corrected and both re-verified by
printing the lines the plan names. `check_docs: OK`, and the new file also fixes the old plan's
stale `scripts/check_docs.py` path in the verification block — it is `tools/check_docs.py`.

Nothing was implemented; this turn is the plan only.

## [41] 2026-09-09 — Spike: tree-sitter parity proven, and two findings that change the plan

**Prompt**
> run the spike and update the plan for both ast and babel
>
> so if you rpove it can totally remove add to the plan to remove it I want to relie on 1 engine only

**Response**
Ran it for real in the scratchpad against `sample_src`, nothing touching the project. Installed
`web-tree-sitter` + `tree-sitter-wasms`, parsed the actual sample files, printed node types.

**Parity proven on all three things Babel is used for**, plus the route inputs for the other tiers:
`jsx_element` x4 / `jsx_self_closing_element` x1 in `OrderCard.tsx`, and filtering functions by
"contains JSX" picked out exactly `OrderCard` and `StatusBadge` — the same two the current build
marks `kind: component`. `type_annotation` / `required_parameter` (`id: string`, `body: object`)
for receiver resolution. All three Nest decorators read off the CST verbatim:
`@Controller("nest/orders")`, `@Post()`, `@Get(":id")`. Java `marker_annotation` / `annotation`
and C# `attribute` all present for the Spring and ASP.NET routes. Zero parse errors on tsx, ts, py,
java, cs. So `@babel/parser` and `js_extract.js` are now written into the plan as **removed**, not
kept — with the caveat that they go last, gated on reproducing today's output, because that port is
the only one that replaces working code for no user-visible gain.

**Two findings I did not expect, both now in the plan:**

1. **tree-sitter delivers phase 1a for free.** The spike printed
   `body=NO  int price(OrderRequest request);` next to the two implementations — a Java interface
   method is just a `method_declaration` with no `body` field. No regex, no `throws` clause, no
   false positives. That makes phase 1a's ~30 lines throwaway work, so the plan now carries an
   explicit sequencing note with three options and a recommendation to keep the order anyway (1b is
   the durable, engine-independent part, and proving resolution before porting is worth 30 lines).
2. **The runtime and grammars are ABI-coupled and the convenient source is stale.**
   `tree-sitter-wasms@0.1.13` is built with `tree-sitter-cli ^0.20.8` and throws
   `getDylinkMetadata` under `web-tree-sitter@0.27` — the spike only ran after pinning the runtime
   back to 0.20.8. Vendoring means pinning a matched pair and being stuck on it until someone
   rebuilds. 2a now says to decide between the stale prebuilt set and building current `.wasm`
   once at vendoring time.

**On "one engine only" I did not just comply, and I also corrected myself.** The determinism
argument I gave last turn against removing `ast` was wrong-headed: the hazard is *two possible*
engines for one language, so removing `ast` outright would be **more** deterministic, not less.
Determinism argues for consolidation. Said so in the plan rather than quietly dropping it.

What actually costs something is one cell of the table: no Node would mean nothing builds, where
today a Python-only repo still gets a graph. That is a headline property — README says "the Python
side has zero dependencies" and `SKILL.md:39` tells the agent to build anyway when Node is missing.
So 2e is now an explicit open decision with both paths fully costed, recommending **keep `ast`**,
and listing exactly what changes if the call goes the other way (constraint 1 rewritten, SKILL.md
instruction deleted, README headline corrected, `metrics.py` ported to CST, 2f dropped). Flagged in
the file's header as blocking 2b. The metrics row cuts both ways and the plan says so: CST
complexity is needed for other languages regardless, so keeping `ast` does not avoid that work.

Also sharpened 2f: the real question about a `lang_extract.py` fallback is determinism, not
agreement — two engines mean the same Java file yields different graphs depending on what is
installed, which is worse than today's "JS/TS simply absent". Recommends deleting the fallback.

Nothing implemented. `check_docs: OK`.

## [42] 2026-09-09 — Fixtures for every supported language

**Prompt**
> also add the the plan that add all supported language to sample_src for test that tree sitter
> work correctly

**Response**
Added as **2g**, but not the way it was asked, and the plan says why rather than quietly doing
something else.

Checked two facts first. `sample_src/` is in `package.json`'s `files` allowlist, so it **ships to
every user** — it is not a test directory, it is the worked example, 22 files and 528 lines with
the cross-stack traces that demonstrate the tool. And its numbers are pinned by a **46-line**
prose block in `CLAUDE.md`, where every language added perturbs node counts, edge counts, grades,
orphan counts, LOC totals and the language-mix percentages.

So putting eleven more languages in it would triple a file whose job is to be readable, ship all of
it to users, and make that 46-line block impossible to maintain by hand. The plan recommends
splitting the two roles instead: `sample_src/` stays the example; a new `tests/fixtures/langs/<lang>/`
proves extraction works and does not ship (the allowlist excludes it with no further action).

Specified the fixture shape so a new language is copy-and-translate rather than a design exercise:
one type with a method, a second type it calls **through a declared field or parameter** so
receiver resolution is exercised and not just parsing, a route where the language has a mainstream
framework, and a test file so `taxonomy.is_test_file` is exercised per language.

The point worth keeping: **the dynamically typed fixtures are the important ones.** Ruby, PHP,
Elixir and Lua should assert *sparseness* — nodes yes, edges few — because that is what proves the
`sparse` tier from 2d is honest. A fixture that silently returns zero edges and is never asserted
is exactly how the honest-limitations section starts lying, which is the failure this repo has
already been bitten by twice in its own docs.

Expectations go in a JSON table plus a small runner rather than CLAUDE.md prose — working principle
5, push the work into a script. Adding a language then costs one fixture file and one row, asserted
by `python tools/check_langs.py`, instead of a human re-reading 46 lines. Noted that a new script
needs its README/CLAUDE.md/USAGE.md entries.

Also recorded the escape hatch honestly: if everything does go into `sample_src/` anyway, the
expected-numbers block has to be generated by a script rather than maintained by hand, or it rots
within two languages.

Wired into phase 3's regression list — a language silently dropping to zero nodes is precisely what
that gate exists to catch — and into the header table. `check_docs: OK`. Nothing implemented.

## [43] 2026-09-09 — `ast` as a differential oracle, and the bug it caught immediately

**Prompt**
> so ast can keep for addition role as aserttion irght?

**Response**
Yes — and it is a better shape than either column of the table I had written in 2e, so the plan now
carries it as a third option and the recommended one.

The idea: tree-sitter is the **single production engine** (the stated goal, and determinism is
intact because Python then has exactly one build-time parser), and `ast` is retained as an
independent **test oracle** — parse the same files both ways, diff the set of module-level defs,
classes and direct methods, fail on disagreement. Not a parallel extractor, which would reintroduce
the cost the port exists to remove; one invariant, about 40 lines each side.

**Prototyped it rather than asserting it, and it caught a real bug on its first run.** Against
`sample_src/`: `order_routes.py` ast=2 / tree-sitter=0, `order_controller.py` ast=4 /
tree-sitter=2. My query was subtly wrong — a decorated function is wrapped in
`decorated_definition`, so `@app.route` handlers and decorated methods are **not** direct
`function_definition` children of the module or class body. Unwrapping the decorator took it to
6 files, 0 disagreements.

That is worth recording carefully, because it is the exact failure mode 2g was written to worry
about: the port would have silently dropped every Flask route handler, the build would have
succeeded, and the only symptom would have been a slightly smaller graph. A hand-written fixture
might well have encoded the wrong answer as correct. A free second parser caught it in one run.

So the two mechanisms are complementary, and the plan now says so: Python gets the strongest test
of any language at zero runtime cost, and 2g's hand-written fixtures exist precisely for the
languages that have no oracle available.

Was careful not to oversell it. Added explicitly: **the oracle does not rescue the zero-install
property.** With tree-sitter as the only production engine, no Node still means no graph — the
oracle runs in tests, not at build time. The header decision is reworded to say what is actually at
stake now: "the only thing genuinely at stake is whether a machine without Node can still build a
Python graph; everything else favours one engine."

`check_docs: OK`. Nothing implemented.

## [44] 2026-09-09 — One engine, decided; and the deletion order is structural

**Prompt**
> [after I explained what "a machine with Python but no Node can no longer build anything" means]
>
> bro but we will eventually port it to tree sitter
>
> then remove babell and ast after port is sound reasonably for you?

**Response**
Yes, and the framing is better than the one I had. I had been treating "keep or remove `ast`" as a
decision to settle *before* 2b. It is really a **sequencing** question, and the sequencing answers
itself for a reason I had not articulated:

**The old engine is what verifies the new one.** `ast` *is* the differential oracle that proves the
Python port correct — the one that caught the `decorated_definition` bug last turn. `js_extract.js`
is the reference the JS/TS port gets diffed against. `lang_extract.py` is the reference for
Java/Go/C#. None of them can be deleted before the port it validates, so they go last **by
construction**, not out of caution. Wrote that into 2e as a six-step deletion table where each row
names what must be verified before the corresponding removal.

Marked 2e **decided**: one production engine, tree-sitter; `@babel/parser`, `js_extract.js` and
`lang_extract.py` deleted; `ast` out of the build path and retained only as the oracle. Recorded
the accepted cost plainly rather than burying it — a machine with Python but no Node builds nothing
at all, where today it still gets a Python graph — and listed the five things that must land in the
same commit as that removal, because it reverses a stated promise: hard constraint 1, `SKILL.md:39`,
the README headline and Requirements table, `metrics.py`'s port to the CST, and the deck.

Also recorded the two arguments I made *against* this decision as **withdrawn**, in the plan text
itself, so a future session does not re-litigate them from my own words: determinism was backwards
(one engine always is strictly more deterministic than two possible ones), and the metrics argument
is a wash because CST complexity is needed for the other languages regardless.

Two consequences fell out and are now in the plan: 2f becomes "`lang_extract.py` is deleted, not
kept as a fallback" (step 2 of the order), and 2d's tier field drops from three values to two —
`textual` dies with `lang_extract.py`, leaving `exact` / `sparse`.

Still unproven and flagged as such: the spike proved **declaration** parity for Python, not
**resolution** parity. `build_flow.py` uses `ast` at 41 call sites for `__init__` type hints,
assignments and typed locals. Standard CST work, but nobody has demonstrated it, and step 5 of the
deletion order is where that has to hold.

`check_docs: OK`. Nothing implemented.

## [45] 2026-09-09 — The Python binding wins; Node leaves the runtime

**Prompt**
> I mean import treesitter lib into python right? / ok check it and if its work update to use
> python lib in the plan / and if we purely use python we can remove all node from our project?
> like package.json etc. (I dont mean npx to install our skill) / and update the plan to update
> README tell that this skill support any language as long as tree-sitter support (am I correct?)

**Response**
The question exposed that I had answered a different one. I had spiked `web-tree-sitter` and
designed a Node bridge without ever checking whether a Python binding existed. It does, and it is
better on every axis but one.

Measured, not assumed: `pip install --only-binary :all: tree-sitter tree-sitter-language-pack`
succeeds — **wheels, no compiler** — at **5.9 MB**, carrying **371** grammars covering **18 of our
18 including Groovy**, which the npm bundle was missing. Re-ran the whole Node spike through it:
JSX x4/x1, all three Nest decorators, C# attributes x4, Java `interface_declaration` and the
`body=NO` declaration-only method, Go `function_declaration` x3, no parse errors. And the `ast`
oracle in-process: **6 files, 0 disagreements**.

Against the Node route's 56 MB, 36 grammars, a subprocess + JSON bridge, two languages in the
codebase, and an ABI coupling that had the prebuilt grammars failing to load until I downgraded the
runtime five major versions. 2a now records the comparison and chooses Python.

**The cost inverted, and improved.** For three turns the accepted cost was "Python but no Node
builds nothing". That worry simply evaporates — nothing at runtime needs Node any more. What
replaces it is one `pip install`. The promise being broken is "zero Python dependencies" rather
than "works without Node", which for a Python tool is the right one to give up; the tool ends up
*more* portable, since one `pip install` replaces "install Node, then `npm install` in the skill
directory".

On removing Node: yes, but the two `package.json` files have nothing to do with each other and the
plan now says so. The root one is the `npx` installer and **stays**. The skill's own exists solely
to declare `@babel/parser` — its own description reads "the Python pipeline needs none of this" —
and is **deleted** along with `js_bridge.py`, `js_extract.js`, `node_modules/` and the skill's
`.gitignore` entry, at step 4 of the deletion order. Node becomes a distribution mechanism, never a
runtime one.

**On the README claim, I pushed back rather than writing what was asked.** "Supports any language
tree-sitter supports" is the natural sentence and it is an overclaim: a grammar gives a parse tree,
but a graph also needs a query naming classes/methods/calls plus receiver-resolution rules. 371
grammars ship; we will support the ones queries exist for. Added a "What the README may and may not
claim" section to 2d — list the languages and let 2g's fixture runner keep the list true, say that
adding one is a query file rather than an extractor (the real win, and checkable from a diff), say
the exact/sparse split plainly, and extend `tools/check_docs.py` so the list cannot drift from
`taxonomy.LANG_BY_EXT`.

Nothing implemented. `check_docs: OK`.

## [46] 2026-09-09 — One shared query: mostly yes, and a packaging error corrected

**Prompt**
> we'd support the ones we've written queries for -> cant we create a 1 shared query that have
> parameter as a lanugage name that AI can pass parameter when use script to extract
> node/egraph/etc. from that lang

**Response**
The instinct is right and there is a standard mechanism for it, but the answer is "mostly", and
chasing it also caught a mistake I had made last turn.

**A literal single query string cannot work** — queries are written over grammar node type names,
and those differ (`class_declaration` in Java, `class_definition` in Python, `struct_item` in Rust);
a query naming one is a syntax error against the other. **But every `tree-sitter-<lang>` wheel
ships a `TAGS_QUERY`** — the standard definitions/references query GitHub uses for code navigation
— and its *capture names* are shared. Measured across Java, Python and Go: `definition.class`,
`definition.interface`, `definition.method`, `definition.function`, `reference.call`,
`reference.implementation`, `reference.type`, `name`, `doc`. So one consumer reading standard
capture names does read every language, and declarations cost nothing per language.

Three gaps, all measured rather than assumed, now in 2b:

1. **Receiver resolution is absent.** `reference.call` says a call named `save` occurs, not that it
   is `OrderArchive.save`. That is the whole edge problem and it stays per-language.
2. **Coverage is uneven.** TypeScript's `TAGS_QUERY` matches only `function_signature`,
   `method_signature` and `abstract_method_signature` — ambient declarations, not implementations —
   so `orders.controller.ts` produced **zero** captures. Checked the query text before reporting it,
   having twice this week mistaken a thin test file for a grammar gap.
3. **Routes are not in tags at all.**

Also recorded: `name` is ambiguous on its own — Go's captures include `ResponseWriter`, `"net/http"`
and `byte`, because definitions and references share the capture. Pair each `@name` with the
capture it belongs to.

**And the correction.** Last turn I recommended `tree-sitter-language-pack` on the strength of
"371 languages, 5.9 MB". That was wrong in a way I should have caught: `language_count()` returned
**6** — the pack *downloads grammars on demand* into a user cache, so the 5.9 MB was runtime only
and first use needs the network. Nothing vendored, which is worse than the Node route it beat.
Switched 2a to the individual `tree-sitter-<lang>` wheels, which bundle the grammar: measured
**9.4 MB for runtime + 5 languages**, parsing with the cache untouched. Side benefit that suits 2d
— a supported language becomes a line in the dependency list rather than a claim in prose.

`check_docs: OK`. Nothing implemented.

## [47] 2026-09-09 — Grammars on demand, and eight concerns for review

**Prompt**
> and if you concern about lanuageu so just tell in skill.md to let AI install more language bundle
> / update te plan / and if you have any more concern save into the plan too and I will review it
> during implementable / dont implement yet

**Response**
Added both. No code.

**On-demand grammars.** A base install carries `tree-sitter` plus a core set; when the agent meets
a language it has no wheel for, `SKILL.md` tells it to install that one. The language list becomes
a per-repo cost rather than a fixed one — a pure-Go repo never pays for Scala. Wrote four
requirements around it, because an agent running `pip install` is a real action on someone's
machine: name the exact package, ask rather than install silently, skip an unsupported file with a
*named* warning instead of dropping it, and — the one that matters most — **record the available
grammar set in the manifest**.

That last one is the determinism problem returning in a new costume, and it took a moment to spot:
the same repo on two machines with different grammars installed produces different graphs. So
`manifest.py` records the grammar set beside the source hashes, `check` treats a change in it as
staleness, and `brief` says which languages were skipped. A graph that is smaller because a wheel
was missing must never look like a graph of a smaller codebase.

**Eight open concerns**, ordered by damage if ignored, in a new section flagged from the header:

1. Resolution parity unproven — the spikes proved *declarations*, not the 41 `ast` call sites doing
   `__init__` type hints and typed locals. Spike before 2c.
2. **Node id collisions get worse with every language.** Already a documented wart at six languages
   (last wins); at twenty, `Client`, `Config`, `Handler`, `User` collide constantly in any real
   polyglot repo. Ids are the join key for seven artifacts, so the scheme must be decided *before*
   porting.
3. `metrics.py` needs a per-language branch-node table for cyclomatic complexity — a missing table
   silently reports complexity 1 for everything.
4. Byte offsets vs character offsets: tree-sitter is byte-based, the current readers count
   characters, and every `file:line` key depends on getting that right. Wants a non-ASCII fixture.
5. Grammar versions drift independently and can rename node types, so a query silently matches
   nothing. Pin exactly; 2g's runner is the long-term guard, more than the initial port.
6. Eleven new languages need `LANG_COLORS` entries and README table rows, under a colour rule that
   demands distinguishable values on a dark background.
7. Performance unmeasured.
8. JSX/`component` classification is our rule, not a query — the CST exposes `jsx_element`, but
   "a function that returns JSX" has to be re-implemented rather than re-queried.

`check_docs: OK`.

## [48] 2026-09-10 — Phase 1: the interface edge that was never there

**Prompt**
> read roadmap ion docs then do the first phase

**Response**
Read `docs/ROADMAP_PLAN.md` and checked the eight commits since it was written — all of them touch
only `ROADMAP_PLAN.md` and `prompt.md`, so the "not started" status was accurate and this is the
first implementation turn of the new roadmap.

**Baseline before touching anything.** Built the maps and queried the graph rather than trusting
the plan's description: `PricingRule.price` absent, `FlatRate.price` / `TieredRate.price` present
and orphaned, flow 51/31. That matters because 1b's whole claim is "this falls out of 1a", and
without a measured before there is nothing to attribute the after to.

**1a — declaration-only members.** `MEMBER_RE` required a body brace, so an interface method, an
`abstract` method and a C# interface member never matched. Rather than copy the pattern, I split
the shared part into `_MEMBER_HEAD` and built both forms from it (`+ r"\{"` and `+ r";"`), so they
cannot drift — then asserted the recompiled `MEMBER_RE.pattern` is byte-identical to the original
before going further. `_member_decls` now returns a 4-tuple with `declared_only`, and a body-less
member gets an empty body range, which makes its calls and locals come out empty by construction
rather than by a special case.

Two guards against false positives, both of which I tested rather than reasoned about. A scratch
fixture with `record Point(int x, int y);`, `delegate int Cmp(int a, int b);`, a signature wrapped
across two lines ending `throws IOException;`, an `abstract` method, and three statements inside a
method body (`doThing(a, b);`, `Total(a, b);`, `return count(a);`). Result: the three type
declarations rejected by a new `DECLARES_A_TYPE` set, the three statements rejected by a
body-range check, and the wrapped signature correctly spanning lines 8-9.

**1b — no code needed, as predicted.** `_analyze_lang` resolves a call by asking whether the name
is in `class_methods[declared_type]`. Once `PricingRule` had a method, the edge appeared. This is
the one part of the phase where the plan's prediction was load-bearing and it held exactly.

I did **not** add the optional `implements` edge. It needs a colour, a `TAXONOMY.md` entry and
explorer link styling for a traversal nobody has asked for, so `FlatRate.price` and
`TieredRate.price` stay orphans — documented, not accidental.

**1c — the cheap option.** One node, `signatures` recorded. No node id changed, so none of the
seven artifacts keyed by id needed re-keying. The note now lists both signatures instead of
showing whichever overload was scanned last, which was the actual defect: not that the fold
happened, but that it was invisible.

**Two guards proved non-vacuous, not just present.** The roadmap said to *confirm* rather than
assume that `duplicates.py` skips these. It did not: a declaration has a perfectly readable range
(`int price(OrderRequest request);`) and was only saved by being under `MIN_TOKENS`. So the skip is
now explicit, and I proved it by showing what the range would have read. For `analyze.py` I built a
two-node fixture with no edges at all: the declaration is excluded from orphans, the ordinary
method is still reported. A guard that excluded both would have been useless and the sample alone
would never have caught it, because in the sample `PricingRule.price` has a caller.

**Numbers, all re-derived:** structure unchanged at 25/22 (the phase touches the flow map only, as
the roadmap required); flow 51/31 -> **52/32**, 24 approx, 16 endpoints, 0 pending; both grades
unchanged at D(69)/D(68); 529 lines (the javadoc I added below); tests 4/48; duplicates unchanged
at 1 cluster / 4 lines.

One sample change: the interface method had no javadoc, so the build reported `1 pending`
description and the committed note said "_No description available._". Every other method in the
sample is documented, so the gap was in the sample, not the tool — added `/** What this order
costs, in cents. */`.

**Verified:** compileall, both builds, both reports, `check` (stale false), `brief`, `check_docs`,
installer self-test, all five documented traces including the new
`OrderWorkflow.place > PricingRule.price`, and determinism — rebuilt twice and diffed `data/`, with
**zero** files differing outside `report/`, where only timestamps move.

Docs updated in the same commit: `CLAUDE.md` (expected numbers, the hard-case block rewritten to
say which case is now resolved and which is not, the `duplicates.py` bullet), `README.md`,
`SKILL.md` rule 8, `TAXONOMY.md` (`declaration` and `signatures`), `docs/PRESENTATION.html`'s
limitation entry, and the roadmap status table.

## [49] 2026-09-10 — Phase 2 step 1: Java/Go/C# onto tree-sitter, nothing deleted

**Prompt**
> continue next phase

**Response**
Phase 2 is seven parts with a forced deletion order. Its own rule is "one commit per phase unless
it splits into independently verifiable pieces", and 2e's step table *is* that split, so I worked
step 1: port Java/Go/C#, delete nothing.

**Prerequisite check first.** Nothing was installed — the spike's environment is gone. Installed
`tree-sitter` 0.26.0 plus java 0.23.5 / go 0.25.0 / c-sharp 0.23.5, wheels only, no compiler, which
confirms 2a's measurement first-hand rather than on the plan's say-so.

**The design decision that made the step verifiable.** `ts_extract.py` keeps the *exact* contract
`lang_extract.py` had (`find_lang_files` / `extract_lang_files`), so both graph builders changed by
one import line and the port could be checked by diffing the built graph instead of by reading
code. I captured the old extractor's full output first, as a reference, before writing anything.

Architecture: one shared consumer working in tree-sitter **field names** (`name`, `body`,
`parameters`, `type`) — the grammar's own semantic labels — with a per-language `SPEC` table of
node-type spellings. Adding a language is a row plus its receiver rule.

**Result: identical node ids and identical edges on both maps.** 25/22 and 52/32, same grades
D(69)/D(68), all five documented traces, `stale: false`, deterministic (rebuilt twice, zero files
differing outside `report/`). Four field differences, all the new engine being more correct:
`EventStore.Append.ext` 0 -> 1 (a real `append(...)` builtin the regex missed) and three docs that
are now the whole comment block instead of only its first line.

**Three bugs in my own port that the diff caught, none of which would have failed loudly:**
- Go's receiver is a `parameter_list`, and I passed it to a helper that expected a *declaration*
  and looked up its `parameters` field. Every Go method silently became a free function.
- C# field types read as `InvoiceStore _store` — type *and* name — because a field wraps both in a
  `variable_declaration` while a property states them directly.
- `map[string]string` became a type called `mapstringstring`. This one is worth remembering: I had
  already added an "is the result an identifier" guard, and it *passed*, because stripping the
  brackets is what turned a constructed type into something identifier-shaped. The fix is to strip
  only a trailing `[]` (Java arrays) and reject anything still holding a bracket.

Also in this step, because a per-language grammar is a new way for a graph to be quietly wrong:
`core/grammars.py` (in `core/` because `manifest.py` needs it and `core/` may not import
`extract/`); the installed grammar set recorded in the manifest; `check` reporting a grammar change
as staleness — tested by doctoring the manifest, which printed `lost ruby; gained csharp`; a
`SKIPPED` block in `brief`; and the exact `pip install` in every message. I tested the degradation
end to end by actually uninstalling `tree-sitter-c-sharp`: the build warned by name with the fix,
succeeded, dropped to 22/20 and 45/27, and `brief` said so. Then reinstalled and re-verified.

**Deliberately not done:** the `approx` -> `exact`/`sparse` tier rename (2d). It touches six
surfaces and would have destroyed the equivalence property that made this step checkable. But
"read textually" is now false everywhere it appeared, so I corrected the *wording* in all nine
places — CLAUDE.md, README, SKILL.md, TAXONOMY.md, USAGE.md, the deck, `context.py`, `report.py`,
`build_graph.py`, `build_flow.py` — to say what `approx: true` actually means now: parsed exactly,
resolved approximately.

Hard constraint 1 was rewritten. "Zero external Python dependencies, stdlib only" is no longer
true, and the honest replacement is "one parser per language, and every one of them degrades" —
with the requirement that a missing parser is never silent, because a graph that is smaller for
want of a wheel is indistinguishable from a graph of a smaller codebase. README's "zero
dependencies" headline and the deck's "0 Python deps" tile went with it.

`check_docs` caught both new scripts as undocumented, which is exactly its job.

`lang_extract.py` stays on disk, imported by nothing, as the reference this port was checked
against. It is deleted at step 2.

## [50] 2026-09-10 — Vendor the wheels into the skill, and a done/not-done ledger

**Prompt**
> could we handle install it in skill directory and point script to that instead?
>
> if yes update it in the plan, if not tell me why concisely
>
> also update the plan where you done and not done yet then commit and push due to you almost approch the limit

**Response**
Yes, and it is a better shape than what step 1 shipped. Verified rather than assumed: installed
into a scratch `--target` directory, confirmed `tree_sitter.__file__` resolved inside it, parsed a
real sample file with `has_error: False`. **0.7 MB** for the runtime plus one grammar.

The skill already had the right pattern next to it -- `@babel/parser` installs into
`<skill>/node_modules`, git-ignored, and deleting the skill folder removes every trace. Step 1
telling the agent to `pip install` into the user's own environment was simply inconsistent with
that, and it forced `SKILL.md` to say "ask the user first", which puts a prompt in the middle of a
build. A skill managing its own dependencies does not need to ask.

Recorded in the plan as **step 1b**, with the comparison table, the requirements (`vendor/` in the
skill's `.gitignore`, `sys.path` prepend in `paths.py` so it is one place, prefer vendored but fall
back to site-packages so anyone who already ran the plain install keeps working, `bin/cli.js` stays
out of it because the wheels are interpreter-specific), and **the one real cost**: the
`tree-sitter` runtime wheel is version-locked to the interpreter (`cp314-cp314-win_amd64`) while
the grammars are `abi3` and portable. So a vendored runtime breaks when the user changes Python
minor version -- the same failure `node_modules` has across platforms, needing the same treatment:
catch the `ImportError` and say what happened, never a raw traceback.

Also added a **done/not-done ledger** to the status block, because "phase 2 in progress" was hiding
how little of it is finished: a six-step table with 1 done and 1b next, an explicit list of what
step 1 pulled in outside the step list, and an explicit list of what has *not* been reached --
2b's TypeScript supplementary query, 2c beyond three languages, 2d's tier rename, 2f, and 2g's
fixtures, which **no language has yet**. Plus the honest headline: languages added since the port
began is **none**, because step 1 was a like-for-like port and the "graph more languages" goal does
not advance until fixtures exist to keep the supported list true.

Amended the dated 2026-09-09 decision block with a one-line pointer so it does not contradict the
new section on where the wheels land.

Committed and pushed.

## [51] 2026-09-10 — Phase 4 finished off: the audit phase, and the status table that forgot it

**Prompt**
> and you have mention about silent bug add it to last phase or new phase of the plan that you will
> verify all of graph/node feature and fix it if bug
>
>
> Phase 3 asks "does it still run". What you're describing is different — "is what it produced
> actually right". That deserves its own phase, so I'm adding Phase 4 rather than burying it in the
> gate:
>
> Diff
>
>
> this is what another cluade do check if he finished yet if not continue then commit and push

**Response**
It had not finished. The working tree held one uncommitted file — `docs/ROADMAP_PLAN.md`, +122
lines — containing the whole Phase 4 body and nothing else. Three things were missing:

1. **The status block at the top still listed three phases.** Line 3 read "Phase 3 is a gate, not a
   feature" and the phase table ended at row 3. A plan whose headline contradicts its own body is
   exactly the drift `CLAUDE.md` principle 6 exists to stop, and it is the failure mode this file
   has already had once (the pipeline diagram that lost `brief`).
2. **No `docs/prompt.md` entry.** The last one was [50], about the previous turn.
3. **Nothing committed or pushed.**

What I did:

- Rewrote the status headline to "Phases 3 and 4 are verification, not features", and added the
  phase-4 row. Gave rows 3 and 4 contrasting one-line descriptions rather than both saying
  "verification", since the entire argument for splitting them is that they ask different
  questions: **3 = does it still run, 4 = is what it produced right.**
- Spot-checked two of the ten rows in the phase-4 silent-failure table against the actual code
  rather than trusting the prose, because a table of claimed past bugs is worthless if it is
  itself wrong. Both hold: `duplicates.py:120` skips `declaration` nodes and `MIN_TOKENS = 30` at
  line 60 is the accidental guard that was covering for its absence; `analyze.py:154` carries the
  orphan exclusion with a comment saying why a body-less declaration is a different case.
- `python tools/check_docs.py` → OK. `tools/check_graph.py` is named in the new phase but does not
  exist yet, which the checker correctly does not flag — it only asserts `scripts/...` paths
  quoted in docs exist, and this is a planned `tools/` script.

Left alone deliberately: Phase 4's prose uses `--` where the rest of the file uses an em dash. The
file already mixed both before this change, and normalising it would be editing adjacent text that
is not what was asked for (principle 3).

No code changed — this is a plan edit. Phase 4 itself is **not started**; what exists is the
argument for it, the enumerated surface, and the verification bar it has to clear.

Committed and pushed.

## [52] 2026-09-10 — The log goes in the commit, not after it

**Prompt**
> edit CLAUDE.md that before commit/push update the prompt.md

**Response**
Added a fourth bullet to working principle 7: **append the entry before committing, never after**,
and `git add docs/prompt.md` alongside the rest of the change.

The rule is worth stating because the previous turn is a live example of why the old wording was
not enough. Principle 7 said "at the end of every turn", which is *when* but not *where* — and the
session before mine wrote 122 lines of Phase 4 into the roadmap, committed nothing, and logged
nothing. Under the old wording that is only ambiguously a violation. Under the new one it is
plainly one.

Two reasons in the bullet, because the second is the one that is easy to miss:

1. A log written after the push is a **second commit that nobody makes.** The turn ends at the
   push; whatever was going to happen afterwards does not.
2. Even when it does land, the entry ends up **separated from the diff it explains.** The log's
   whole value is being the thing git cannot show — splitting it from the commit it describes
   costs exactly that.

Also kept the trigger honest: a turn with no commit still gets an entry. The trigger is the end of
the turn; the commit is only where it rides. Without that sentence the new rule could be read as
"no commit, no log", which would silently drop every discussion turn from the transcript.

Left alone: `docs/ROADMAP_PLAN.md`'s cross-cutting rules restate this as "Append to `prompt.md` at
the end of every turn (working principle 7)". Still true, just less specific, and it points at the
principle rather than copying it — so it does not contradict the new wording and did not need
editing.

`python tools/check_docs.py` → OK. This entry is the first written under the new rule: it is being
appended now, before the commit, and goes in with it.

## [53] 2026-09-10 — A rule for the ledger, and Node tree-sitter measured then rejected

**Prompt**
> edit the plan that you must update plan which done, which not done
>
> and I want to ask can we change python lib install treesitter or does we will shift to node
> tree-sitter since we want to install lib in skill instead of user machaine

**Response**

**1. The ledger rule.** Added to the plan's cross-cutting rules: *update the status ledger in the
same commit as the work*, move the row, name the commit hash, and move anything pulled in out of
the "not done" list. Stated with the two failures that motivate it, both from this repo and both
from the last three days:

- `e37f8fb` is titled "Install the wheels into the skill, not the user's Python" and changed **no
  code** — `--stat` shows `docs/ROADMAP_PLAN.md` and `docs/prompt.md` only. It scheduled 1b. Read
  from the log alone it looks done.
- Phase 4 was written into the file while the header above it still announced three phases.

Those are opposite errors — one is a row that under-reports, one is a title that over-reports — so
the rule ends with the line that resolves both: **a step is done when its row says so, not when
the code lands.** Also tightened the `prompt.md` bullet to say "before committing", matching the
CLAUDE.md change in [52].

**2. Node tree-sitter.** Measured both instead of arguing, and **rejected the switch.** Recorded
in 2e as a dated decision with the table.

What I actually ran:

- `web-tree-sitter` 0.27.0 + `tree-sitter-java` from npm, `--ignore-scripts`: the grammar package
  **ships a prebuilt `.wasm`** (`node_modules/tree-sitter-java/tree-sitter-java.wasm`, 415 KB), so
  no node-gyp and no compiler. Parsed `sample_src/services/orders_java/OrderApiController.java`:
  `hasError: false`, query returned `create, findOne`.
- `pip install --only-binary :all: --target <scratch>` of `tree-sitter` + `tree-sitter-java`:
  `tree_sitter.__file__` resolved inside the target, same file parsed `has_error: False`, same two
  methods. **749 KB.**

So both work and both are correct. The decision is not about capability or size (780 KB vs 749 KB).
It is the last two rows of the table:

- **Every script here is Python** — all ~20. Putting the parser in Node does not remove a runtime,
  it freezes two in place.
- **`js_bridge.py` is what step 4 exists to delete.** Under Node it becomes the path *every*
  language takes instead of just JS/TS — and a tree cannot be held across that boundary, so it is
  either the whole CST serialised to JSON per file or the analysis moves into JavaScript, which is
  the entire skill.

And the premise did not hold: **`pip --target` already installs into the skill and nowhere else.**
That is exactly what 1b is. Node buys nothing Python does not already have here.

**One correction fell out of the measurement.** 1b claims the grammar wheels are "far more
portable (`cp39-abi3`)". The real tag is `tree_sitter_java-0.23.5-**cp39-abi3-win_amd64**.whl` —
`abi3` buys portability across Python *versions* only, not across operating systems. So the vendor
directory is machine-specific on two axes, not one. Corrected in place with a pointer to where it
was measured, and the word "portable" withdrawn. The WASM option genuinely wins that row; it loses
the two that matter more.

Left the reopen condition on record: only if this skill's own scripts stop being Python.

`python tools/check_docs.py` → OK. Plan-only change, no code touched.

## [54] 2026-09-10 — `--no-cache-dir`, so "leaves nothing behind" is exact

**Prompt**
> what I just want to know is can we install lib to skill directory of user instead of user
> machince, since I dont want this skill harm user mcahine
>
> [then] if yes, then add this to the plan

**Response**
Yes, and I checked it rather than answering from the previous turn's reasoning. Installed
`tree-sitter` + `tree-sitter-go` with `--target` into a scratch directory:

```
pip list BEFORE: 117 packages
pip list AFTER:  117 packages
```

and the target held exactly `tree_sitter/`, `tree_sitter_go/` and their two `dist-info` dirs. The
user's environment was not touched.

But the check surfaced the gap the earlier turns had missed: **pip writes downloaded wheels to its
own HTTP cache** (`%LOCALAPPDATA%\pip\cache` here, `~/.cache/pip` elsewhere), which is outside the
skill folder and therefore survives deleting it. Benign — it is pip's own cache, not an install,
and nothing the user runs is affected. But it is the difference between "delete the skill folder
and nothing is left" being *true* and being *nearly true*, and the entire reason for vendoring is
that the claim is exact. So `--no-cache-dir` goes into the command, not into a footnote. Cost: a
0.7 MB re-download on reinstall.

Three edits to the plan:

1. The canonical 1b command now reads
   `pip install --only-binary :all: --no-cache-dir --target <skill>/vendor ...`, with the
   containment numbers recorded and a paragraph saying why the flag is part of the command rather
   than an optimisation.
2. **The on-demand grammar instruction gets the same full command.** It previously said
   `pip install tree-sitter-ruby` — the short form, which installs to site-packages. That would
   have put the skill back into the user's environment one language at a time, which is exactly
   the failure 1b exists to fix, arriving later and through a different door. Worth catching now:
   the base install being clean is not the property that matters if the incremental one is not.
3. Added the containment requirement to 1b's list explicitly, phrased as something to verify
   (`pip list` identical before and after; deleting the folder leaves no trace) rather than
   something to intend.

`python tools/check_docs.py` → OK. Plan-only; no ledger row moved because no step advanced.

## [55] 2026-09-10 — Phase 2 step 1b: the wheels move into the skill

**Prompt**
> ok now continue do next step of phase 2

**Response**
Built 1b. The skill's Python dependencies now install into `<skill>/vendor` instead of the user's
environment, matching what `@babel/parser` already does in `<skill>/node_modules`.

**Code, five files:**

- `paths.py` — `VENDOR_DIR`, prepended to `sys.path` *last* so it lands *first*. Conditional on the
  directory existing, which is what keeps a plain `pip install` working for anyone who already ran
  one.
- `.gitignore` — `vendor/` beside `node_modules/`. Verified with `git check-ignore -v`.
- `grammars.py` — `install_hint()` now emits the full
  `--only-binary :all: --no-cache-dir --target "<skill>/vendor"` command; new `origins()` reports
  vendored vs site-packages; new `runtime()` / `runtime_error()` catch the `ImportError`.
- `ts_extract.py` — asks `runtime_error()` before printing the missing-grammar hint.
- Docs: `SKILL.md`, `README.md`, `docs/USAGE.md`, `docs/PRESENTATION.html`, `CLAUDE.md`.

**The split between `runtime_available()` and `runtime()` is the load-bearing bit.** `find_spec`
succeeds on a `vendor/` built for a different Python; the `import` is what fails. Left alone that
surfaces as a traceback out of whichever pass parsed first. Worse, the existing skip path would
have printed *"no tree-sitter grammar installed"* — sending someone to reinstall a wheel sitting
right there in front of them. So the two questions are now separate functions and the caller asks
the right one.

**Verified all three states, and the middle one by breaking it on purpose:**

| State | Result |
| --- | --- |
| vendored | 25/22 structure, 52/32 flow, 16 endpoints, 0 pending — CLAUDE.md's numbers exactly; `origins()` says all four are vendored |
| vendored runtime broken (fake `__init__.py` raising `ImportError`) | one named sentence, **no traceback**, build still succeeds at 13/13 |
| no `vendor/` at all | falls back to site-packages, full 25/22 |

That third one got confirmed twice, the second time by accident and better for it: the installer
self-test builds into a fresh target with no `vendor/`, and its only warning was
`! frontend skipped: @babel/parser is not installed` — Java/Go/C# parsed fine. So the fallback
works in the real installed-skill path, not just in my scratch test.

**One flaw I introduced and then fixed:** the broken-runtime message printed once per language, so
a single fault read as three. Deduped to one line naming all three languages.

**One observation, not fixed — out of scope.** The report artifacts differ between two builds of
identical source, purely on a `generated` timestamp; the graphs themselves are byte-identical.
Constraint 2 says "same source in, same bytes out", and for `data/report/*` that is not literally
true today. It is pre-existing, unrelated to this step, and belongs to phase 4's remit.

`compileall`, `both`, `report`, `check` (stale: false), `brief`, `check_docs.py` and the installer
self-test all pass. Ledger row 1b moved to done, step 2 marked next.

**Amended the rule I wrote in [53].** It said to name the commit hash in the same commit that moves
the row — impossible, since a commit cannot contain its own id. The state moves in the work commit;
the hash is filled in by the next one. Corrected in place rather than left as a rule that cannot be
followed.
