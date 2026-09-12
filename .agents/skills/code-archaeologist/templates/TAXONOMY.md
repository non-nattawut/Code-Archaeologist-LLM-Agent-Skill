# Template field taxonomy

Reference for every `{{placeholder}}` written into a generated page, so values stay
**consistent** across the Python and JS/TS extractors and both maps. The code source of
truth is `scripts/core/taxonomy.py` (do not hand-edit generated pages to values outside these
sets — change the taxonomy instead).

## Structure pages (`data/structure/vault/<Entity>.md`, from `wiki_page_template.md`)

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `{{name}}` | any entity id | Class or component name, or `<Module>Module` for a file's module-level functions. |
| `{{kind}}` | `class`, `component`, `module` | What the entity is. `component` is a JS/TS function that returns JSX. |
| `{{layer}}` | `controller`, `service`, `repository`, `model`, `client`, `config`, `ui`, `test`, `function`, `module`, `unknown` | Architectural role (inferred from name/decorators; `test` wins for anything in a test file, and a `component` is always `ui`). |
| `{{lang}}` | `py`, `js`, `java`, `go`, `csharp`, `kotlin`, `rust`, `swift`, `scala`, `groovy`, `dart`, `c`, `cpp`, `ruby`, `php`, `elixir` | Source language. `js` covers `.js/.jsx/.ts/.tsx`. |
| `{{source}}` | `<area>/<path>` | Source file, prefixed with its root area (e.g. `backend/order_service.py`). |
| `{{summary}}` | free text | Docstring / description. |
| `{{bases}}`, `{{decorators}}`, `{{methods}}`, `{{references}}` | lists | `[[wikilinks]]` where the target is a known entity, else inline code. |

## Flow pages (`data/flow/notes/<Class.method>.md`, from `build_flow.py`)

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `entity` | `Class.method` or `function` | The method/function node id. An overloaded method's id carries its parameter types — `InvoiceService.Total(int,int)` — so every overload is its own node. |
| `kind` | `method`, `function`, `endpoint`, `component`, `test` | `endpoint` = a route handler (flow root); `component` = a function that returns JSX. Both are entry points: something outside the graph calls them, so neither counts as dead code. |
| `layer` | same set as above | Role of the owning class/file. |
| `lang` | same set as `{{lang}}` above | Source language. |
| `precision` | a list of `interface-dispatch`, `overloads`, `name-matched` (present only when non-empty) | **Named** precision losses for this node's outgoing edges. Absent means nothing *nameable* was lost — never that the edges are complete. See *Precision* below. |
| `declaration` | `true` (present only when true) | A signature with no body (interface member, `abstract` method). Its **Calls** section is always empty because there is no body to call from — that says nothing about whether the implementations are used. |
| `desc_source` | `docstring`, `ai`, `auto` | Where "What it does" came from (see hybrid descriptions). |
| `class` | class name | Owning class (absent for module-level functions). |
| `source` | `<area>/<path>:<line>` | Location: the declaration's **first** line, decorators, annotations and attributes included, in every language — so the range `source`..`end` covers everything the node owns. |

