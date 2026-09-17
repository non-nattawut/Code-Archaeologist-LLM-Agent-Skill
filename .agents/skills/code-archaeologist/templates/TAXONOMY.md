# Template field taxonomy

Reference for every `{{placeholder}}` written into a generated page, so values stay
**consistent** across the Python and JS/TS extractors and both maps. The code source of
truth is `scripts/core/taxonomy.py` (do not hand-edit generated pages to values outside these
sets — change the taxonomy instead).

## Structure pages (`data/structure/vault/<Entity>.md`, from `wiki_page_template.md`)

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `{{name}}` | any entity id | Class or component name, or `<Module>Module` for a file's module-level functions. |
| `{{kind}}` | `class`, `interface`, `abstract`, `component`, `module` | What the entity is. `component` is a JS/TS function that returns JSX. A class is `interface` when the source declares one (an interface, trait or protocol, Kotlin `interface`, a Python `Protocol`, a Go `interface` type) and `abstract` when it carries an `abstract` modifier (a Python `ABC` or a class with an `@abstractmethod`). The explorer draws both as a shape: an interface hollow, an abstract class dashed. |
| `{{layer}}` | `controller`, `service`, `repository`, `model`, `client`, `config`, `ui`, `test`, `function`, `module`, `unknown` | Architectural role. An annotation that declares one wins (`@RestController`/`@Controller`/`@ControllerAdvice` → `controller`, `@Service`, `@Repository`/`@Mapper`, `@Entity`/`@Table`/`@Document` → `model`, `@Configuration` → `config`); otherwise inferred from the name and decorators, where `@Component` counts for nothing and `handler` is not a controller word, and a short word must end where the word ends (`repo` does not match `PnoDataReportMail`). When name and annotations say nothing, the **folder** decides, on an exact name only (`service/pnodata/` → `service`, `response/` → `model`, `properties/` → `config`; `taxonomy.PATH_LAYERS`) — a fallback, never an override. A folder that names no layer (`util`, `exception`) leaves the node `unknown`. `test` wins for anything in a test file, and a `component` is always `ui`. |
| `{{lang}}` | `py`, `js`, `java`, `go`, `csharp`, `kotlin`, `rust`, `swift`, `scala`, `groovy`, `dart`, `c`, `cpp`, `ruby`, `php`, `elixir` | Source language. `js` covers `.js/.jsx/.ts/.tsx`. |
| `{{source}}` | `<area>/<path>` | Source file, prefixed with its root area (e.g. `backend/order_service.py`). |
| `{{summary}}` | free text | Docstring / description. |
| `{{bases}}`, `{{decorators}}`, `{{methods}}`, `{{references}}` | lists | `[[wikilinks]]` where the target is a known entity, else inline code. |
| `{{decorators_label}}` | `Decorators`, `Annotations`, `Attributes` | The heading over `{{decorators}}`, in the word the language uses: `Annotations` for Java/Kotlin/Groovy/Scala/Dart, `Attributes` for C#/Rust/Swift/PHP/Elixir, `Decorators` otherwise (`taxonomy.DECORATION_TERMS`). The field itself is one list in every language. |

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
| `ext` | integer | Call sites that did not become an edge (library/stdlib, or unresolvable); the explorer shows `N ext`. |
| `unresolved` | a list of called names (present only when non-empty) | Of those `ext` sites, the ones naming something this graph **does** define — so an edge may be missing here because the receiver's class could not be read. Matched by name, so it over-counts: a library's `get()` looks the same as the graph's. It never becomes an edge; it says where to look. |
| `untyped` | a list of called names (present only when non-empty) | Of those `unresolved` names, the ones dropped because the receiver's type is stated nowhere — an untyped parameter, `a.b.save()`, a Ruby `@store`. What earns `precision: name-matched`. |
| `declaration` | `true` (present only when true) | The node is a signature with no body — a Java interface method, an `abstract` method, a C# interface member. It exists so a call through the declared type has something to resolve to. Because it holds no code, `duplicates.py` skips it and `analyze.py` never reports it as dead code. |
| `entry` | `@<Annotation>`, `override`, `main`, `next:<convention>`, `module`, `init` (present only when set) | Something outside the graph calls this node: a Spring `@Scheduled` / `@Bean` / `@EventListener` / `@PostConstruct` / aspect / listener method, an `@Override` or `override` method (called through its base type), `main`, inside a Next.js app a page, layout, route handler (`next:route`), `generateMetadata` or `getServerSideProps`, or (`module`) a JS/TS or Python module's top-level code as it loads -- or, in JS/TS, hands it to a call there (`createApiInstance(getUserApiBaseUrl)`) (including `if __name__ == "__main__":`), or (`init`) code with no method node of its own: a Java/C# field initializer, initializer block or constructor, a Kotlin property initializer, `init {}` block, secondary constructor or top-level property, a Go package `var` or `func init()`. `analyze.py` never reports it as dead code; no edge is drawn to it. In the **structure** map a class carries it when an annotation says a framework builds it and calls into it (`@SpringBootApplication`, `@Configuration`, `@Aspect`, `@ControllerAdvice`) or one of its own methods carries an `entry`, and a JS/TS module group carries its Next.js convention. `@Component` / `@Service` / `@Repository` alone are not an entry: Spring builds them, but one nothing injects runs nothing. |
| `overridden` | `true` (present only when true) | A method with a body that every subclass in the graph replaces (`overrides` links from each), so the body never runs today. When nothing calls it, `analyze.py` lists it under **overridden**, not as an orphan, and does not grade it: deleting it changes what a new subclass would inherit. |
| `signatures` | list of signature strings | Present only when two definitions still share one id: overloads whose parameter types could not be read apart, or a language without overloading defining a name twice (Rust's two `impl` blocks). Overloads whose types can be read are separate nodes. |
| `ambiguous` | list of overload-set names (`Class.method`) | Present only when a call here names an overload set and no single overload fits the arguments the source states — `render(report, pick())` against `render(Report,int)` and `render(Report,String)`. The call is dropped, not guessed, and the node carries `precision: overloads`. |
| `routes` | list of `{method, path}` | Routes handled by this node (endpoints only). A **list**: one handler often serves several verbs (Flask `methods=["GET", "POST"]`) or carries stacked route decorators. `method` is an HTTP verb, or `ANY` when the framework registers every verb at once (Go's `mux.HandleFunc` without a method in the pattern) — `ANY` matches a frontend call of any verb. |
| `http` | list of `{method, url}` | Frontend HTTP calls, used for cross-stack `http` edges. |

Graph-only link fields (in `flow_graph.json`, on a `calls` link only -- never on `renders`, `passes`,
`http` or an inheritance link):

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `line` | integer | The first line the call is written on, inside its caller's `source`..`end`. The explorer ranks a node's calls by it: the order they are **written** in, never the order they run. Absent only on a link no call site wrote (a JS/TS `new X()`). |
| `loop` | `true` (present only when true) | At least one site of the call is written inside a loop's body, so it may run many times. A loop's iterable or initializer runs once and does not count. |
| `arms` | list of `"<line>:<col>/<arm>"`, outermost first (present only when non-empty, and only with `cond`) | Each **either/or** branch the call is on one side of: the branch's first line and column, and the side, counted in source order (`if` 0, its `else if` 1, its `else` 2; a `match` / `when` / switch arm by position). Two calls on different sides of one branch are alternatives -- exactly one runs -- and the explorer numbers them `3a` / `3b`. Only where the sides exclude each other: a `case X:` switch that can fall through, and a `catch`, give none. A call made on two sides keeps only what every site shares. |
| `cond` | `true` (present only when true) | **Every** site of the call is written inside a branch -- an `if`/`else`, a `switch`/`match` arm, a ternary's result, a `catch` -- so it may not run. A call also made unconditionally has no `cond`. Both flags are a lower bound: `core/call_ctx.py` names the node types it reads, and anything else reports nothing. |

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
| `interface-dispatch` | an outgoing edge lands on a node with `declaration: true` | The call stops at an interface; which implementation runs is not knowable from the source. Emitting a call edge to every implementor would trade precision for recall; each implementor carries an `implements` link to the declaration instead. |
| `overloads` | the node has `ambiguous`, or an outgoing edge lands on a node whose `signatures` has more than one entry | Every overload is its own node, and a call picks one by argument count and the argument types the source states. When that does not settle it, the call is dropped rather than guessed. |
| `name-matched` | the node has `untyped`: it dropped a call through a receiver whose type the source does not state, to a name the graph defines | A link may be missing here. Common in Ruby, PHP, Elixir, Groovy and untyped JS/TS, possible in any language (`a.b.save()` in Java). Until finding #25 it sat on every node of those five languages whether or not anything was dropped; on the sample that was 15 nodes, and it is now 2. |

Order follows `taxonomy.PRECISION_REASONS`, so the field is deterministic (constraint 2).

## Edge `type` (in graph.json / flow_graph.json)

| Value | Meaning |
| --- | --- |
| `references` | structure map: one entity references/imports another. |
| `calls` | flow map: one method/function calls another. |
| `http` | flow map: a frontend `fetch`/`axios` call linked to a backend route handler. |
| `renders` | flow map: a component's JSX renders another (`<Dashboard />`), resolved like a call. Followed by traces and `--impact-of`; not a call, so it is not counted as coupling and never appears as "Delegates to". |
| `passes` | flow map: a JS/TS function hands another to code that calls it -- a call argument (`rows.map(formatDate)`), a value in an argument's object (`t.rich(key, { b: tag })`) or a JSX attribute (`onClick={run}`) -- when the name resolves through an import or to a module function of the same file, and never when it is a parameter or local there. Followed by traces and `--impact-of` and counted as a use by orphans; not a call, so not coupling, `precision` or "Delegates to". Never drawn where a `calls` or `renders` link already joins the two. |
| `implements` | flow map: a method linked to the same-named method its class's base (interface, abstract or parent class in the graph) defines -- directly, or past a base that defines none; overloads pair by parameter types. Stored implementation -> declaration (`FlatRate.price -> PricingRule.price`) and walked declaration -> implementation by traces, `--impact-of`, orphans, `search.py`, `context.py` and the explorer (`taxonomy.call_direction`). Not a call: never coupling, a cycle, a layer violation, `precision` or "Delegates to". It says which classes can run a call, never which one does. Only into a **declaration** (a signature with no body, or a Python `@abstractmethod`); replacing a body is `overrides`. In the structure map it is a class's stated base that is an interface (`FlatRate -> PricingRule`), walked the same way, so a class implementing a referenced interface is not an orphan. |
| `extends` | structure map: a class's stated base that is a class or abstract class, or an interface's base interface (`AasHandler -> MasterAASDataUploadHandler`). Walked backwards like `implements`; not a reference for coupling, cycles or layers. |
| `overrides` | flow map: a method that replaces a same-named method with a body in its class's base (`AasHandler.saveDetails -> BaseHandler.saveDetails`). Stored and walked exactly like `implements`. When every subclass overrides a method, that method is `overridden`. |

## Review pass (`data/report/`, from `report.py`)

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `severity` | `high`, `medium`, `low` | Risk-scan finding severity (`scan_security.py`). |
| `rule` | `hardcoded_secret`, `sql_injection`, `dangerous_eval`, `debug_statement` | Which scan rule fired. |
| `node` | node id or `null` | The graph node owning the flagged line (`null` = module level). |
| `grade` | `A`, `B`, `C`, `D`, `F` | Health grade for the 0-100 score (`analyze.py`). |
| `reason` (god objects) | `methods`, `references` | Why the entity was flagged. |
| coupling sections | `hubs`, `shared_helpers`, `coordinators`, `wrong_way_deps` | The four shapes a single degree count used to fold into one. Only `hubs` and `wrong_way_deps` are **graded**; the other two are reported so they stay visible and cost nothing. |
| `fan_in` / `fan_out` | integers | Callers and callees over `app_edges()` — test, `renders`, `passes` and `implements` links excluded. |
| `instability` | `0.00`-`1.00` | Martin's `I = fan_out / (fan_in + fan_out)`. `0` = everything depends on it and it depends on nothing (a shared helper); `1` = it depends on everything and nothing depends on it (a coordinator). An isolated node is `0.0` — it has no direction to measure. |
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
