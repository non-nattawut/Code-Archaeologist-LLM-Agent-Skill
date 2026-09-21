# debt.py — Technical Debt, Markers & Dead Code Analysis

`scripts/review/debt.py` provides a deterministic inventory of code rot across the codebase. It combines two complementary signals into a single actionable cleanup report without requiring developers or AI agents to read raw source files:

1. **Explicit Debt (Markers)**: Developer-left breadcrumbs (`TODO`, `FIXME`, `HACK`, `BUG`, etc.).
2. **Implicit Debt (Dead Code)**: Zombie functions, orphan classes, and **entirely dead files** that nothing in the graph calls.

---

## 1. Explicit Debt: Comment Markers (`find_markers`)

`debt.py` scans for developer annotations left in comments, but applies strict filtering to prevent false positives and links each marker directly to an AST graph node.

### Supported Tags
```python
TAGS = ("TODO", "FIXME", "HACK", "XXX", "BUG", "DEPRECATED")
```

### False-Positive Suppression (`_comment_part`)
A naive regex over whole lines would incorrectly flag variables like `todo_count = 5` or string literals like `"TODO in a string"`. 

`debt.py` extracts only the comment portion of a line:
- Looks for `#`, `//`, `/*`, or leading `*` in multi-line comment blocks.
- Strips trailing comment closes (`*/`).
- Matches markers that begin docstrings or comments.
- Ignores code lines that contain these words inside strings or identifier names.

### AST Node Attribution
Instead of merely returning a file and line number, `debt.py` calls `scan_security.owner_of(index, file, line)`:
- Maps the line number against the AST ranges of graph nodes.
- Attributes the marker to its enclosing function or class (e.g. `[OrderService.checkout]`).

---

## 2. Implicit Debt: Dead Code Detection (`find_dead`)

Dead code is detected by analyzing the **graph topology** (`flow_graph.json` / `graph.json`) via `analyze.find_orphans()` and aggregating results by file.

### Why Checking `fan_in == 0` Alone Fails
At its simplest mathematical level, an orphan has no incoming callers (`fan_in == 0`). However, if an engine *only* checked for `fan_in == 0`, large portions of a healthy codebase would be falsely reported as dead:
- **API Controllers**: Called by external HTTP clients outside the graph.
- **Scheduled Tasks**: Invoked by framework timers (e.g. `@Scheduled`).
- **React/Vue Components**: Mounted dynamically by the frontend framework.
- **CLI Entrypoints & Runtime Hooks**: Called by the OS (`main()`, Go `func init()`, Python `__init__`).
- **Interface Implementations**: Callers link to the interface declaration (`PaymentGateway.charge`), so the concrete implementation (`StripeGateway.charge`) has zero direct call edges.

---

## 3. The Dead Code Algorithm

The engine determines dead code through a multi-stage qualification process:

### Stage 1: Build the "Called / Reachable" Set (`has_caller`)
1. **Direct Calls**: Every edge `caller -> callee` marks `callee` as called.
2. **Interface Implementations (`implements`)**: Walked in reverse via `taxonomy.call_direction`. A call to an interface declaration propagates reachability to all concrete methods that implement it.
3. **Inherited Base Classes (`extends`)**: If class `Order` extends `AuditableEntity`, the base class is recognized as actively used in the codebase.
4. **Ambiguous Overloads**: Calls where argument types could not differentiate between overloaded methods record all candidate methods in `node.ambiguous`, protecting them all from being marked dead.

### Stage 2: Filter Out Legitimate Entry Points
A node with 0 incoming callers is **excluded** from dead code if it matches any of the following:
- **`kind in ("endpoint", "component")`**: HTTP endpoints and frontend UI components.
- **`layer in ("controller", "test")`**: Web controllers and unit/integration test suites.
- **`bool(node.get("routes"))`**: Nodes mapped to routing tables.
- **`bool(node.get("entry"))`**: Framework entries (`@Scheduled`, `@Bean`, `next:page`, `next:route`, `init`).
- **`bool(node.get("declaration"))`**: Abstract signatures without a body (interfaces/protocols).
- **`_is_dunder(name)`**: Implicit runtime methods like `__init__`, `__str__`.
- **`bool(node.get("overridden"))`**: Base methods overridden by every subclass (reported in a separate design section, not graded as dead rot).

### The Real Dead Node Formula

$$\text{Dead Node} = (\mathbf{fan\_in == 0}) \ \mathbf{AND}\ (\mathbf{NOT\ an\ entrypoint})\ \mathbf{AND}\ (\mathbf{NOT\ reachable\ via\ inheritance})$$

---

## 4. Dead Files: The Highest Confidence Signal

A single orphan method might just be a utility function or invoked via reflection. But an entire file where **every single method and class is dead** is almost certainly an abandoned module, forgotten prototype, or obsolete feature.

`debt.py` groups all nodes by source file:

```python
by_file: dict[str, list[str]] = {}
for nid, n in nodes.items():
    file_path = (n.get("source") or "").split(":")[0]
    by_file.setdefault(file_path, []).append(nid)

dead_files = sorted(f for f, ids in by_file.items()
                    if f and ids and all(i in orphans for i in ids))
```

If a file defines 6 methods and all 6 are dead, the entire file is flagged in `dead_files`, signaling a safe candidate for complete file deletion.

---

## 5. Output Payload Schema (`debt.json`)

Saved in `data/report/debt.json` (or `data/report/{flow,structure}/debt.json`):

```json
{
  "roots": ["src"],
  "graph": "flow_graph.json",
  "summary": {
    "markers": 14,
    "by_tag": {
      "TODO": 8,
      "FIXME": 4,
      "HACK": 2
    },
    "dead_nodes": 5,
    "dead_files": 1
  },
  "markers": [
    {
      "tag": "FIXME",
      "text": "retry logic fails on timeout",
      "file": "src/services/billing.py",
      "line": 84,
      "node": "BillingService.charge"
    }
  ],
  "dead_nodes": [
    {
      "id": "LegacyExporter.to_csv",
      "source": "src/utils/legacy_exporter.py:12",
      "layer": "service",
      "kind": "method"
    }
  ],
  "dead_files": [
    "src/utils/legacy_exporter.py"
  ]
}
```

---

## 6. Downstream Consumption

- **Architecture Report (`report.py`)**: Lists markers, dead nodes, and dead files in the cleanup section of `architecture_report.md`.
- **Health Grade Impact (`analyze.py`)**: Dead code directly penalizes the codebase architecture health score (up to -20 points).
- **Explorer UI (`explorer.html`)**: Visually distinguishes dead nodes and surfaces marker counts in the project dashboard.
