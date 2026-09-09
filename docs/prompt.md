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
