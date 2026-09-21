# metrics.py — Size & Complexity Review Engine

`scripts/review/metrics.py` is the size and complexity review pass of **Code Archaeologist**. It measures code volume, comment density, and cognitive complexity across the entire codebase, correlating AST-level measurements directly to graph node IDs (e.g. `OrderService.place_order`).

---

## 1. Summary of Everything `metrics.py` Does

### Category 1: Per-Node Metrics (AST Level — Functions / Methods / Classes)
Attached directly to each node ID in `flow_graph.json` or `graph.json`:

1. **`loc` (Lines of Code)**: The physical line span of the function, method, or class body (`end_line - start_line + 1`), starting from the first decorator/annotation or declaration line.
2. **`complexity` (McCabe Cyclomatic Complexity)**:
   - Base = `1`.
   - `+1` for every decision branch (`if`, `elif`, `for`, `foreach`, `while`, `do..while`, `catch`/`rescue`, `case`/`when`, `ternary`, `assert`, list comprehension `if` clauses).
   - `+1` for short-circuit boolean operators (`&&`, `||`, `and`, `or`, `??`).
   - `0` for fallback arms (`default:`, `_ =>`, `else ->`, `true ->`).
3. **`depth` (Max Nesting Depth)**: The deepest control-flow block nesting level inside the function (e.g., an `if` inside a `for` inside a `while` = depth 3; flat function body = 0).
4. **`params` (Parameter Count)**: Formal parameter/argument count, with grammar-aware handling (unpacks Go grouped types `a, b int`, ignores C `f(void)`, includes Python `self`).
5. **Node Location Metadata**: Records `file`, `line`, and `lang` for exact navigation.

---

### Category 2: Per-File Metrics (Physical File Level)
Measured for every individual source file discovered by `scan_security.iter_source_files`:

6. **`lines`**: Total line count of the file.
7. **`code`**: Executable code lines (`total - comment - blank`).
8. **`comment`**: Comment lines (lines starting with `#`, `//`, `/*`, or `*`). Note: Python docstrings count as executable code lines, not comments.
9. **`blank`**: Empty or whitespace-only lines.
10. **`lang`**: Source language of the file (via `taxonomy.lang_of` extension mapping).

---

### Category 3: Project-Wide Census & Totals
Global aggregate metrics for the entire repository:

11. **Total Files**: Count of all scanned source files.
12. **Total Lines / Code / Comment / Blank**: Aggregate codebase volume.
13. **`comment_ratio`**: Proportion of comments to total lines (`total_comments / total_lines`).
14. **Language Breakdown (`languages`)**: File count and total lines per programming language (e.g., `python: 30 files / 8,500 lines`, `typescript: 15 files / 4,340 lines`).

---

### Category 4: Leaderboard Rankings (Top-N Hotspots)
Surfaces the largest cognitive hotspots:

15. **`top_loc`**: Top 10 longest functions/methods in the codebase.
16. **`top_complexity`**: Top 10 most branched/complex functions by McCabe cyclomatic complexity.
17. **`top_files`**: Top 10 largest files by total line count.

---

### Category 5: Gap & Coverage Tracking
18. **`unmeasured_graph_ids`**: Lists every graph node that has **no body to measure** (e.g. abstract interface declarations, module groups, stubs, or nodes outside the scanned root).
19. **Missing Grammar Detection Trigger**: Provides the raw language inventory used by `brief.py` to warn if a language is present in source files but missing its tree-sitter parser wheel.
20. **Payload Generation**: Serializes the data into `data/report/metrics.json` to feed `report.py`, `context.py`, and `explorer.html`.

---

## 2. Downstream Consumption

While `metrics.py` does not penalize or deduct points from the Architecture Health Score (leaving smell grading to `analyze.py`), its data is actively consumed by:

- **`context.py` (Zero-RAG Node Context)**: When an LLM agent inspects a node via `python context.py <node_id>`, the node's exact `loc`, `complexity`, and `depth` are injected into the prompt. The agent knows immediately if a function is a 200-line complex monster without reading raw source code.
- **`brief.py` (Grammar Verification)**: Compares detected source languages against installed tree-sitter wheels to alert about missing parsers.
- **`report.py` & `explorer.html` (Universal Census)**: Powers the file census dashboard, language breakdown charts, and top complexity tables.
