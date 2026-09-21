# tests_map.py — Test Coverage & Reference Mapping

`scripts/review/tests_map.py` maps test files to production graph nodes **statically (Zero-Instrumentation)**. It does not run test suites, execute bytecode, or require language-specific coverage tools (like pytest-cov, JaCoCo, or Istanbul).

Instead, it answers the fundamental architecture question: **"Which functions and classes does the test suite even talk about, and which are completely unreferenced?"**

---

## 1. Test File Discovery (`taxonomy.is_test_file`)

`tests_map.py` scans source files under `--src` and classifies test files using two criteria:

1. **Path & Filename Conventions:**
   - Folders: `test/`, `tests/`, `__tests__/`, `spec/`
   - Filenames: `test_*.py`, `*_test.go`, `*.test.ts`, `*.spec.js`, `*Test.java`, `*Tests.cs`
2. **Framework Annotations & Declarations:**
   - `@Test`, `@SpringBootTest`, `[Fact]`, `#[test]`, `func TestX(t *testing.T)`

---

## 2. Token Extraction via Regex (`identifiers`)

Instead of parsing test files with tree-sitter, `tests_map.py` uses a single fast regular expression:

```python
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

def identifiers(full: str) -> set[str]:
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            return set(IDENT_RE.findall(fh.read()))
    except OSError:
        return set()
```

### Why Regex instead of Tree-Sitter for Test Files?
If `tests_map.py` parsed test files with tree-sitter looking strictly for AST function call expressions (`obj.method()`), it would fail to detect modern testing patterns:
- **Mocking & Spies:** `@patch.object(OrderService, "checkout")`, `jest.spyOn(OrderService, 'checkout')`.
- **BDD & Reflection:** Tests passing method names as string arguments, reflection handles, or data provider tables.
- **Performance:** A single regex scan extracts all tokens into a Python `set` in milliseconds, making subsequent membership checks instantaneous $O(1)$ operations.

---

## 3. Matching Graph Nodes Against Test Identifiers

Production nodes are loaded from `flow_graph.json` or `graph.json` (which **were** extracted and structured via tree-sitter).

### Exclusions
- **Dunder Methods**: (`__init__`, `__str__`, etc.) are skipped because they are invoked implicitly by runtimes.
- **Test-layer Nodes**: Nodes located within test files themselves are skipped.

### Matching Rules
For each node in the graph:
1. **Class Methods (`cls` is present, e.g. `OrderService.checkout`):**
   **BOTH** the method name (`checkout`) **AND** the class name (`OrderService`) must be present in the same test file.
   ```python
   hits = [f for f, ids in tests.items() if name in ids and cls in ids]
   ```
   *(This prevents a test for `PaymentService.checkout` from falsely counting as a test for `OrderService.checkout`.)*
2. **Standalone Functions & Classes (`cls` is absent):**
   Only the name of the function or class must be present in the test file (`name in ids`).

---

## 4. Output Partition: `referenced` vs `unreferenced`

- **`referenced[node_id]`**: Lists all test files that mention this method or class.
- **`unreferenced`**: All production graph nodes that are **never named in any test file** across the entire project.

```json
{
  "roots": ["src"],
  "summary": {
    "test_files": 12,
    "considered": 85,
    "referenced": 68,
    "unreferenced": 17,
    "referenced_pct": 80.0
  },
  "referenced": {
    "OrderService.checkout": ["tests/test_orders.py", "tests/integration/test_checkout.py"]
  },
  "unreferenced": [
    { "id": "LegacyExporter.export", "source": "src/utils/legacy.py:10", "layer": "service" }
  ]
}
```

---

## 5. Confidence & Guarantees

- **Referenced $\ne$ Fully Covered:** A node mentioned in a test file might only be imported or mocked.
- **Unreferenced $=$ Definite Test Gap:** An unreferenced node is guaranteed to have **zero direct tests**—the test suite does not even know its name. This gives developers and agents an instant, zero-config map of untested production code.
