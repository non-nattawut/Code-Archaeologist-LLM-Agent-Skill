# CLAUDE.md

You are the **skill creator** of the **Code Archaeologist LLM Agent Skill** — the agent skill that
lives in `.agents/skills/code-archaeologist/`. Your job in this repo is to build and maintain that
skill, **not** to use it on this repo.

## What the skill is

A deterministic, Zero-RAG codebase documentation engine. It builds two maps of a target codebase,
reviews them, and renders one browsable page:

| Map | Nodes | Built by | Output |
| --- | --- | --- | --- |
| **Structure** | classes/entities | `build_wiki.py` → `build_graph.py` | `data/structure/{graph.json, registry.json, vault/*.md}` |
| **Flow** | methods/functions | `build_flow.py` | `data/flow/{flow_graph.json, notes/*.md}` |

An agent answers architecture questions by **querying the graph, then reading only the notes on the
returned path** — never by scanning source.

### Pipeline (what calls what)

```
archaeologist.py  project | flow | both | check | report        <- the only entrypoint
  project  -> build_wiki -> build_graph ------------------\
  flow     -> build_flow (+ js_bridge -> js_extract.js) ---+--> render_explorer()
  report   -> report.py (scan_security + git_insights + analyze + metrics) -> data/report/<map>/
  brief    -> brief.py (reads the artifacts above, computes nothing)
  check    -> manifest.py (source hashes vs last build)
                                                            \-> build_html.py -> data/explorer.html
```

- `taxonomy.py` owns every `kind`/`layer` value (mirrored in `templates/TAXONOMY.md`). Add values
  there, never inline.
- `trace_path.py` is the query tool: `--from/--to` (BFS path), `--impact-of` (blast radius),
  `--impact-of-diff` (map a git diff to nodes, union their impact). Works on either graph.
- `analyze.py` is graph-only: cycles, orphans, layer violations, hubs, god objects, name-based
  idioms, and the 0–100 / A–F `health()` score (accepts security counts).
- `scan_security.py` is line-regex over source; every finding is attributed to the node owning that
  line. `git_insights.py` is one `git log --numstat` pass → churn, owners, hotspot risk.
- `metrics.py` is line counts per file plus LOC / cyclomatic complexity / nesting depth /
  parameter count per node, keyed like the graph nodes (Python only: `js_extract.js` records no
  end line yet). `report.py` derives `file_census` from it, so line counts have one definition.
- `search.py` is the "which nodes are these" filter over one graph (name/doc/layer/kind/lang/file
  plus `--calls` / `--called-by` / `--orphans`). It exists so neither the agent nor a human greps
  source to find a starting node.
- `context.py` is the per-node pack: graph facts + metrics/security/insights for one node and its
  neighbors, rendered under a hard `--max-chars` budget. Like `brief.py` it only reads artifacts.
- `brief.py` is the fixed-size digest an agent should open a session with — it only reads what the
  other scripts wrote. Anything expensive belongs upstream of it, never inside it.
- `report.py` joins all of it into `data/report/<map>/architecture_report.{md,json}` plus
  `security.json` / `insights.json`. **One report per map** — node ids differ between maps, so a
  report from the other map must never be embedded (`build_html.report_for()` enforces this).
- `build_html.py` is thin: it loads `templates/viewer.html`, substitutes `__TITLE__` and
  `__MAPS_DATA__`, and writes **one** `data/explorer.html` holding both maps (header switch).

### Where the front-end lives

`templates/viewer.html` is a normal HTML/CSS/JS file (three-pane explorer: health ring + tiles +
LOC/language mix + file tree | seven views: Graph/Treemap/Matrix/Tree/Flow/Cluster/Bundle |
FILE/PATTERNS/SECURITY tabs). Edit it directly; don't move markup back into Python. Its per-map
state is rebuilt by `loadMap()` / `applyMap()` — anything derived from a graph belongs in there,
not in a top-level `const`.

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
SQL, an innerHTML sink — so the review path has something to find):

- flow graph: 13 nodes / 9 edges, 3 endpoints, **0 pending** descriptions
- traces: `create_order → place_order → {save, charge}` and `get_order → find_order → get`;
  cross-stack `submitOrder → createOrder → OrderController.create_order → …`
- grades: structure **C (75)**, flow **D (67)**; 4 risk findings
- `archaeologist.py check --src ./sample_src` → `stale: false` right after a build

Other checks worth running when you touch the relevant part:

```bash
python -m compileall -q .agents/skills/code-archaeologist/scripts     # syntax
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

### 5. Keep the docs in the same commit
Three files describe this skill to different readers — when behavior changes, update all that apply:

| File | Reader | Covers |
| --- | --- | --- |
| `SKILL.md` | the agent using the skill | operating principles + numbered tool commands |
| `README.md` | a human evaluating/installing it | features, requirements, install, layout |
| `USAGE.md` | a human running it by hand | the full command reference + worked example |
| `templates/TAXONOMY.md` | anyone adding a field value | allowed `kind`/`layer`/severity/grade values |

A new script also needs: a docstring saying what it is and why, a line in the README structure
tree, a numbered command in `SKILL.md` if the agent should call it, and its command form in
`USAGE.md`.
