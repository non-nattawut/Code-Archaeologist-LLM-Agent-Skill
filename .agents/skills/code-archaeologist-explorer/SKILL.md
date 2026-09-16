---
name: code-archaeologist-explorer
description: Create, initialise or replace the Code Archaeologist explorer page (data/explorer.html) for this project -- builds both maps and the review report, then renders the one self-contained, offline HTML page a human opens in a browser. Use only when the user asks for the explorer / explorer.html itself; for questions about the code, use the code-archaeologist skill.
---

# Skill: Code Archaeologist Explorer

One job: leave an up-to-date `data/explorer.html` in the **code-archaeologist** skill folder. It
creates the page on a project that has never been built and replaces it on one that has. Answering
questions about the code is the main skill's job, not this one's.

The scripts live in the main skill, installed next to this folder:
`.agents/skills/code-archaeologist`. The installer rewrites that prefix to wherever it installed
the skill; if the folder was copied by hand, use that folder in every command instead.

## Steps

**1. Source roots.** Use the folders the user named (`/code-archaeologist-explorer ./backend
./frontend`). Otherwise reuse the roots the last build recorded -- the `roots` list in
`.agents/skills/code-archaeologist/data/cache/manifest.json`. With neither, use `./src` if it
exists; if it does not, ask the user which folders to map. Never guess a root that does not exist.

**2. Preflight, on the first build only** (no `manifest.json` yet). Python 3.10+ is required;
older or missing, stop and say so. Then install the grammars for the languages the roots contain,
yourself -- they go into the skill's own `vendor/`, never into the user's Python:
```bash
python --version
python .agents/skills/code-archaeologist/scripts/core/grammars.py --install python typescript   # the repo's languages
```
The main skill's `SKILL.md` (*Setup*) has the full language list and what each message means.

**3. Build both maps, then the report.** Always both commands, in this order: the first rebuilds
the structure and flow maps from the current source, the second grades them and re-renders the
explorer with both reports embedded (health ring, churn/risk colours, Patterns and Security tabs).
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py both   --src <roots>
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src <roots>
```
If a build prints `pending` descriptions, leave them: the page renders without them, and filling
them in is the main skill's *Keeping the maps current* step.

Only when the user explicitly asks to re-render **without** rebuilding (the maps are already
current), run this instead of step 3:
```bash
python .agents/skills/code-archaeologist/scripts/query/build_html.py
```

**4. Report back.** Give the path to `.agents/skills/code-archaeologist/data/explorer.html`, the
node/link counts and grade per map the build printed, and every `skipped` warning word for word --
a language whose grammar is missing is absent from the page, and nothing on the page says so. Open
the file only if the user asks (`start` on Windows, `open` on macOS, `xdg-open` on Linux).

## What to tell the user about the page

- One self-contained file, both maps (header switch), no network: it opens from `file://` and can
  be emailed to someone without the repo.
- Seven views (Graph, Treemap, Matrix, Tree, Flowchart, Cluster, Bundle); the file tree filters the
  canvas; **Blast radius** shades what the selected node reaches; **Freeze** holds the current view
  while you click through its nodes; dragging pins a node, and the toolbar **reset** re-runs the
  layout and is the only click that clears a selection.
- Call links are a lower bound: a call is drawn only when the source states the receiver's type.
- Replacing the page overwrites the previous one. It is regenerated from the source, so nothing is
  lost that a rebuild cannot bring back.
