# Project History — Code Archaeologist LLM Agent Skill

How this project went from an empty repo to its current state.

> **Provenance.** This document is reconstructed from the **git history** (44 commits,
> 2026-09-02 → 2026-09-06), not from chat transcripts. Claude does not retain memory between
> sessions, so the commit log — subjects, bodies, and the verification notes recorded in them — is
> the authoritative record of what happened and why. Where a commit body stated the reasoning, that
> reasoning is quoted or paraphrased here rather than guessed at.

---

## At a glance

| | |
| --- | --- |
| Repo | `Code-Archaeologist-LLM-Agent-Skill` |
| Commits | 44 |
| Span | 2026-09-02 → 2026-09-06 (5 days) |
| Cadence | 13 commits day 1 · 1 commit day 3 · 30 commits day 5 |
| Current HEAD | `3bc603b` — *revisual* |
| Skill location | `.agents/skills/code-archaeologist/` |
| Hard constraint held throughout | Zero external Python deps (stdlib only, 3.10+) |

The idea never changed: **build a deterministic map of a codebase so an agent answers architecture
questions by querying a graph and reading a handful of notes, instead of scanning source.** Every
phase below is an expansion of that one premise.

---

## Phase 1 — The engine (2026-09-02, 13 commits)

### The core, in one commit

`1a84b1f` **Initial commit: Code Archaeologist code-wiki skill** established the whole shape of the
project on day one:

- `build_wiki.py` — AST scan → `data/vault/*.md` (one note per class, `[[wikilinks]]`)
- `build_graph.py` — vault → `graph.json` + `registry.json`
- `trace_path.py` — BFS flow (`--from/--to`) and impact (`--impact-of`)
- `build_html.py` — standalone shareable HTML graph viewer
- `SKILL.md`, a page template, and the `sample_src` demo trio

Preceded only by `7f08c63` (LICENSE + README stub).

### Making it installable

- `b3f2903` install scripts + full README
- `f4f9d0a` npx/npm installer (`code-archaeologist-skill`)
- `4f8d48d` let users pick the harness — `.claude`, `.agents`, `.cursor`, `.windsurf`, `.zed`
- `eaaea59` **removed** the shell installers once npx covered them

### The second map — the pivotal design decision

`9041193` **Add method-level flow map alongside the structure map.** The original graph was
*structural* (which class references which). This added a *behavioral* one: a method-level
call/request-flow graph.

- `build_flow.py` resolves `self.<dep>.m()` via `__init__` type hints/assignments, typed
  params/locals, and same-class `self.m()` calls; marks controller methods as endpoint roots
- `archaeologist.py` became the single entrypoint with `project` / `flow` / `both`
- Verified on the sample: `create_order → place_order → {save, charge}` and
  `get_order → find_order → get` — the same assertion still used to verify builds today

**Two maps, one entrypoint** has been the project's backbone ever since.

### Descriptions without burning tokens

`0efc94e` **Hybrid method descriptions.** Graph structure stays 100% deterministic AST; only the
prose is AI-written, and it is cached by source hash so *only new or changed methods ever cost
tokens*:

```
docstring  ->  cached AI summary (valid while source hash matches)  ->  deterministic auto
```

`apply_descriptions.py` merges agent-written summaries into the cache keyed by the current hash, so
edits auto-invalidate and deletions get pruned. This is the mechanism that keeps the skill cheap to
re-run.

### Beyond Python

- `29ec90c` frontend (JS/TS) + monorepo support (`--src` accepts multiple roots) + a shared
  `taxonomy.py` so both extractors emit the same `kind`/`layer` values
- `42a1bfe` **cross-stack API-edge linking** — frontend `fetch`/`axios` calls matched to backend
  route handlers by HTTP method + normalized path, so one trace crosses the whole stack
- `c4e802e` made the Node/`@babel/parser` dependency an explicit, documented setup step

### Ground rules

`750dbd3` added **CLAUDE.md** — skill-creator identity, project orientation, and the working
principles (think before coding, simplicity first, surgical changes, goal-driven execution) that
later commits visibly follow.

---

## Phase 2 — Trust the map (2026-09-04, 1 commit)

