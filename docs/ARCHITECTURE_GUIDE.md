# Code Archaeologist — Complete Architecture & Workflow Guide

A deterministic, Zero-RAG codebase documentation engine that builds two queryable maps of a target codebase (Structure & Flow), audits them with graph algorithms, and renders a self-contained offline viewer.

---

## 1. Visual Pipeline Architecture & Data Flow

```
archaeologist.py  project | flow | both | check | report | brief   (Entrypoint)
  project  -> build_wiki -> build_graph ------------------\
  flow     -> build_flow ---------------------------------+--> render_explorer()
      both extract through: py_extract.py     (Python,        tree-sitter)
                            js_ts_extract.py  (JS/TS/JSX/TSX, tree-sitter)
                            langs_extract.py  (15 languages,  tree-sitter)
            flow also reads: route_tables.py   (Django/Rails/Laravel/Phoenix tables -> handlers)
  report   -> report.py (scan_security + git_insights + analyze + metrics + debt + tests_map
                         + duplicates)
                                                                    -> data/report/<map>/
  brief    -> brief.py (reads computed JSON artifacts, zero computation)
  check    -> manifest.py (source hashes vs last build; detects staleness)
                                                            \-> build_html.py -> data/explorer.html
```

---

## 2. Practical Operational Scenarios

### Scenario 1: Codebase Ingestion & Graph Building
Scans target source roots, parses every file via Tree-sitter, resolves calls against declared receiver types, and writes deterministic graph JSONs and Markdown notes.

```bash
# Build both structure and flow maps
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./sample_src
```

**Key Artifacts:**
- `data/structure/graph.json` & `vault/*.md` — Classes, React components, and module groups.
- `data/flow/flow_graph.json` & `notes/*.md` — Methods, functions, and cross-stack HTTP call edges.
- `data/explorer.html` — Standalone offline viewer.

### Scenario 2: Zero-RAG Architecture Query & Blast Radius
AI agents answer architecture and impact questions by querying the graph using BFS and reading only the returned notes, avoiding multi-hundred-thousand token source dumps.

```bash
# Trace execution path between components
python .agents/skills/code-archaeologist/scripts/query/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json \
  --from submitOrder --to OrderRepository.save

# Blast radius: all upstream callers affected by modifying a node
python .agents/skills/code-archaeologist/scripts/query/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json \
  --impact-of OrderRepository.save
```

### Scenario 3: Code Health & Risk Audit
Runs 7 analysis passes to compute an A–F health grade, detect circular dependencies, locate copy-pasted blocks, and rank git churn hotspots.

```bash
# Generate architecture reports
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./sample_src

# Orientation brief (fixed token size digest)
python .agents/skills/code-archaeologist/scripts/archaeologist.py brief
```

---

## 3. Directory of All 28 Scripts: Mechanics & Algorithms

### Core & Bootstrapping

