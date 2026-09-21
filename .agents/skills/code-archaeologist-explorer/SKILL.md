---
name: code-archaeologist-explorer
description: Create, initialise or replace the Code Archaeologist explorer page (data/explorer.html) for this project -- builds both maps and the review report, then renders the one self-contained, offline HTML page a human opens in a browser. Use only when the user asks for the explorer / explorer.html itself; for questions about the code, use the code-archaeologist skill.
---

# Skill: Code Archaeologist Explorer

One job: leave an up-to-date `data/explorer.html` in the **code-archaeologist** skill folder.
The scripts live in the main skill at `.agents/skills/code-archaeologist`.

## Execution Directive (Zero Overthinking & Low Token Usage)

- **Execution-only mode**: Run the commands step-by-step. Do NOT evaluate or verify data correctness or completeness. The Python scripts handle parsing, extraction, and rendering deterministically.
- **NEVER inspect generated files**: Do NOT open, view, or grep `data/explorer.html`, `graph.json`, `flow_graph.json`, notes, or reports. Trust script stdout completely.
- **NEVER read source code files**: Answering architecture questions is the main skill's job, not this one's.
- **Ignore pending descriptions and warnings**: Do not attempt to fill in descriptions or fix missing grammars. Proceed directly.

## Steps

**1. Source roots.** Fast priority (do not crawl or search the filesystem):
- Roots specified by user in prompt (`/code-archaeologist-explorer ./backend ./frontend`).
- Otherwise, recorded `roots` in `.agents/skills/code-archaeologist/data/cache/manifest.json`.
- Otherwise, `./src` if it exists, else ask the user which folder to map.

**2. Preflight (first build only).** Skip completely if `manifest.json` already exists.
Otherwise check Python 3.10+ and install grammars:
```bash
python --version
python .agents/skills/code-archaeologist/scripts/core/grammars.py --install python typescript   # the repo's languages
```

**3. Build both maps, then the report.**
Execute chained in a single command to save tool roundtrips:
```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src <roots> && python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src <roots>
```
*(Only when user asks to re-render without rebuilding: `python .agents/skills/code-archaeologist/scripts/query/build_html.py`)*

**4. Report back.** Output ONLY this concise summary and stop:
```
Explorer ready: `.agents/skills/code-archaeologist/data/explorer.html`
- Structure: <N> nodes, <E> edges (Grade: <G>)
- Flow: <N> nodes, <E> edges (Grade: <G>)
<Any skipped grammar warnings verbatim from build stdout>
```
Open the file only if the user asks (`start` on Windows, `open` on macOS, `xdg-open` on Linux).
**Do NOT explain views, features, or architecture unless explicitly asked.**

## Reference (Provide only if user asks about page features)
- One self-contained offline HTML file (`file://`).
- Seven views: Flowchart (default), Graph, Treemap, Matrix, Tree, Cluster, Bundle.
- Canvas tools: Blast radius, Freeze view, File tree filter, Reset layout.