`f5828d7` **Add staleness guard, diff blast-radius, smell report; reorganize data/**

Three features aimed at a single weakness: *the skill's answers were only as good as the freshness
of its graph, and nothing enforced that.*

| Feature | Command | Problem solved |
| --- | --- | --- |
| **Staleness guard** | `archaeologist.py check --src ...` | Builds record a content-hash of every scanned file (`manifest.py` → `cache/manifest.json`). Reports `{stale, changed, added, deleted}` so the agent rebuilds before trusting a drifted graph. |
| **Changeset blast-radius** | `trace_path.py --impact-of-diff` | Maps a git diff to nodes and unions their upstream impact — "what does this PR affect?" — crossing frontend→backend `http` edges. |
| **Smell report** | `analyze.py` | Cycles (Tarjan SCC), orphan/dead nodes, backwards layer violations. |

Two false positives were found and fixed during verification: cross-stack `http` edges were being
flagged as layer violations (a frontend client calling a backend controller is the *correct*
direction), and dunder methods like `__init__` were being reported as orphans.

The same commit reorganized `data/` by map — `structure/`, `flow/`, `cache/` — while deliberately
leaving `scripts/` flat, because the scripts import each other as siblings and moving them would
break those imports for no real gain.

---

## Phase 3 — From tool to instrument (2026-09-06, 30 commits)

The largest day by far. Four threads ran through it.

### 3a. A review pass, not just a map

`613e25b` **Add review pass: risk scan, git hotspots, health grade, report + viewer modes** —
described in its own commit body as porting "the ideas worth having from browser-based codebase
analyzers into the deterministic, stdlib-only pipeline":

- `scan_security.py` — line scan for hardcoded secrets, interpolated SQL, `eval`/`innerHTML` sinks,
  debug leftovers; every finding attributed to the graph node owning that line, secrets redacted,
  tests/fixtures skipped
- `git_insights.py` — one `git log --numstat` pass → churn, ownership, hotspot ranking
  (`risk = commits × (1 + fan_in + fan_out)`)
- `analyze.py` grew high-coupling hubs, god objects, idiom detection, and a 0–100 / A–F health score
- `report.py` + `archaeologist.py report` joined it into `architecture_report.{md,json}`

The bundled sample gained three *deliberate* smells so the committed demo exercises the scan
end-to-end.

### 3b. The explorer

- `418fd78` rebuilt the viewer as a **three-pane code explorer** with per-map reports
- `036f4d3` merged both maps into **one** `explorer.html`, switched from the header
- Later polish: folder hulls drawn per cluster rather than one stretched blob (`1e6eff3`), padded
  along their edges (`433375a`), test areas green with stable folder colours (`d5c48d4`),
  a re-skin toward "instrument, not dashboard" (`df84731`), and fixed chrome with only the
  explorer scrolling (`69a5ec3`, `3bc603b`)

### 3c. The rename and the doc reckoning

`f11111b` **Rename the skill to code-archaeologist; rewrite CLAUDE.md.** The folder was still called
`code-wiki` while the package, repo, CLI and docs all said Code Archaeologist. The same commit
rewrote CLAUDE.md, which "was describing the skill as it stood several features ago."

Follow-ups closed the drift: `078f556` realigned SKILL.md/TAXONOMY.md/installer with the code,
`c6dea41` made dependency setup an explicit agent preflight, `aca9bf6` split the command reference
out of README into **USAGE.md**, and `0b10afc` stopped shipping build junk and put SKILL.md "on a
diet."

### 3d. Token reduction — planned, then built

`f06e5f3` recorded a roadmap of "five near-term scripts, each justified by a specific place the
agent currently spends tokens," then delivered them in order:

| Commit | Script | Purpose |
| --- | --- | --- |
| `7c1a85e` | `metrics.py` | LOC, cyclomatic complexity, nesting depth, params per node |
| `d7ee9e3` | `brief.py` | fixed-size digest to open a session with |
| `adc156a` | `context.py` | one budgeted per-node pack instead of six reads |
| `fe76038` | — | compact text output for `trace_path` / `analyze` |
| `1c61f93` | `search.py` | find nodes without grepping source |

Then `1b068f3` "Fix what the review turned up in the five new scripts" — the batch was reviewed
before being trusted.

### 3e. Debt and tests

`e918d68` added the **debt inventory** and **test-coverage map** (`debt.py`, `tests_map.py`).
`f927c51` taught `taxonomy.py` to classify test code across a dozen languages "so it stops reading
as dead" — test files get `layer: test`, which is why `analyze.py` no longer calls them dead code
and `scan_security.py` skips them. `401179d` then used test edges for *coverage* while keeping them
out of *coupling* metrics. `16d6d0d` gave the sample a real test suite so the demo exercises that
path.

---

## Where it stands now

```
.agents/skills/code-archaeologist/
├── SKILL.md
├── scripts/          22 files — archaeologist, build_*, analyze, report, brief,
│                     context, search, metrics, debt, tests_map, scan_security,
│                     git_insights, manifest, taxonomy, console, js_*
├── templates/        viewer.html · TAXONOMY.md · wiki_page_template.md
└── data/             structure/ · flow/ · report/ · cache/
CLAUDE.md · README.md · USAGE.md · PROJECT_HISTORY.md · prompt.md · package.json · bin/cli.js
```

Four docs, four readers: **SKILL.md** (the agent), **README.md** (someone evaluating it),
**USAGE.md** (someone running it by hand), **TAXONOMY.md** (someone adding a field value).

### Loose ends worth knowing

- The `.agents/skills/code-wiki/` husk left behind by the `f11111b` rename was **removed**
  (2026-09-08). It held no source — only `.pyc` caches, a gitignored `manifest.json`, and
  `node_modules`. That `node_modules` happened to hold the machine's only copy of
  `@babel/parser`, so deleting it silently degraded JS/TS parsing until the dependency was
  reinstalled in the live skill; the build now says so loudly instead of quietly shrinking.
- `ROADMAP.md` was **removed** (2026-09-08). Every near-term item and three of four backlog
  items had shipped, so it had become a record of finished work that this document now covers.
  Its one surviving idea — duplicate-code clusters via normalized token hashing — moved to the
  README roadmap.
- Distribution went the GitHub route rather than the npm registry — publishing hit an npm 2FA wall,
  so install is `npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill`. The package is
  publish-ready if that is ever revisited.

---

## The through-line

Reading the log end to end, the same few commitments show up in almost every commit:

1. **Determinism first.** AST and graph traversal do the work; the LLM only writes prose, and only
   for what changed.
2. **Push work into a script, not into the context.** Every recurring question became a script —
   `search.py`, `brief.py`, `context.py`, `manifest.py` all exist because an agent was spending
   tokens re-deriving something.
3. **One meaning, one colour; one entrypoint; one page.** Consistency treated as a feature.
4. **Docs ship in the same commit as the behaviour.** Twice the project stopped to fix doc drift
   (`f11111b`, `078f556`) rather than let it compound.
5. **Verify against the sample, every time.** The same assertion from day one —
   `create_order → place_order → {save, charge}` — still gates changes today.