| Script | Role | Technique / Algorithm | Key Invariant |
| :--- | :--- | :--- | :--- |
| `scripts/archaeologist.py` | CLI Dispatcher | Subcommand routing (`project`, `flow`, `both`, `check`, `report`, `brief`). | Single entrypoint at `scripts/` root. |
| `scripts/paths.py` | System Paths | MAX_PATH normalization (`\\?\` prefix) and `sys.path` bootstrap. | Sits below categories; imports nothing from skill. |
| `scripts/core/ids.py` | ID Generation | **SharedNames:** Groups by `name.lower()` to prevent case collisions on Windows/macOS. Qualifies by stem/path. | Node IDs stay bare unless defined in 2+ files. |
| `scripts/core/taxonomy.py` | Taxonomy Rules | Defines kinds, layers, skip directories, and `is_test_file()` detection. Computes `precision_of()`. | Single source of truth; never re-implemented inline. |
| `scripts/core/grammars.py` | Grammar Wheels | Manages pinned Tree-sitter wheels, lazy loading, and `drift()` detection. | Wheels installed on demand into `<skill>/vendor/`. |
| `scripts/core/manifest.py` | Staleness Check | Computes SHA-256 source and grammar version hashes into `manifest.json`. | Deterministic: no wall-clock timestamps. |
| `scripts/core/console.py` | Output Encoding | Safe stdout/stderr wrapper protecting non-UTF-8 terminals (e.g. Windows cp874). | Must be called before echoing external repo strings. |

### Extraction Engine (Why 3 Extractor Files?)

The extractors are kept in **three separate files** rather than one monolithic module because the file boundary is the **graceful degradation boundary** required by Constraint 1:
- `py_extract.py` (Python CST + newline normalization) — degrades via `python skipped`.
- `js_ts_extract.py` (JS/TS/JSX/TSX) — degrades via `frontend skipped` (needs both `javascript` and `typescript` grammars).
- `langs_extract.py` (15 languages: Java, Go, C#, Rust, Kotlin, etc.) — degrades on a per-language basis.

| Script | Role | Technique / Algorithm | Key Invariant |
| :--- | :--- | :--- | :--- |
| `scripts/extract/build_wiki.py` | Structure Wiki | Extracts classes, JSX components, and module-level functions into Markdown notes. | JSX functions become `kind: component` / `layer: ui`. |
| `scripts/extract/build_graph.py` | Structure Graph | Assembles `graph.json` from vault notes and type references. | Edges are references; carry no precision. |
| `scripts/extract/build_flow.py` | Flow Graph | Two-pass caller resolution, overload picking (`_pick_overload`), cross-stack linking, and **`unresolved` dropped-call tracking** (`_record_dropped`, `_split_dropped`). | Lower bound: calls resolved only through declared types. Interface calls stop at `declaration: true`. Dropped calls matching known graph nodes are tracked in `unresolved` (never guessed as edges). |
| `scripts/extract/py_extract.py` | Python CST | Tree-sitter CST queries + newline normalization (`read_source()`). | Validated against stdlib `ast` via `check_py_oracle.py`. |
| `scripts/extract/js_ts_extract.py` | JS/TS CST | Multi-grammar parsing (`javascript`, `typescript`, `tsx`), routes, axios/fetch calls. | Emits `{type, name}` calls for typed receivers (`new X()`, `this.<field>`, typed params). |
| `scripts/extract/langs_extract.py` | 15 Lang Extractor | Table-driven CST extraction via `SPEC` and `SHAPES` tables; handles `OVERLOADING`. | Range starts at first annotation/decorator (`source..end`). |
| `scripts/extract/route_tables.py` | Route Tables | Parses external routing tables (Django `urlpatterns`, Rails `routes.rb`, Laravel, Phoenix). | Dropped if route matches 0 or >1 target handler. |
| `scripts/extract/apply_descriptions.py` | Descriptions | Waterfall: 1. Docstring, 2. Hash-cached AI summary (`descriptions.json`), 3. Fallback. | Sole entrypoint for AI text; deterministic at runtime. |

### Review & Code Health

| Script | Role | Technique / Algorithm | Key Invariant |
| :--- | :--- | :--- | :--- |
| `scripts/review/analyze.py` | Health & Smells | **Iterative Tarjan's SCC** for cycles, degree coupling, god objects, capped health score. | Coupling runs on `app_edges()` (excludes `layer: test`). |
| `scripts/review/duplicates.py` | Code Clones | **1. Token Normalization** (ID/LIT) for whole bodies.<br>**2. Winnowing ($K=10, W=21$)** with rolling polynomial hash for blocks. | Deterministic rolling hash mod $(2^{61}-1)$. Skips declarations. |
| `scripts/review/scan_security.py` | Vulnerability Scan | Line-oriented regex scanning mapped to innermost node range via `owner_of()`. | Module-level findings attributed to file, never preceding function. |
| `scripts/review/git_insights.py` | Churn & Risk | Streaming `git log --numstat` parser. Computes $\text{risk} = \text{commits} \times (1 + \text{fan\_in} + \text{fan\_out})$. | Single git subprocess call; degrades gracefully if not git repo. |
| `scripts/review/metrics.py` | Complexity | CST decision-point counter per language table (McCabe cyclomatic complexity & depth). | Keyed by graph node ID by construction across all languages. |
| `scripts/review/debt.py` | Debt Markers | Heuristic comment scanner for TODO/FIXME/HACK + orphan file detection. | Review prompt only; does not penalize health score. |
| `scripts/review/tests_map.py` | Test Mapping | Scans test files to map tests to production node names. | Coverage indicator; test nodes tagged `layer: test`. |
| `scripts/review/report.py` | Report Generator | Aggregates all review passes into markdown and JSON architecture reports. | One report per map; node IDs are never mixed. |
| `scripts/review/brief.py` | Orientation Brief | Zero-computation digest reading existing JSON artifacts. | Fixed-size output; identical token cost on small and large repos. |

### Query & Visualization

| Script | Role | Technique / Algorithm | Key Invariant |
| :--- | :--- | :--- | :--- |
| `scripts/query/trace_path.py` | Path Tracing | **Forward BFS** for shortest path (`--from/--to`), **Reverse BFS** for blast radius (`--impact-of`). | Pure stdlib (no NetworkX); deterministic ordering. |
| `scripts/query/search.py` | Node Search | Indexed multi-filter query (`--name`, `--doc`, `--layer`, `--calls`, etc.). | Replaces grepping source files to find node IDs. |
| `scripts/query/context.py` | Context Pack | Packs node facts, callers, callees, metrics, and security into a strict `--max-chars` budget. | Trims under budget; includes precision caveats. |
| `scripts/query/build_html.py` | HTML Bundler | Inlines graph JSONs, CSS, and vendored `force-graph.js` into single `data/explorer.html`. | Zero network calls; opens directly via `file://`. |
| `templates/viewer.html` | Frontend UI | Responsive 3-pane desktop app; 7 visualization views; D3 force-graph physics. | Quiet chrome (`#08090b`), test nodes green (`#57ab5a`), no emojis. |

---

## 4. Key Architectural Invariants

1. **Deterministic Byte-for-Byte Output:** Given the same source files, every generated graph, note, and report produces identical bytes across runs. No wall-clock timestamps or process-salted hashes.
2. **Lower-Bound Call Precision:** Call edges are drawn only when the receiver's type is declared in the source. Ambiguous or dynamic dispatch is dropped rather than guessed, and named in `precision`.
3. **Standalone Offline Explorer:** The HTML viewer inlines all data and JavaScript libraries, ensuring full functionality with network access completely disabled.
4. **Windows & CP874 Console Safety:** Standard output is guarded by encoding-safe wrappers, preventing crashes from unprintable characters or non-UTF-8 Windows consoles.
5. **Dropped Calls Keep Their Names (`unresolved`):** Dropped calls are split into true external calls (`ext`) vs calls naming entities that exist in the graph (`unresolved`). The system records them as investigation clues without guessing or inventing false edges (guarded by `check_graph.py` rule `c19` and regression test `r35`).