Graph-only node fields (in `flow_graph.json`, not written into the pages):

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `ext` | integer | Call sites that leave the graph (library/stdlib); the explorer shows `N ext`. |
| `declaration` | `true` (present only when true) | The node is a signature with no body — a Java interface method, an `abstract` method, a C# interface member. It exists so a call through the declared type has something to resolve to. Because it holds no code, `duplicates.py` skips it and `analyze.py` never reports it as dead code. |
| `signatures` | list of signature strings | Present only when two definitions still share one id: overloads whose parameter types could not be read apart, or a language without overloading defining a name twice (Rust's two `impl` blocks). Overloads whose types can be read are separate nodes. |
| `ambiguous` | list of overload-set names (`Class.method`) | Present only when a call here names an overload set and no single overload fits the arguments the source states — `render(report, pick())` against `render(Report,int)` and `render(Report,String)`. The call is dropped, not guessed, and the node carries `precision: overloads`. |
| `routes` | list of `{method, path}` | Routes handled by this node (endpoints only). A **list**: one handler often serves several verbs (Flask `methods=["GET", "POST"]`) or carries stacked route decorators. `method` is an HTTP verb, or `ANY` when the framework registers every verb at once (Go's `mux.HandleFunc` without a method in the pattern) — `ANY` matches a frontend call of any verb. |
| `http` | list of `{method, url}` | Frontend HTTP calls, used for cross-stack `http` edges. |

## Precision

**Every language's call edges are a lower bound.** A call is drawn only when the receiver's type
can be read from the source; anything else is dropped rather than guessed, because a wrong edge is
worse than a missing one. That is stated once — in `brief`, in the report header, and in
`taxonomy.PRECISION_CAVEAT` — and it applies to every node in both maps.

It used to be a per-node `approx: true` on Java, Go and C#. That was honest while those three were
read textually, and became arbitrary once every language moved to tree-sitter: Python and JS/TS
resolve no more completely, they simply had no marker.

What survives per node is narrower and more useful — the losses that can be *named*. Each is
derived from what is already in the graph, never from the language alone:

| `precision` value | Set when | Why it matters |
| --- | --- | --- |
| `interface-dispatch` | an outgoing edge lands on a node with `declaration: true` | The call stops at an interface; which implementation runs is not knowable from the source. Emitting an edge to every implementor would trade precision for recall. |
| `overloads` | the node has `ambiguous`, or an outgoing edge lands on a node whose `signatures` has more than one entry | Every overload is its own node, and a call picks one by argument count and the argument types the source states. When that does not settle it, the call is dropped rather than guessed. |
| `name-matched` | the node's `lang` is `js`, `ts`, `jsx`, `tsx`, `ruby`, `php`, `elixir` or `groovy` | These languages' source usually names no receiver type, so a call through an object is dropped unless its class is written down (a `new X()`, a `this`, a PHP typed property, a Groovy typed field, an Elixir module name). Measured: the Ruby fixture drops `@store.save` while keeping the same-class `validate` call; the TypeScript fixture, which states every class, resolves **3 of 3**. |

Order follows `taxonomy.PRECISION_REASONS`, so the field is deterministic (constraint 2).

## Edge `type` (in graph.json / flow_graph.json)

| Value | Meaning |
| --- | --- |
| `references` | structure map: one entity references/imports another. |
| `calls` | flow map: one method/function calls another. |
| `http` | flow map: a frontend `fetch`/`axios` call linked to a backend route handler. |

## Review pass (`data/report/`, from `report.py`)

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `severity` | `high`, `medium`, `low` | Risk-scan finding severity (`scan_security.py`). |
| `rule` | `hardcoded_secret`, `sql_injection`, `dangerous_eval`, `debug_statement` | Which scan rule fired. |
| `node` | node id or `null` | The graph node owning the flagged line (`null` = module level). |
| `grade` | `A`, `B`, `C`, `D`, `F` | Health grade for the 0-100 score (`analyze.py`). |
| `reason` (god objects) | `methods`, `references` | Why the entity was flagged. |
| idiom keys | `singleton`, `factory`, `observer`, `react_hook` | Name-based pattern detection. |

## Test code

`taxonomy.py` also owns what counts as a test, because "is this a test?" has to mean the same
thing in every pass. Detection is by convention, so it holds for languages this skill cannot
build a graph for:

| Signal | Examples |
| --- | --- |
| directory | `test/`, `tests/`, `__tests__/`, `spec/`, `specs/`, `testing/` |
| filename (lowercase) | `test_orders.py`, `conftest.py`, `orders_test.go`, `order_spec.rb`, `order.test.tsx`, `order.spec.ts`, `OrderTest.php` |
| filename (Java-style, case-sensitive) | `OrderServiceTest.java`, `FooTests.kt`, `PaymentIT.java`, `BazSpec.scala`, `QuxTests.cs`, `AppTests.swift` |
| content marker | `@Test` / `@SpringBootTest` / `@ParameterizedTest` (JUnit 5, Spring Boot), `[Fact]` / `[TestMethod]` (.NET), `#[test]` (Rust), `func TestX(t *testing.T)` (Go), `unittest.TestCase` / `import pytest` |

Consequences, all from that one definition: nodes in test files get `layer: test`; `analyze.py`
does **not** count them as dead code (a runner calls them, so the graph never will) and drops
test edges from the hub / god-object degree counts (`app_edges`), so a well-tested function does
not read as highly coupled; `scan_security.py` skips them (their "secrets" are fixtures);
`tests_map.py` treats them as the test suite rather than as application code; `context.py` lists
them under **Covered by**; the explorer can hide them with its **Tests** toggle. Markers
(`debt.py`) are still collected there — a TODO in a test is still a TODO.

`kind` and `layer` come from `taxonomy.py` (`KINDS`, `LAYERS`, `LAYER_RULES`). Add a new value
there once, and every extractor and template stays consistent. Scan rules and grade cutoffs live
in `scan_security.py` (`RULES`) and `analyze.py` (`GRADES`, thresholds).
