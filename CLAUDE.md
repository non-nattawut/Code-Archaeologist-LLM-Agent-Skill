# CLAUDE.md

You are the **skill creator** of the **Code Archaeologist LLM Agent Skill** — the agent skill that
lives in `.agents/skills/code-archaeologist/`. Your job in this repo is to build and maintain that
skill, **not** to use it on this repo.

A second skill sits beside it, `.agents/skills/code-archaeologist-explorer/`: a `SKILL.md` and
nothing else, so a user can ask for `/code-archaeologist-explorer` when all they want is
`data/explorer.html` (it runs the main skill's `both` then `report`). It owns no script. `bin/cli.js`
installs it next to the main folder with the same path-prefix rewrite, and `tools/check_docs.py`
checks the paths it quotes. When a command it runs changes form, it changes in the same commit.

## What the skill is

A deterministic, Zero-RAG codebase documentation engine. It builds two maps of a target codebase,
reviews them, and renders one browsable page:

| Map | Nodes | Built by | Output |
| --- | --- | --- | --- |
| **Structure** | classes / React components / module groups | `build_wiki.py` → `build_graph.py` | `data/structure/{graph.json, registry.json, vault/*.md}` |
| **Flow** | methods/functions | `build_flow.py` | `data/flow/{flow_graph.json, notes/*.md}` |

Three producers feed both maps -- Python (`py_extract.py`), JS/TS (`js_ts_extract.py`) and
everything else (`langs_extract.py`: Java, Go, C#, and since phase 7 Kotlin, Rust, Swift, Scala,
Groovy, Dart, C, C++, Ruby, PHP and Elixir) -- and since phase 2 all three are **tree-sitter**.
There is one parser in the build, and **seventeen languages have a graph**.

**Precision is stated once, globally, and named per node where it can be.** Every language's call
edges are a lower bound -- a call is drawn only when the receiver's type can be read from the
source -- and that caveat lives in `taxonomy.PRECISION_CAVEAT`, printed by `brief` and the report
header. What a node carries is `precision`: a list of *named* losses
(`interface-dispatch`, `overloads`, `name-matched`), computed by `taxonomy.precision_of()`
from what the node calls and drops, never from its language alone: `name-matched` is earned by
`untyped`, the dropped calls through a receiver of unknown type whose names the graph defines. It
was on every JS/TS/Ruby/PHP/Elixir/Groovy node until finding #25 (r51). It replaced a per-node `approx: true` on
Java/Go/C#, which was honest while those three were read textually and became arbitrary once every
language moved to tree-sitter. Adding a producer means teaching `build_wiki` what its entities
reference and `build_flow` how to resolve its calls, nothing else. Python and the Java family
share one entity builder -- `build_wiki.extract_backend_entities`, called once per producer so
the collision order stays Python, then JS/TS, then the rest -- because what an entity *is* does
not differ between them; the one thing that does, *what it references*, is named in `_refs_of`.
Their **flow** analyzers stay two on purpose (`_analyze_py`, `_analyze_lang`): at least 67 lines
of the latter are overload sets, Spring beans, return types, getters and `via` chains that
Python has none of, and their node constructors differ in `signature`, `hash` and `code` by
construction (ROADMAP finding 39). JS/TS keeps its own entity pass, since a JS specifier names
a *file* rather than a name.

**A dropped call keeps its name.** `ext` counts the call sites that did not become edges, and
used to keep nothing else, so `print(...)` -- correctly dropped, nothing in the graph is called
that -- was indistinguishable from a call to a name the graph *does* define, which is a missing
edge. `build_flow._record_dropped` keeps the names and `_split_dropped` keeps those the graph
defines as `unresolved` (`context.py` prints them on the node). It is name-matched and therefore an
over-count -- on the skill's own code 207 of 2,782 dropped sites, and 11 of them the *same* real
gap. Nothing turns it into an edge.

**Node ids are bare unless a name is defined in more than one file** -- in *both* maps.
`core/ids.py`'s `SharedNames`, used by `build_flow` and `build_wiki` alike,
pre-scans every definition from all three producers, then qualifies only the ids two or more files
share -- by file stem, else by path -- compared **case-insensitively**, because each node's note is
`<id>.md` and `Widgets.X` / `widgets.X` are one file on Windows and macOS. That includes two
*different* names that differ only by case (`login` in one file, `Login` in another): grouping by
exact name missed them until a real Next.js repository put the two notes in one file. A call to a shared name
resolves to the caller's own file's definition, or is dropped (`FlowIds.target`). Before this,
every `main()` was one node carrying every definition's calls: 72 false edges on the skill's own
code. `sample_src` has no shared names, so none of its ids changed.

**A node's range starts at its first decorator, annotation or attribute** -- in every language,
both maps. `@PostMapping`, `[HttpPost]`, `#[post(...)]` and `@app.route` are part of what a
handler *is*, so a finding on one of those lines belongs to the handler (finding #6). It used to
be the name line in Python/Java/C# and the decorator line in JS/TS; `tests/fixtures/langs`'
`lines` column pins it now.

**Every method is its own node, overloads included** -- in the languages that have them (Java,
C#, Kotlin, Scala, Swift, C++, and Groovy through Java's tree; `langs_extract.OVERLOADING`). A name a
class defines twice gets its parameter types in its id -- `InvoiceService.Total(InvoiceRequest)`,
`InvoiceService.Total(int,int)` -- and every other id stays bare (`build_flow._local_names`). A
call picks its overload by argument count, then by every argument type the source states -- a
literal, `new X(...)`, or a name with a declared type (`build_flow._pick_overload`); what that
leaves ambiguous is dropped, and the caller records the set in `ambiguous` and carries
`precision: overloads`. Until finding #8 an overload set was one node holding every overload's
calls but one overload's range; `signatures` now appears only when two definitions still cannot
be told apart. Anything that looks a node's name up in source asks `ids.bare(id)`.

**An implementation is linked to the method it implements.** A call through an interface stops at
the declaration, and which class runs is decided outside the source (a constructor argument, a
Spring bean). What the source *does* state is `class FlatRate implements PricingRule`, so
`build_flow._implements_links` joins each method to the same-named method of its class's nearest
base in the graph -- walking past a base that defines none, pairing overloads by parameter types --
as an `implements` link stored `FlatRate.price -> PricingRule.price`. Every walker reads it
backwards through `taxonomy.call_direction` (traces, `--impact-of`, orphans, `search.py`,
`context.py`, the explorer's blast radius), and nothing counts it as a call: not `calls` /
`callers`, not `precision`, not coupling, cycles or layer violations. It says which classes *can*
run a call, never which one does (r50, `check_graph` c21). Go states no bases, so its interfaces
get none. In the structure map a stated base is an `implements` link too, walked the same way, so
a class implementing a referenced interface is not an orphan (finding #29, r55).

**The object model is stated, and named** (r61). A class node's `kind` is `interface`, `abstract`
or `class` -- an interface/trait/protocol node, Kotlin's `interface` keyword, an `abstract`
modifier token (`langs_extract._class_kind`), TypeScript's `abstract_class_declaration` (which was
not read at all before), a Python `Protocol` / `ABC` / `@abstractmethod`, a Go `interface` type.
The explorer draws it as a shape, never a colour: an interface hollow, an abstract class ringed
dashed. Inheritance is three links, all in `taxonomy.INHERITANCE_LINKS` (= `REVERSED_LINKS`):
`implements` (a class fills in an interface; a method fills in a declaration), `extends` (a class
inherits a class, an interface an interface -- structure map, decided in `build_graph` once both
ends' kinds are known) and `overrides` (a method replaces a base method that has a body -- flow
map). Every walker, check and exclusion that named `implements` reads the set instead. A method
with a body that **every** subclass in the graph replaces carries `overridden: true`
(`build_flow._overridden_everywhere`); uncalled, it is listed by `analyze.find_overridden` in its
own report section and **not** as an orphan -- its body never runs today, but deleting it changes
what a new subclass inherits, which dead code never does. It is not graded.

**A class name two files define is settled by the source** (r57). Two applications in one
repository each with a `ConfigService` used to resolve only from the caller's own file, so every
call from anywhere else was dropped. `langs_extract.class_locator` picks the file: the caller's
own, the only one, the one an exact `import` names, one a wildcard `import` or C# `using` covers,
or the one in the caller's package (Java, Groovy, C#, Kotlin record `package` and `imports`).
`build_flow._analyze_lang` and `build_wiki` both ask it, and so does `_base_resolver`. A call with
no receiver, `this.` or a typed receiver whose class does not define the name walks to the nearest
base that does (`ancestor_defining`, r58), and a local's type is read from its declaration --
`R3RequestDto request = mapper.read()`, a for-each variable -- not only from `= new X(` (r59).

**What the source settles, the resolver follows** (findings #27 and #28, and Spring injection):

- A call through a **global** resolves: a Python module-level `store = Store()`, or one imported
  with an unaliased `from m import store` (`py_extract._imported_globals`); a Kotlin top-level
  `val`; a Go package `var`; and `Registry.STORE.save()` through the static field's declared type
  (`via.fields`). A parameter or local of the same name hides the global. Python's
  `ClassName.method()` resolves as every other language's does (r52).
- A call made **outside any method node** -- a Java/C# field initializer, `static {}` / `{}` block
  or constructor, a Kotlin property initializer, `init {}`, secondary constructor or top-level
  property, a Go package `var` -- is collected as `init_calls`, and each callee carries
  `entry: init`, as module-load code carries `module`; a Go `func init()` does too. No link is
  drawn from anything (r53).
- **Spring**: a call through a type Spring injects into a class it manages (a stereotype
  annotation) links straight to the bean's method when the scanned source settles which bean --
  a `@Qualifier` naming one, one `@Primary`, the only bean (never a lone `@Profile` /
  `@Conditional*` one), or a `@Bean` method that builds exactly one class -- and otherwise stays at
  the declaration. Java, Groovy and Kotlin: a Kotlin `@Qualifier` on a constructor property or a
  `lateinit` field, and a `@Bean` function that builds one class (`= SmtpMailer()`), are read into
  the same `bean` / `qualifier` data (r54, r56 -- finding #30).

An agent answers architecture questions by **querying the graph, then reading only the notes on the
returned path** — never by scanning source.

### Pipeline (what calls what)

```
archaeologist.py  project | flow | both | check | report | brief   <- the only entrypoint
  project  -> build_wiki -> build_graph ------------------\
  flow     -> build_flow ---------------------------------+--> render_explorer()
      both extract through: py_extract.py     (Python,        tree-sitter)
                            js_ts_extract.py  (JS/TS/JSX/TSX, tree-sitter)
                            langs_extract.py     (14 languages,  tree-sitter)
           flow also reads: route_tables.py   (Django/Rails/Laravel/Phoenix tables -> handler nodes)
  report   -> report.py (scan_security + git_insights + analyze + metrics + debt + tests_map
                         + duplicates)
                                                                    -> data/report/<map>/
  brief    -> brief.py (reads the artifacts above, computes nothing)
  check    -> manifest.py (source hashes vs last build; --src optional, roots recorded)
                                                            \-> build_html.py -> data/explorer.html
```

### Where the scripts live

`scripts/` is grouped by role, and `archaeologist.py` is the only file at its root because it is
the only entrypoint:

```
scripts/
  archaeologist.py   the entrypoint
  paths.py           SKILL_ROOT / DATA_DIR / TEMPLATES_DIR, the sys.path bootstrap, and
                     long_path() -- every per-node file goes through it (MAX_PATH, phase 6d),
                     and skill_rel() -- every report's `graph` field (cross-drive, phase 9)
  core/     taxonomy.py  manifest.py  console.py  grammars.py  ids.py  doc_text.py
  extract/  build_wiki.py  build_graph.py  build_flow.py  py_extract.py
            js_ts_extract.py  langs_extract.py  route_tables.py  apply_descriptions.py
  review/   analyze.py  scan_security.py  git_insights.py  metrics.py  debt.py
            tests_map.py  duplicates.py  report.py  brief.py
  query/    trace_path.py  context.py  search.py  build_html.py
```

Dependencies point one way: `core/` imports nothing of the skill's, everything else imports
`core/`, and no two categories import each other in a cycle. Keep it that way — a new script goes
in the category it *depends on*, not the one it reads like.

Every script therefore opens with the same two lines instead of re-deriving its own paths:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)
```

Importing `paths` puts `scripts/`, all four category dirs **and `<skill>/vendor`** on `sys.path`,
which is why sibling imports stay bare (`import taxonomy`), why `import tree_sitter` finds the
skill's own copy before the user's, and why every script still runs directly from any working
directory (constraint 3). `console.py` and `taxonomy.py` need no preamble at all because they
touch neither `data/` nor a sibling.

`paths` is the one exception to "`core/` imports nothing of the skill's": `grammars.py` imports it
for `VENDOR_DIR`. That is deliberate — `paths` sits *below* the categories, imports nothing itself,
and re-deriving the skill root inside `core/` is exactly the duplication `paths` was created to
delete. Nothing else in `core/` may import a skill module.

- `taxonomy.py` owns every `kind`/`layer` value (mirrored in `templates/TAXONOMY.md`). Add values
  there, never inline. It also owns **which way a link is walked** (`REVERSED_LINKS` /
  `call_direction()`): an `implements` link is stored implementation -> declaration and every
  walker reads it backwards. It also owns **`SKIP_DIRS`** -- the one definition of which directories are
  not source (dependencies, build output, framework caches such as `.next/`); five hand-kept copies
  had drifted, and a Next.js dev server's output became 9% of a real repository's flow graph
  (phase 9). `target`, `out`, `coverage`, `vendor` and `data` are deliberately absent: each is a real
  source directory somewhere (`data` was listed for this skill's own output and hid a Next.js route
  segment on a real repository, r69; an installed skill copy is skipped by `source_dirs()` instead). It also owns `LANG_BY_EXT` / `lang_of()` -- one answer to "what language is
  this file", read by `metrics.py` and `langs_extract.py`. And it owns **what counts as a test
  file** (`is_test_path` / `is_test_file`): path and filename conventions plus framework markers
  (`@Test`, `@SpringBootTest`, `[Fact]`, `#[test]`, `func TestX(t *testing.T)`). Nodes in test
  files get `layer: test`, which is why `analyze.py` never calls them dead code and
  `scan_security.py` skips them. Every pass must ask taxonomy, never re-implement the check.
  When neither an annotation nor the name says anything, the **folder** does
  (`PATH_LAYERS` / `layer_from_path`, r79): an exact folder name, nearest first --
  `service/pnodata/` is a service, `response/` and `request/` hold models, `properties/` holds
  config. A fallback only, never an override, and matched exactly rather than as a substring:
  `api/` is a folder half a repository lives under, not six hundred clients. Words that name no
  layer here (`util`, `exception`, `constant`) are absent on purpose -- `unknown` is the honest
  answer, and on a real repository it stayed that for ~90 of 189.
  A layer word must end where the word ends (`(?![a-z])`, r78): `repo` matched
  `PnoDataReportMail` and `store` matched `StoredFileDto`, putting 7 classes of a real repository
  in `repository` -- and since that rule runs before `model`, a `*Dto` lost its layer, which
  fabricated the report's only layer violation. `repository` / `mapper` / `client` and the other
  long words still match anywhere, because no longer word contains them.
  It also owns **which annotation declares a layer** (`ANNOTATION_LAYERS` -- `@RestController`,
  `@Service`, `@Repository`, `@Entity`, `@Configuration` -- checked before any name rule, with
  `@Component` counting for nothing; `handler` is no longer a controller word, which on a real
  Spring repository made 24 service-to-handler calls "layer violations"), **what a framework
  calls** (`FRAMEWORK_ENTRY` / `framework_entry()`, and the Next.js file conventions in
  `next_entry()`: a matching node carries `entry` -- `@Scheduled`, `@Override`, `override`, `main`,
  `next:page`, `next:route`, `module` for a JS/TS function top-level code calls, or `init` for
  one a field initializer, initializer block, constructor or Go package `var` calls -- and
  `analyze.find_orphans` never calls it dead; `build_flow.write_graph` must copy it, and for one
  retest it did not, while r40/r41 passed on the in-memory dicts: assert on the written file).
  A **class** gets one too, through `container_entry` (`CLASS_ENTRY_ANNOTATIONS`:
  `@SpringBootApplication`, `@Configuration`, `@Aspect`, `@ControllerAdvice`, else the first
  `entry` one of its own methods carries) -- written by `build_wiki` into the page's front matter
  and read back by `build_graph`, since structure nodes carried no `entry` at all while
  `find_orphans` was already checking for one (r75). `@Component` / `@Service` / `@Repository`
  are deliberately **not** in that set: Spring builds them too, and sparing them all would end
  dead-class detection for a whole application. And
  **what a language calls a decoration** (`DECORATION_TERMS` / `decoration_term()`): the graph
  field is one list (`decorators`) because every producer reads the same thing, but a vault note's
  heading is the language's own word -- `Annotations` for Java/Kotlin/Groovy/Scala/Dart,
  `Attributes` for C#/Rust/Swift/PHP/Elixir, `Decorators` otherwise; Lombok's `@Data` under a
  `## Decorators` heading named it in a language that has no decorators. And
  **`source_dirs()`**, the one walk filter every walker calls: `SKIP_DIRS` plus any installed copy
  of this skill (a child directory holding `SKILL.md` and `scripts/archaeologist.py`), which a
  project that installed it under `.claude/skills/` used to graph as its own code.
- `grammars.py` owns "can this machine parse language X" -- the wheel table, lazy cached parsers,
  the exact `pip install` for anything missing, and the installed versions for the manifest. It
  owns the **pins** too (`PINS`: exact per grammar, a range for the runtime, since phase 6c), and is
  itself the installer: `grammars.py --install [langs]` runs pip with the interpreter that will run
  the skill. `bin/cli.js` calls it rather than keeping a wheel list, and every doc points at it
  rather than spelling out package names -- a second list is how the pins went missing before.
  `drift()` names an installed grammar that is not its pin; `brief` prints it as `UNPINNED`. It
  lives in `core/` because `manifest.py` needs it, and `core/` may not import `extract/`. It also
  owns the two questions the vendor directory creates: **`origins()`** (did this resolve from
  `vendor/` or from site-packages — both can be installed, and `sys.path` order decides silently)
  and **`runtime()` / `runtime_error()`**, which turn an unloadable runtime into one sentence
  instead of a traceback. `runtime_available()` is a `find_spec`, `runtime()` is the real import;
  they disagree exactly when the wheels were built for another Python, so a caller reporting a
  skip must ask `runtime_error()` first — telling someone a grammar is missing when it is sitting
  right there sends them to reinstall what they already have.
- `ids.py` is the one id rule for both maps: `SharedNames` is given every definition's (name,
  file) before any node is built, qualifies only the names two or more files define (stem, else
  path, compared case-insensitively), and resolves a reference to a shared name to the
  referencing file's own definition or to nothing. Pure logic -- it imports nothing -- so it sits
  in `core/` below both `extract/` builders. The structure map used to keep the first entity of a
  shared name and drop the rest; the flow map used to merge them. Neither does now.
- `doc_text.py` is the one rule for turning a doc comment into a node's `doc`, and every producer
  asks it. The rule is `langs_extract`'s: the comment block above the declaration, blank lines
  invisible, stopping at the first non-comment (a comment separated by code is not the doc);
  *consecutive* blocks all count, which is how a run of `//` becomes one doc; markers are stripped
  and every non-empty line is joined with a space, so a `doc` is always exactly one line. Finding
  the block stays in each producer -- only it knows its grammar's comment node types -- and the
  cleaning is `clean()`, or `join()` for a Python docstring, which has no markers. `clean(xml=True)`
  is for the languages whose doc convention is XML or HTML (C#, and JS/TS, since JSDoc borrowed
  Javadoc's); it is **off** for the rest, because the tag sweep cannot tell a tag from a generic and
  `Vec<String>` in a Rust doc comment is not markup. Before this each producer answered
  differently: JS/TS refused a comment that was not on the line directly above and kept only one
  line *of the nearest block*, so a doc written as a run of `//` was published as its **last line**
  -- three of the sample's five JS/TS docs were sentence fragments (r80); Python was truncated at
  its first line by each call site separately. Python is the one deliberate asymmetry left: a `#`
  comment above a `def` is not documentation in that language, so only a docstring counts, and it
  goes through `join()`. Pure string work -- it imports nothing -- so it sits in `core/` below every
  producer.
- `py_extract.py` is the Python producer, and since phase 10 it really is one: `find_py_files`
  / `extract_py_files`, the contract the other two already kept. It was a *helper library* until
  then -- ~25 tree helpers, with the Python extraction itself spread over 120 `px.*` call sites in
  the builders -- because phase 2's port swapped `ast` calls for tree-sitter calls **in place**, to
  keep the diff that proved it. Fixing a Python resolution rule meant editing the graph builder.
  595 lines moved here, and the graphs came out byte-identical. A call site is emitted as
  `{name, type}` where `type` is what the source states -- `""` a bare call, `"self"` a
  `self.method()`, `"Cls"` a receiver the source types, `"?"` one it does not (with `recv` when
  that receiver is a bare name the graph may know as a class) -- and `build_flow._py_targets`
  decides the target, the same split every other language has. Python states no field types, so
  `_attr_types` builds `self.<attr> -> Class` out of what `__init__` was handed, and
  `extract_py_files` parses every file before reading any, because a call through a global
  resolves across files (`_imported_globals`, finding #27). The `ast` helpers it still exposes
  are the `ast` helpers of `build_flow.py`, `build_wiki.py` and
  `metrics.py` translated node-for-node, plus `read_source()`, which normalises newlines because
  `ast` was handed universal-newline text and tree-sitter is handed raw bytes -- without it a CRLF
  checkout hashes every node differently and silently misses the description cache. `ast` is **not**
  gone: it is the oracle, and `tools/check_py_oracle.py` parses every file both ways and fails on
  any disagreement about what was declared. That is the one reason to keep a stdlib parser around,
  and the only thing in the repo that still imports `ast`. `load_time_calls()` collects what a
  module calls as it is imported -- top-level statements and the `if __name__ == "__main__":` guard,
  never a def, class or lambda body -- and `build_flow` marks each callee `entry: module`, as it
  does for JS/TS; a shared `main` resolves to the caller's own file (r48).
- `js_ts_extract.py` reads JS/JSX/TS/TSX from a tree-sitter parse: classes, functions, imports,
  Express and Nest routes, `fetch`/axios calls (including an axios instance *imported* from the
  one file that creates it, directly or through a factory function -- `extract_js_files` parses
  every file before reading any, and an import that resolves to exactly one such file binds the
  name -- and URLs built on a same-file `const BASE = "/x"`), and the JSX rule that makes a function a
  `kind: component`. A call carries the **class of its receiver** where the source states it --
  `new X()`, `this`, `this.<typed field>`, or a typed parameter or local -- and `"?"` where it does
  not, the same shape `langs_extract` emits, so `build_flow` resolves JS/TS the way it resolves Java.
  Until then the receiver was discarded and class methods were never registered as candidates, so
  **no call could land on a JS/TS class method at all** (the TypeScript fixture: 0 edges of 3).
  It replaced the Node extractor behind that extractor's exact output contract
  (`find_js_files` / `extract_js_files` / `frontend_degraded`), which is why the port could be
  proved by diffing JSON rather than by reading code: the diff reported **identical output** on
  all six sample files and the graphs came out byte-identical. That reference (`js_bridge.py`,
  `js_extract.js`, `@babel/parser` 7.29.8) and the diff tool were deleted at step 4, so the
  comparison cannot be re-run -- `fd9c7d8` is its record. Four extensions, three grammars: `.tsx`
  will not parse under the TypeScript language and needs `tsx`.
  Imports carry `bindings`, and once every file is parsed, the `path` they resolve to --
  relative, through the nearest tsconfig/jsconfig `paths` (`@/utils/x`), else the one suffix
  match; when two apps in one repository both have that suffix, the one inside the importer's
  nearest package.json/tsconfig/jsconfig folder (`_package_root`, r62) -- so `build_flow` follows `label()` or `errors.toMessage()` to the *imported* file's
  definition even when another file defines the same name. Only a binding under the exported
  name itself: `import { a as b }` would draw an edge to a name the caller never spells
  (`check_graph` c13). An anonymous `export default function () {}` is a node named by its file
  stem, and inside a Next.js app (`next.config.*`, or a package.json depending on `next`) each
  exported function the framework calls carries `entry`. `tests/fixtures/ts_imports/` pins all of
  it (`check_regressions.py` r42). Top-level code is read too: what a module calls as it loads
  (`export const api = createApiInstance()`, never a function body passed at top level) goes in
  `module_calls`, resolved like any call, and the callee gets `entry: module` (r45). `new X()` is
  kept as `constructs`, which the structure map counts as a use of `X`. In the structure map a
  resolved import also records the file it named (`import_sources`), so `render_entity` links to
  that file's definition with `SharedNames.id` even when two files define the name. A name the
  file defines **itself** is a reference too (`build_wiki._provided_names`, r77): JS/TS and Python
  resolved references from the import list alone, so a component calling a function of its own
  file's module group pointed at nothing -- not one of 385 references into a module node on a real
  repository was same-file. A module group *is* its functions, so a use of one names the group; a
  node never references itself. The Java family already resolved this through `class_locator`.
  A call through a variable resolves in every shape the source states exactly (r47): a
  module-level or imported `new ProjectApi()` instance types the receiver (`_module_instances` /
  `_imported_types`, the axios-instance idea generalised); `export * from`, `export { x } from`
  and `export * as ns from` are `reexports`, followed by `build_flow`'s `exported_node` /
  `exported_member` when exactly one re-exported file has the name and never through a rename;
  and an object literal's inline members (`export const api = { approve: async () => ... }`) are
  flow nodes `api.approve` (kind `method`, `cls: api`, with their own HTTP calls), while a member
  that only names a function of the same name is an alias for it. A hook's untyped return value
  stays dropped. A call on another call's result carries `via` (below), typed from `(): X` return
  annotations. And `<Name />` in a component is a flow edge of its own type, **`renders`**,
  resolved like a call -- `<Ctx.Item />` names an object's member and draws nothing (r49). It is
  followed by traces and `--impact-of`, excluded from `node["calls"]` / `callers`, `precision`
  and `analyze.app_edges` (coupling), and drawn lavender and dotted in the explorer.
  Three shapes of indirection resolve, all from what one function's source states
  (`_scope_bindings`): a `const` holding a name or a `?:` / `||` / `??` of names is a call to every
  branch (`const save = id ? updateUser : createUser`, r66); a function handed over -- call argument,
  object value inside one, JSX attribute -- is a **`passes`** link, handled exactly like `renders`
  and resolved only through an import or to the passing file's own function, never a parameter or
  local (`passed_node`, r67; at top level it sets `entry: module`); and a call on an object resolves
  when the object is a renamed or default import (member calls only), a `const` choosing between
  objects, or the result of a function whose every `return` is one object literal naming the
  functions (`returns_members`, r68). A field of a hook's result -- `const { api } = useSetdatVariant();
  api.fetchX()` -- follows only written types (r72): the hook's `(): T` or the `createContext<T>` every
  `return useContext(Ctx)` reads (`returns_type` / `returns_context`, file-level `contexts`), then
  `interface T { api: X }` / `type T = {...}` (`types`, found through imports by
  `build_flow.declared_in`), then `type X = typeof service`, then `service`'s member as r68 does. A
  prop is still untyped. `const Button = forwardRef(...)` / `memo(...)` is the function it wraps
  (`_wrapped_function`, r70), so it is a node and a component.
  **An object handed over whole is not unpacked** -- `t.rich(key, { ...TAGS })` passes `TAGS`, and
  its members keep no `passes` link. That is deliberate, and the rule behind it is stated in
  SKILL.md's Command 10: an orphan means "no code references this", the standard an IDE's *unused*
  hint uses, so a function a framework finds by a name held in **data** (a next-intl tag named only
  inside `en.json`, a string-keyed bean, reflection) is an orphan and correctly so. Following the
  spread, or reading message files for tag names, would invent links; do not add either.
- `langs_extract.py` reads Java/Go/C# from a real parse tree, and keeps the same
  `find_lang_files` / `extract_lang_files` contract the textual extractor before it had -- which is
  what let the port be verified by diffing the graph instead of by reading code. That extractor
  (`lang_extract.py`, 788 lines) was deleted at step 2 once the diff was clean; it is in git
  history if the comparison is ever wanted again. It was called `ts_extract.py` until
  2026-09-12: `ts` meant *tree-sitter*, but next to `js_ts_extract.py` -- which is the one
  that reads TypeScript -- it read as the opposite of what it does. The name now matches the
  contract it exports (`find_lang_files` / `extract_lang_files`). One shared consumer works
  in tree-sitter *field* names (`name`, `body`, `parameters`, `type`); only the `SPEC` table knows
  node-type spellings. Adding a language is a row there plus its receiver rule. tree-sitter gives
  declarations, bodies, param types and doc attachment; it does **not** give resolution, so
  `_calls` still answers `""` / `"Type"` / `"?"` exactly as before.
  **Since phase 7 it also reads eleven more languages**, through a second, shared walker rather
  than more inline branches: `SHAPES` names each grammar's container / method / comment node
  types, and a handful of small readers cover the trees that are genuinely shaped differently (a
  Rust method lives in an `impl`, a Dart method is a signature *beside* its body, a C function's
  name sits inside nested declarators, an Elixir `def` is a macro call). Groovy's tree is Java's,
  so it takes Java's branch (`JAVA_LIKE`). The walker adds one resolution rule these languages
  lean on: a receiver that is itself a type name (`WidgetStore.save` in Elixir, `Widget::new` in
  Rust) resolves to that type. Java, C# and Groovy use the same rule (`_type_name`, so
  `DateUtil.now()` resolves), and so does JS/TS; Go does not, because a capitalised Go head is as
  often an exported value as a type. `build_flow` still requires the class to be in the graph and
  to define the method, so `Math.max()` drops as before. Java-family method references
  (`this::clearBin`, `Store::save`, `store::flush`) are read as calls the same way; they carry no
  argument list, so an overloaded target is dropped as ambiguous rather than picked (r44).
  A Java `String... parts` is read as a parameter (`_param_pairs`; its id segment is `String[]`)
  and its kind as `...String`, which `_pick_overload` tries only when no fixed-arity overload
  fits -- Java's own order (r63). A cast receiver, `((UserSecurity) u).getPlantIds()`, is typed
  by the cast in Java, Groovy and C# (r65), and so is a pattern variable -- `instanceof T t`,
  `case T t ->`, C#'s `is T t` (`_tree_locals`, r71). And the Java inside MapStruct's
  `@Mapping(expression | defaultExpression | conditionExpression = "java(...)")` is parsed as Java
  and read like a body, with the method's parameters in scope (`_expression_calls`, r64) -- so a
  body-less mapper declaration carries call links, the one exception `check_graph` c08 allows.
  A call whose receiver is itself a call -- `resolveHandler(type).downloadFile(x)` -- is read from
  the receiver *node*, never its text (`resolve(a.b)` holds a dot inside its parentheses), and
  carries `via`: the innermost call's receiver type and the calls outward. Methods record
  `returns` (Java/Groovy `type`, C# `returns`, Kotlin's unnamed type after the parameters), a
  Java class with Lombok `@Data` / `@Getter` / `@Value` (or a field's `@Getter`) records
  `getters` typed by their fields, and `build_flow._analyze_lang` walks `via` through them. A
  step whose type is unknown, or whose definitions disagree on a return type, drops the call (r46).
  For the **structure** map it also records `refs` -- every type name a class or method's own
  source states: return types, *every* generic argument (`_base_type` keeps only the head, so
  `GlobalResponse<PaginationResponse<UserResponse>>` used to yield one name of three), local
  declarations, `X.class`, and the class a static constant is read from (capitalised, and never in
  Go). That is what an IDE counts as a usage; it draws references, never call edges
  (`_type_refs`, r73). Java, Go and C# keep their own branches untouched -- the sample's
  graphs were byte-identical before and after.
- `route_tables.py` reads routes declared **away from their handlers** (phase 8): Django
  `urlpatterns` (with `include()` prefixes, regex paths and class-based views -> one route per HTTP
  method the class defines), Rails `routes.rb` (`resources`, `namespace`, `scope`, `member`),
  Laravel `routes/*.php` (both handler forms, `prefix()->group`, `resource`), Phoenix routers
  (nested `scope` aliases, `resources`). It only *reads*; `build_flow._attach_table_routes` attaches
  each route to the one node its `(class, method)` reference names -- a Django function view is also
  pinned to the file its import points at -- before the cross-stack pass. A reference naming no
  node, or two, is dropped and counted in one stderr line, never guessed.
- `trace_path.py` is the query tool: `--from/--to` (BFS path), `--impact-of` (blast radius),
  `--impact-of-diff` (map a git diff to nodes, union their impact). Works on either graph. An
  `implements` link is walked declaration -> implementation, so a trace through an interface
  reaches every implementation and `--impact-of` on one reaches the interface's callers.
- `analyze.py` is graph-only: cycles, orphans, layer violations, hubs, god objects, name-based
  idioms, and the 0–100 / A–F `health()` score (accepts security counts). Degree-based checks run
  on `app_edges()`, which drops edges touching a `layer: test` node — test calls are coverage, not
  coupling — and `renders` / `passes` / `implements` links. Cycles and layer violations ignore `implements`
  too: a decorator delegating to its own interface is not a cycle. `find_orphans` never lists an
  overload of a set some node names in `ambiguous` (`this::values`): one of them is called, the
  graph cannot say which, so the whole set is spared rather than one member guessed (r63). Nor a
  base: `implements` / `extends` mark **both** ends used, because `class Audited extends Auditable`
  names the base in its own source -- the backwards walk alone only ever marked the child, so a
  base with twelve subclasses was dead (r74). Not `overrides`: replacing a method does not
  reference the base body, which is `find_overridden`'s case.
- `scan_security.py` is line-regex over source; every finding is attributed to the innermost node
  whose `source`..`end` range **contains** that line, or to none (`owner_of`, shared with
  `debt.py`). It used to take "the last node starting at or before the line" and never looked at
  `end`, which pinned module-level findings on the preceding function — 99 of 152 on the skill's
  own code. A credential-named key is not reported when its value only *names* a credential -- the
  key's own name (`ACCESS_TOKEN: "accessToken"`), a path, prose, or lowercase words joined by
  `-`/`:` (`space-y-4`, `auth:token-refreshed`; a UUID mixes letters and digits in a segment and
  is still reported) (`_names_not_holds`); all ten
  "hardcoded secrets" on a real repository were one of those, at 10 grade points each.
  `git_insights.py` is one `git log --numstat` pass → churn, owners, hotspot risk.
- `metrics.py` is line counts per file plus LOC / cyclomatic complexity / nesting depth /
  parameter count per node **in every graphed language**, measured on the graph's own nodes: a
  node's `source` + `end` pick its definition out of the file's parse (`locate`), and one
  `TABLES` row per grammar names its decisions, blocks and definitions. So metrics are keyed by
  graph id by construction -- until phase 6a they were keyed by *bare* name, first wins, which
  left 66 of 294 nodes on the skill's own code unmeasurable, and every non-Python node had
  none. Structure classes and components carry `source: file:line` + `end` for this since 6a;
  a module group is a whole file and has no range, so it is listed in `unmeasured_graph_ids`
  with the declarations. `report.py` derives `file_census` from it, so line counts have one definition.
- `search.py` is the "which nodes are these" filter over one graph (name/doc/layer/kind/lang/file
  plus `--calls` / `--called-by` / `--orphans`). It exists so neither the agent nor a human greps
  source to find a starting node.
- `context.py` is the per-node pack: graph facts + metrics/security/insights for one node and its
  neighbors, rendered under a hard `--max-chars` budget. Like `brief.py` it only reads artifacts.
- `debt.py` (markers in comments + orphan nodes/files) and `tests_map.py` (which nodes a test file
  names) are the two "what is rotting / what is untested" passes. Both are heuristics on purpose
  and neither feeds the health grade -- they report, they do not judge.
- `duplicates.py` is the third such pass: it reduces each node's body to a token shape
  (identifiers -> `ID`, literals -> `LIT`, comments gone) and clusters equal hashes, so a renamed
  copy still matches. It reads ranges from the graph (`source` + `end`), never re-parsing --
  which is why `build_flow.py` records `end` on every node it builds. Nodes marked
  `declaration: true` are skipped: a signature has a readable range but no body to compare.
  Since phase 9 it also finds **blocks**: a run of 30+ tokens copied into two otherwise
  different nodes, which no whole-body hash can see. Winnowed k-gram fingerprints (K=10,
  W=21, so every shared run of 30 is guaranteed a common fingerprint) with a *stable* rolling
  hash -- Python's `hash()` is salted per process and would break constraint 2. Matches grow
  to maximal runs and are trimmed to **whole lines** in both copies, so half a statement never
  counts; that keeps the "never re-parses" property, where statement boundaries would need a
  parse. A pair already in a cluster is never repeated as a block; overlapping ranges are
  skipped; a fingerprint in 50+ places is boilerplate. Blocks are **grouped by shape** -- one
  entry per copied block with every `places` it occurs (finding #7); as pairs, one block in N
  places was N*(N-1)/2 entries.
- `brief.py` is the fixed-size digest an agent should open a session with — it only reads what the
  other scripts wrote. Anything expensive belongs upstream of it, never inside it.
- `report.py` joins all of it into `data/report/<map>/architecture_report.{md,json}` plus
  `security.json` / `insights.json`. **One report per map** — node ids differ between maps, so a
  report from the other map must never be embedded (`build_html.report_for()` enforces this).
- `build_html.py` is thin: it loads `templates/viewer.html`, substitutes `__TITLE__` and
  `__MAPS_DATA__`, and writes **one** `data/explorer.html` holding both maps (header switch).
  `archaeologist.py` renders it **once**, after every map and the manifest, and a missing
  `templates/vendor/force-graph.min.js` is one named error and a non-zero exit -- never a lost
  map. On a real install it stopped `both` before the flow map: npm packs the repo for `npx` and
  reads the skill's `.gitignore`, whose unanchored `vendor/` (meant for the pip wheels) also
  dropped `templates/vendor/`. The rule is `/vendor/`, and `bin/cli.js` checks the file is there.

### Where the front-end lives

The explorer filters test nodes at load (`loadMap` -> `HAS_TESTS` / `EDGES`) and starts with them
hidden (`#showTests` has no `checked`), so the **Tests**
checkbox re-renders through `applyMap`; anything reading edges must use `EDGES`, not `GRAPH.edges`.

`templates/viewer.html` is a normal HTML/CSS/JS file (three-pane explorer: health ring + tiles +
LOC/language mix + file tree | seven views: Graph/Treemap/Matrix/Tree/Flowchart/Cluster/Bundle |
FILE/PATTERNS/SECURITY tabs). Edit it directly; don't move markup back into Python. Its per-map
state is rebuilt by `loadMap()` / `applyMap()` — anything derived from a graph belongs in there,
not in a top-level `const`.

A node is drawn and listed by `labelOf(n)` -- its id without the file qualifier `ids.py` adds
to a shared name -- and its path lives in the right panel, never on the canvas. A file/folder
filter and a Flowchart selection **hide** what they leave out (`visibleIds`, through
force-graph's `nodeVisibility` / `linkVisibility`) rather than dimming it: a file keeps its own
nodes plus their direct links, a Flowchart selection its whole flow -- every caller back to the
start and every callee to the end, whatever **Blast radius** says (it only picks the highlighted
links). The flow kept is the **focus**'s (`focus`), which is the selection unless **Freeze** is
ticked: then a click still selects (panel, highlight) but neither re-narrows the Flowchart nor
flies the other views, and unticking catches the view up with the selection. Clicking empty canvas
clears nothing -- only the toolbar **reset** (or Escape) drops the selection and focus. On a
1,500-node repository a faded node was still in the way. The Flowchart replaced the old `Flow`
view (a `dagMode("lr")` force layout) and keeps its id `flow`: `layoutFlowchart()` gives each
node the column of its longest call path, orders rows by folder and then by neighbours'
rows, puts unlinked nodes in a grid underneath, and pins the result like Cluster and Bundle;
`drawFlowBox` / `drawFlowLink` draw boxes and elbow links from the same colour and dash
accessors as every other view.

### Colour rules

One meaning, one colour, everywhere — a reader learns the scheme once, from any view.

- **Test code is green** (`TEST_COLOR` in `viewer.html`): the node (`LAYER_COLORS.test`), its
  folder area, the legend, all the same green. It is deliberately kept out of `FOLDER_COLORS`, so
  an ordinary folder can never be handed it.
- **A folder's colour comes from its index in `allFolders`** — every folder in the map — never
  from the visible list. Colouring off the visible list meant hiding the test folder re-coloured
  everything after it, and pink stopped meaning the same folder from one screenshot to the next.
- **A new `layer` / `kind` value needs its colour in `LAYER_COLORS` in the same commit** that adds
  it to `taxonomy.py`. The legend, the node painter and every view read from there; nothing
  hard-codes a colour at a call site. The one exception is a **class kind** (`interface`,
  `abstract`): a node's colour already means its layer, so a class kind is a *shape* in
  `drawNode` (hollow / dashed ring) and in the legend (`.kind-interface` / `.kind-abstract`).
- **Languages are coloured by family** (`LANG_COLORS`, the rail's language-mix bar): JVM
  (Java/Kotlin/Scala/Groovy), .NET, native (C/C++/Rust/Swift), dynamic (Ruby/PHP/Elixir), Go,
  Dart, plus the original five for Python and JS/TS. Seventeen distinguishable hues on this ground
  do not exist, and the label beside each swatch names the language. The family hues sit outside
  `FOLDER_COLORS` and the layer palette, so none of them means two things.
- The chrome is deliberately quiet so the data can be loud: near-black ground `#08090b`, hairline
  rules `#1b1f26`, one accent (amber `#d99f4a`) for the active state and nothing else, and a system
  monospace stack. No emoji anywhere in the UI — icons are inline SVG on a 16px grid. Keep it that
  way; the palette below is the only saturated thing on screen.
- Already spoken for: controller/endpoint pink `#f778ba`, service blue `#6ea8fe`, repository green
  `#3fb950`, model amber `#e3b341`, client teal `#39c5cf`, config purple `#a371f7`, ui orange
  `#f0883e`, test green `#57ab5a`, unknown grey `#8b98ad`. Pick something distinguishable from all
  of them on the dark background — and if two must be close (the two greens are), keep them in
  different channels: node dots vs folder areas.
- Edges are a channel of their own: `calls` grey, `http` pink dashed, `renders` lavender
  `rgba(167,139,250,.45)` dotted (matrix cell `#a78bfa`), `passes` sky `rgba(125,211,252,.45)`
  dash-dot (matrix cell `#7dd3fc`), `implements` light grey
  `rgba(201,209,217,.4)` long-dashed (matrix cell `#c9d1d9`), `extends` sand
  `rgba(214,190,140,.45)` long-dashed and `overrides` the same sand short-dashed (matrix cell
  `#d6be8c`) -- one relation at two levels, one hue. Config purple and model amber live on node
  dots, so none of them shares a channel.

### Layout rules

The explorer is a three-pane desktop app, and it behaves like one: chrome holds still, content
scrolls.

- **One scroll region per pane, never two nested.** The left rail scrolls in the file tree only;
  the right panel scrolls in its body only. If something does not fit, fold it or shrink it —
  never add a second scrollbar. The one exception is the **colour legend** (`#legend`), capped at
  `max-height: 132px` and scrolling: in folder mode it is one entry per folder, so a real
  repository's ~120 folders pushed Census, Explorer and the tree out of the pane with no way to
  reach them. It is a bounded list inside a section, not a pane, and the other three colour modes
  are a handful of rows that never reach the cap.
- **The node search lists, it never scrolls.** `#results` is `position: fixed` under `#search`,
  because the rail's `overflow: hidden` would clip it, and shows up to 12 matches (fewer when the box sits low in a short window) plus a count -- a
  scrolling dropdown would be a second scroll region in the rail.
- **A pane is a flex column**: `overflow: hidden` on the pane, `flex: none` on the fixed blocks,
  `flex: 1; min-height: 0` on the one region that grows, and `min-height: 0` again on the scroller
  inside it (without it the scroller inherits its content's height and the pane scrolls instead).
  Give the growing region a `min-height` floor so it cannot be squeezed to nothing.
- **Rail sections fold from their own `h3`**, with the marker in `::before` and the body hidden by
  a `folded` class on the section. Folding is how the user gives the tree room, so anything bulky
  in the rail needs a header. A folded header still carries its count (`Explorer 7 files`) — a
  section that says nothing when closed is a dead control.
- **Fold state is a class on static markup**, so it survives every re-render and map switch by
  construction. Do not store it in a variable that `applyMap()` resets. Rail width works the same
  way — `--lw` / `--rw` set inline on `#app` by a drag, and nothing re-renders `#app`.
- **The rails resize, and that is all they do.** Two 9px grips (`.rsz`) straddle the pane borders.
  There is no collapse: it was built, and taken out again as a control nobody needed. The explorer
  is not resizable either — it takes every pixel the fixed blocks leave, and folding a section is
  how you give it more.
- **A rail may never eat the toolbar.** `setRail` caps a drag at what the centre still needs,
  measured by summing the toolbar's children — `clientWidth` would report "exactly what it already
  has" and let a drag ratchet controls off the right edge a pixel at a time. The cap counts only
  what the **compact** row needs (~560px): the toggles are left out of `stageMin()` because they
  can move. With both rails at their minimum the toolbar never clips above about **1020px** wide
  -- the supported floor (987px when measured in phase 5; the `Flowchart` label added 33px) (it was ~1270px, and ~1360px before that).
- **The toolbar compacts rather than clipping.** When the toolbar is narrower than the full row
  (~884px since `Freeze` joined the row; ~803px before), `fitToolbar()` re-parents `#toggles`
  (Folders, Blast radius, Freeze, Tests) into
  `#menuToggles` at the top of the `⋯` menu, and moves it back as soon as there is room. It moves
  the *same* elements, so ids, checked state and handlers travel with them; a `ResizeObserver` on
  the toolbar drives it. Clicking a toggle inside the menu leaves the menu open.
- **A toggle is shown only where it does something.** Folders draws areas in Graph and Cluster
  only (`drawHulls`), so `setView` hides `#hullsToggle` in the other five views and re-runs
  `fitToolbar()` -- showing it again widens the row, which no resize reports.
- **The toolbar row holds only what is used constantly.** Zoom in/out, fit and PNG export live in
  the `⋯` overflow menu (`#more` / `#moreMenu`), which took the full row from ~897px to ~770px.
  A new control goes in that menu unless it is used on
  nearly every visit. The menu items keep their old ids (`zoomIn`, `zoomOut`, `zoomFit`, `png`), so
  no handler depends on where a control is drawn.
- **Below `max-height: 620px`** the rail gives up and scrolls as a whole — a 60px tree is worse
  than a scrollbar.
- **Dragging a node pins it** (force-graph sets `fx`/`fy` and leaves them), so `resetLayout()` is
  the only way back. It deletes `x`/`y`/`vx`/`vy` as well as clearing the pins, because `setView`
  alone only unpins and reheats — the simulation would restart from wherever the nodes were
  dragged. It hangs off the existing toolbar **reset** rather than a button of its own -- a new
  toolbar button would cost the row width the overflow menu was introduced to win back.

## Hard constraints

1. **One parser per language, and every one of them degrades.** Python 3.10+.
   **Every language is tree-sitter, Python included**: the runtime plus the wheel for that
   language (`tree-sitter-python`, `tree-sitter-javascript` for `.js`/`.jsx`,
   `tree-sitter-typescript` for `.ts` *and* `.tsx`, `tree-sitter-java`, `tree-sitter-go`,
   `tree-sitter-c-sharp`, and since phase 7 one each for Kotlin, Rust, Swift, Scala, Groovy, Dart,
   C, C++, Ruby, PHP and Elixir — all pinned in `grammars.PINS`) — wheels, no compiler, grammar
   bundled. Python no longer parses out of
   the box, and that is the promise phase 2 knowingly traded away: one engine, at the cost of
   "zero Python dependencies". **Node is not used at all**:
   it is not required, not checked for, and not installed. The skill has no `package.json`. **Grammars are installed on demand, not shipped**: a repo with no Go pays nothing for
   Go.
   **Every dependency installs inside the skill folder, never into the user's environment.**
   `pip install --only-binary :all: --no-cache-dir --target vendor` → `<skill>/vendor`, which is
   git-ignored, cannot collide with the user's own versions, and disappears with the skill folder. Keep all three pip flags:
   `--target` is the point, `--only-binary :all:` refuses to compile, `--no-cache-dir` stops pip
   writing wheels outside the folder. Because `vendor/` is built for one interpreter version, a
   Python upgrade breaks it — that must surface as a named message telling the user to re-run the
   install, never as an `ImportError` traceback.
   Every one of those is optional at runtime and must fail the same way: **warn by name, skip
   those files, still build the rest.** A missing parser may never be silent, because a graph that
   is smaller for want of a wheel is indistinguishable from a graph of a smaller codebase — which
   is why `manifest.py` records the installed grammar set and `check` reports a change to it as
   staleness, and why `brief` prints a `SKIPPED` block naming the exact `pip install`.
   That end state was reached in phase 2 (`docs/ROADMAP_PLAN.md`): one engine, tree-sitter, with
   `ast` kept only as a test oracle and Node gone. **Do not add a second engine** — a new language
   is a grammar wheel plus a `SPEC` row, never a new parser.
2. **Deterministic.** Same source in, same bytes out -- graphs *and* reports: no artifact carries
   a wall-clock time (`tools/check_regressions.py` r19 runs the report twice and diffs it). AI text enters only through
   `apply_descriptions.py` (cached by source hash, docstring wins first, deterministic fallback
   last).
3. **Paths resolve from the skill root**, so every script runs from any working directory.
4. **The explorer is one self-contained file, with no network at all.** Data *and* the graph
   library are embedded inline; it opens from `file://` with the network disabled. `force-graph`
   is vendored at `templates/vendor/` (see its README) and inlined by `build_html.py` through the
   `__VENDOR_JS__` placeholder. Nothing may reintroduce a `<script src>`, `<link href>` or
   `@import` — `bin/cli.js --self-test` fails the build if one appears. URL-shaped *strings* are
   fine and unavoidable (SVG/XML namespaces are identifiers the browser never fetches), so assert
   on resource loads, never on the substring `http`.
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

Expected on the current sample (it carries three deliberate smells -- a hardcoded key, interpolated
SQL, an innerHTML sink -- plus a pytest/unittest file, a `.test.ts`, a `.tsx` with two React
components, four API frameworks, and Java/Go/C# with two deliberate hard cases, so the review path, the test path, the component path, every route shape and the
"drop rather than guess" rule all have something to find):

- structure graph: **25 nodes / 23 edges** -- 7 Python, 6 JS/TS, 12 from Java/Go/C# (6 Java,
  3 Go, 3 C#), of which `OrderCard` and `StatusBadge` are `kind: component` / `layer: ui`.
  Structure nodes carry **no** `precision`: their edges are 21 references and 2 stated bases
  (`implements`: `FlatRate` and `TieredRate` -> `PricingRule`), and a reference from a declared
  field is resolved. No node is `layer: unknown` -- the three pricing classes take `service` from
  their `services/` folder (r79), which is the only thing that rule changes here. Exactly one node
  is not `kind: class` among the classes: `PricingRule` is
  `kind: interface`; no `extends` link, no `overrides` link and no `overridden` node exist in the
  sample, so r61 asserts those
- flow graph: **53 nodes / 36 edges** (29 `calls`, 4 `http`, 1 `renders`: `OrderCard -> StatusBadge`,
  2 `implements`: `FlatRate.price` and `TieredRate.price` -> `PricingRule.price`),
  **16 endpoints, 0 pending** descriptions; **4 nodes carry
  `unresolved`** (all four name `get`, and all four are the honest over-count -- axios's `api.get`,
  a Java `Map.get` -- which is why the field is a place to look, never an edge); one node
  `declaration: true` (`PricingRule.price`); **3 nodes carry `precision`** -- 2 `name-matched`
  (`getOrderEvents` and `getOrderStatus`: each drops axios's `get` through an untyped receiver, so
  each carries `untyped: [get]`), plus exactly one earned by an edge: `OrderWorkflow.place` ->
  `interface-dispatch` (it calls the declaration). If it moves, a named marker has stopped
  working. `overloads` marks no node in the sample -- both calls to `Total` pick their overload
  -- so `tools/check_regressions.py` r33 is where that marker is asserted; likewise no node
  carries `entry: init` and no Spring injection is settled (neither rate is a bean), so r53 and
  r54 assert those
- routes, one per framework shape: FastAPI `OrderController.create_order`; Flask `orders` with
  **two** entries (`GET` + `POST /legacy/orders`) and `order_detail` (`<int:order_id>`); Express
  `createOrderHandler` (named handler) and the endpoint node `GET /orders/:id/status` (inline
  arrow); Nest `OrdersController.{create,findOne}` under the `@Controller("nest/orders")` prefix;
  Spring `OrderApiController.{create,findOne}` under `@RequestMapping("/java/orders")`; ASP.NET
  `InvoiceController.{Create,Find}` under `[Route("cs/[controller]")]` -> `/cs/Invoice`; Go
  `handleOrderEvents` / `recordOrderEvent` (named) and `GET /go/healthz` (inline literal)
- traces: `create_order -> place_order -> {save, charge}`, `get_order -> find_order -> get`, the
  Flask handler `orders -> place_order -> save`, and one per Java/Go/C# language --
  `OrderApiController.create -> OrderWorkflow.place -> OrderArchive.save`,
  `InvoiceController.Create -> InvoiceService.Issue -> InvoiceStore.Put`,
  `handleOrderEvents -> EventService.Events -> EventStore.List`
- cross-stack: `submitOrder -> createOrder -> OrderController.create_order -> ...`, and
  `loadOrderHistory -> getOrderEvents -> handleOrderEvents -> ...` all the way into Go; structure
  `OrderCard -> {ApiClientModule, StatusBadge}`
- `getOrderStatus -> GET /orders/:id/status` is the **suffix fallback**: the call is
  `/api/orders/:id/status`, the router registers `/orders/:id/status`, and it links because
  exactly one route matches
- the two deliberate hard cases, **both now resolved**:
  - **interface dispatch — resolved to the declaration.** `OrderWorkflow.place` calls
    `pricing.price()` through the `PricingRule` interface, and the edge
    `OrderWorkflow.place -> PricingRule.price` now exists, because a declaration-only member is
    extracted as a node (`declaration: true`, empty body, `end` at the end of the signature).
    The call edge stops at the interface: **no call edge is emitted to `FlatRate.price` or
    `TieredRate.price`** -- picking one impl would be a guess and emitting both would trade the
    precision guarantee for recall. Each carries an `implements` link to `PricingRule.price`
    instead, so neither is an orphan and a trace from `OrderApiController.create` reaches both.
  - **overloads — every overload is its own node** (finding #8).
    `InvoiceService.Total(InvoiceRequest)` and `InvoiceService.Total(int,int)` each have their own
    range; `Issue`'s `Total(request)` picks the first by argument count, and the first's
    `Total(request.Units, request.UnitPrice)` picks the second -- one edge more than when the pair
    was one node, which carried both bodies' calls but only one body's range.
  - The structure map *does* show `OrderWorkflow -> PricingRule` -- a declared field is a real
    reference even when the dispatch is not resolvable.
- a `declaration: true` node is a signature, not code: `duplicates.py` skips it (no body, no token
  shape) and `analyze.py` never calls it dead code (there is nothing in it to delete). Both guards
  are load-bearing, not decorative -- an uncalled declaration has no caller and would otherwise be
  reported as an orphan.
- grades: structure **C (73)**, flow **C (70)**; 4 risk findings each; 2 debt markers. Structure
  fell from C(71) to D(69) when the interface impls were added -- the hard case being honest, not
  a regression -- and rose to C(73) when their bases became `implements` links, leaving one
  structure orphan, `OrderPageModule`. Flow fell from
  D(69) to D(68) when the planted clone below was added -- nothing calls it, so it is one more
  orphan -- and rose to C(70) when `implements` links took `FlatRate.price` and `TieredRate.price`
  off the orphan list, leaving 5 flow orphans, all JS/TS.
- duplicates: **1 cluster, 2 nodes, 4 duplicated lines, 0 copied blocks** (the planted pair is a
  whole-body clone, so it is a cluster and never repeated as a block) -- `createInvoice` is `createOrder` with
  every identifier renamed, planted in `frontend/api_client.ts` so the clone pass has something to
  find. Renaming a variable in one copy must keep them clustered; changing an operator must split
  them.
- tests: 2 test files, flow **4/49 nodes named by a test**, and the two test nodes carry
  `layer: test` with call edges into `OrderService.place_order` / `OrderRepository.get`
- metrics: **52 of 53** flow nodes and **19 of 25** structure nodes measured, across every
  language; the unmeasured are exactly the declaration `PricingRule.price` and the six
  `*Module` groups, which have no range
- 529 lines across 22 files (py 126, java 102, csharp 90, ts 90, go 66, js 28, tsx 27)
- `archaeologist.py check --src ./sample_src` -> `stale: false` right after a build

Every grammar is optional and each one degrades the same way -- rename it out of `vendor/`, and
the build must still succeed with **one** named warning carrying the exact install command:

| Grammar removed | Warning | Structure | Flow |
| --- | --- | --- | --- |
| `tree_sitter_javascript` + `tree_sitter_typescript` | `frontend skipped`, naming **both** wheels | 19 / 19 | 37 / 23 |
| `tree_sitter_python` | `python skipped`, **once** for the whole run, not once per map | 18 / 12 | 39 / 21 |

Two checks stand in for the extractors that were deleted:

```bash
python tools/check_py_oracle.py                                   # must print: OK   0 disagreements
python tools/check_py_oracle.py .agents/skills/code-archaeologist/scripts
```

and the byte-identity of the committed graphs — rebuild, then `git diff` on
`data/structure/graph.json` and `data/flow/flow_graph.json` must be empty. That is the strongest
check available and it is what proved every port in phase 2: the JS/TS one, the Python one, and
`metrics.py`, none of which moved a single byte of either graph.

Other checks worth running when you touch the relevant part:

```bash
python -m compileall -q .agents/skills/code-archaeologist/scripts     # syntax
python tools/check_docs.py                                            # docs vs code
python tools/check_langs.py                                           # every language still graphs
python tools/check_py_oracle.py                                       # ast vs tree-sitter on Python
python tools/check_graph.py                                           # the graph deserves trust
python tools/check_graph.py --self-test                               # ...and every check can fail
python tools/check_regressions.py                                     # every past silent failure
python tools/time_build.py [<corpus> ...]                             # wall time per stage, read-only
node bin/cli.js --harness claude --target <tmpdir> --self-test        # installer
```

`tools/check_graph.py` asserts what a *correct* graph must satisfy, on any built graph: every
edge lands on a node, ids are unique, each node's range really contains its own name, each call
edge's callee is really named inside its caller, `precision` is what the edges imply, the report's
counts are the graph's, and every security finding lies inside the node it is attributed to, and no two nodes'
notes are one file on a case-insensitive filesystem (c17), and every call dropped as ambiguous
names a real overload set (c18), and no declaration has a call link unless its own range spells the
callee inside a MapStruct `java(` (c08), and every `renders` edge's `<Name` is written in its caller (c20), and every `passes` link's function is named in its caller (c23), and every `implements` link
joins one method name on two classes whose files name each other, directly or within three hops,
or in the structure map is a base its class names, and whose type matches its ends --
`implements` into a declaration or an interface, `overrides` into a body, `extends` otherwise
(c21), and every `overridden` node has an `overrides` link into it and a body (c22). Its
`D` checks test the analysis *metamorphically* — inject a cycle, an orphan, a hub, a god object or
a layer violation into a copy of the real graph and require it to be reported — because a detector
that returns nothing looks exactly like a clean codebase. `--self-test` breaks the input (or swaps
an analysis function for a broken one) once per assertion and fails if the check stays quiet: an
assertion that cannot fail is worse than none. `tools/check_regressions.py` holds one named case
per silent failure this project has had. Both are repo tools; neither ships.

`tools/check_langs.py` is the one to run after touching **any** extractor. Each supported language
has a fixture under `tests/fixtures/langs/<lang>/` — a store, a service calling it *through a
declared field*, a route, and a test file — and a row of expectations in `expected.json`. The
**edges** are the assertion that matters: nodes alone only prove the grammar loaded, an edge proves
receiver resolution worked. `--update` rewrites the expectations from reality, which is how they
were recorded in the first place, and will just as happily bless a regression — read its diff.

Fixtures live outside `sample_src/` on purpose: that directory ships to users and its numbers are
pinned by the prose block above, so every language added there means rewriting all of it by hand.
A fixture costs one directory and one row. `tests/fixtures/ts_imports/` is not a language row:
it is a minimal Next.js app pinning import resolution and file conventions, asserted by
`check_regressions.py` r42. Current expectations, all asserted:

| Language | Nodes | Edges | Routes | Test node |
| --- | --- | --- | --- | --- |
| python | 8 | 3 | 1 | yes |
| java | 6 | 3 | 1 | yes |
| csharp | 6 | 3 | 1 | yes |
| go | 7 | 3 | 1 | yes |
| javascript | 6 | 3 | 1 | yes |
| typescript | 6 | 3 | 1 | yes |
| kotlin | 6 | 3 | 1 | yes |
| rust | 6 | 3 | 1 | yes |
| swift | 5 | 2 | 0 | yes |
| scala | 5 | 2 | 0 | yes |
| groovy | 5 | 2 | 0 | yes |
| dart | 5 | 2 | 0 | yes |
| c | 5 | 2 | 0 | yes |
| cpp | 5 | 2 | 0 | yes |
| ruby | 7 | 2 | 0 | yes |
| php | 6 | 2 | 0 | yes |
| elixir | 5 | 2 | 0 | yes |
| django *(route table)* | 6 | 1 | **5** | no |
| rails *(route table)* | 5 | 1 | **5** | no |
| laravel *(route table)* | 5 | 1 | **5** | no |
| phoenix *(route table)* | 5 | 1 | **5** | no |

The eleven phase-7 rows have no controller where the language's route shape is read elsewhere
(Ruby, PHP, Elixir route *tables* are phase 8) or not at all (Swift, Scala, Dart, C, C++ -- a
stated boundary in the README), hence 2 edges and 0 routes. Ruby's 2 edges are the honest
sparse case: `@store.save` is dropped (an instance variable carries no type) while the
same-class `validate` call and the test's `WidgetService.new(...)` call are kept.

Each also asserts every node's **line and doc**, and each fixture carries 2-, 3- and 4-byte UTF-8
before its nodes plus one non-ASCII node name (`größe`) — phase 6b, so a byte offset applied to
decoded text cannot shift a name silently. And each asserts every node's **metrics**
(complexity, depth, params); each fixture's `grade` is counted by hand in its own comment —
complexity 6, depth 2, 2 params, in all six — so that row is checked against a person rather than
only against the recorder (phase 6a).

TypeScript's 3 edges used to be **0**: JS/TS matched calls by name only, so JavaScript's bare
function calls linked and TypeScript's `new WidgetStore().save()` did not. The receiver is kept
now, so a call resolves wherever the source states the class. What still drops is a receiver with
no stated type -- `other.save()` on an untyped parameter -- which is why a JS/TS node that drops
one earns `name-matched`, and why `tools/check_regressions.py` r34 asserts both halves: the four shapes that
resolve, and the untyped one that must not.

For `templates/viewer.html`, extract the inline `<script>` and parse it as a **classic script**
(`new vm.Script(code)`) — `node --check` wraps input in a CommonJS function, so it accepts top-level
`return` that a browser would reject. Then load `data/explorer.html` in a browser and exercise:
map switch, all seven views, explorer filter, blast toggle, tab drill-through.

The in-app preview pane **does** run the page's own script (verified 2026-09-11; an earlier note
here said it did not). **Do not re-run it with `(0, eval)(document.scripts[1].textContent)`.** An
indirect eval keeps the app's top-level `let`/`const` private to itself while its `function`s
overwrite the page's, so you get a second, *shadow* instance: handlers update the shadow's
`nodes`/`EDGES` while a probe reads the page's untouched originals. In phase 3 that produced a
convincing fake bug — the Tests checkbox "doing nothing" — which a clean probe then disproved.
Probe in the page's own scope by bare name instead: `nodes.length`, `EDGES.length`,
`selectNode(id)`, `setView(v)`, `el("reset").click()`.

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

### 5. Push the work into a script, not into the context
The skill exists because deterministic scripts are cheaper than an LLM reading files — and that
applies to *building* it too. Before answering a question about this codebase by reading source,
ask whether a script (or an existing tool: `git`, `python -c`, the skill's own commands) can
produce the answer once, for every future session.

- Reach for a script or an existing tool first; write ad-hoc analysis in the terminal, not in
  prose you would have to re-derive next time.
- If you find yourself reading many files to answer one question, that question wants a script.
- The runtime rule still stands: the skill ships the standard library plus the tree-sitter wheels
  constraint 1 names, and **nothing else**. "Use a library" means use what is already on the
  machine while developing, never add a dependency to the skill.
- A new script pays for itself the second time it runs. A one-off shell pipeline is fine; copy it
  into `docs/USAGE.md` if it will be wanted again.

### 6. Keep the docs in the same commit
Every document in this repo describes the skill to some reader. When behavior changes, they all
move with it — in the same commit, not in a follow-up that never comes.

There are **two disciplines**, and confusing them destroys the two files whose entire value is
that nobody rewrites them.

**Mirror current truth** — rewrite freely, so the file matches how the skill behaves *today*:

| File | Reader | Goes stale when |
| --- | --- | --- |
| `CLAUDE.md` | the next session working on the skill | the pipeline, script inventory, layout, constraints, colour/layout rules or the expected-numbers block change |
| `SKILL.md` | the agent using the skill | a command or an operating rule changes |
| `README.md` | a human evaluating/installing it | features, language table, requirements or the structure tree change |
| `docs/USAGE.md` | a human running it by hand | any command's form or flags change |
| `templates/TAXONOMY.md` | anyone adding a field value | a `kind`/`layer`/severity/grade value changes |
| `docs/ARCHITECTURE_GUIDE.{html,md}` | someone learning how the 29 scripts fit together | a script is added/renamed/moved, an inter-script call changes, or a function it names by hand is renamed |
| `docs/ARCHITECTURE_GUIDE.th.html` | the same reader, **in Thai** | the English guide changes — it is a translation, so it goes stale silently |

`ARCHITECTURE_GUIDE.html` is **one flowchart**, deliberately: BUILD (parses source, rewrites
artifacts) and QUERY (reads artifacts, never opens a source file), with `check` as the hinge
between them. It carried three overlapping taxonomies of the same six commands until 2026-09-12 —
5 "scenario" diagrams, 7 "execution flows" and 3 "operational scenarios", in which *Flow 1* meant
two different things. If a command needs explaining, it becomes a chip that opens its script
sequence in the existing sidebar (`COMMANDS_DATA` / `openCommand()`); **it does not become a
second diagram.** Both files name functions by hand and nothing checks them — eight were invented
before anyone noticed (finding #12).

`ARCHITECTURE_GUIDE.th.html` is the Thai translation of the `.html`, structurally identical —
same ids, same classes, same handlers — so a structural change must be made in **both**, and
`fc-box` / `fc-cmd-chip` / `fc-phase` counts are expected to match exactly between them. Two
house rules govern the Thai text -- they came from `docs/PRESENTATION.html`, the Thai slide deck
removed on 2026-09-16, and outlived it: **every technical identifier stays in English**
(script and function names, `kind`/`layer` values, algorithm names like *Winnowing* and *Tarjan's
SCC*, CLI flags — Thai is the connective prose around them), and **fonts are system-only**
(`IBM Plex Sans Thai`, `Noto Sans Thai`, `Leelawadee UI`, `Sarabun`, Tahoma) at
`line-height: 1.85`, because the page must open offline. Nothing may add a webfont `@import`.

The one deliberate difference: the Thai file ends with a **judge Q&A bank** (`#judge-qa`, after
the script cards) that the English file does not have. It is rehearsal material for the Thai
presentation, not part of the guide's structure, so it uses only `qa-*` classes and the `fc-*`
counts above still match. Its answers quote numbers and finding statuses by hand — when the
expected-numbers block, a check count or a ROADMAP finding changes, grep the `QA.push` blocks for
the old value in the same commit.

**Append, never revise** — these are records of what was actually done and thought at the time;
editing them to match the present is the one way to make them worthless:

| File | Discipline |
| --- | --- |
| `docs/PROJECT_HISTORY.md` | extend with new phases; never rewrite a past entry to agree with the present |
| `docs/prompt.md` | append the turn verbatim at the end of every turn (principle 8) |

**This file is not exempt.** `CLAUDE.md` describes the repo to its next session, so when the repo
changes, `CLAUDE.md` changes in the same commit. It has drifted before precisely because it was
the one doc outside its own rule — its pipeline diagram lost `brief` and nobody noticed.

A new script also needs: a docstring saying what it is and why, a line in the README structure
tree **and** in this file's script layout, a numbered command in `SKILL.md` if the agent should
call it, and its command form in `docs/USAGE.md`.

The mechanical half of this rule is checked, so it cannot quietly rot:

```bash
python tools/check_docs.py
```

It verifies that every script is listed in `README.md` and named in `CLAUDE.md`, that every
`scripts/...` path quoted in any doc actually exists, and that every `kind`/`layer` value in
`taxonomy.py` is documented in `TAXONOMY.md`. It deliberately checks facts, never prose — keeping
the *words* honest is still the writer's job.

### 7. Fix what you find, or write it down — never just mention it
Implementing one thing surfaces others: a stale claim in a tooltip, a number that contradicts a
doc, an artifact that is not as deterministic as the constraint says. Saying so in a chat reply
and moving on is the one option that is always wrong — the observation is gone the moment the
session ends.

Two outcomes, and which one applies is decided by whether a person has to choose something:

- **Fixable without a decision — fix it now**, in the same commit, and say so. A claim that is
  simply false, a message that misdiagnoses, an orphan your own change created: there is one right
  answer, so asking for it is just latency. Principle 3 still binds — fix the thing you found, not
  its neighbourhood.
- **Needs a judgement call — record it in `docs/ROADMAP_PLAN.md`** under *Found while
  implementing*, with what it is, why it is not obviously fixable, and a recommendation. It is
  reviewed with the phase, not mid-flight. Anything that changes output format, drops a
  user-visible field, or trades one guarantee for another belongs here.

The test for which bucket: *if I fix this my way and the user disagrees, have I destroyed
something?* If yes, write it down. If no, fix it.

### 8. Log every exchange to `docs/prompt.md`
This repo keeps a running transcript of its own construction. **At the end of every turn, append
that turn to `docs/prompt.md`** — the user's prompt verbatim, then what you did and said.

```markdown
## [N] YYYY-MM-DD — <short title>

**Prompt**
> <the user's message, verbatim>

**Response**
<what you did: decisions made, files touched, commands run, what you found, what you told them>
```

Rules that keep the log worth having:

- **Append, never rewrite.** Earlier entries are the record of what was actually thought at the
  time; correcting them retroactively destroys the only reason to keep it.
- **Write it contemporaneously**, at the end of the turn, while the reasoning is still exact. A
  transcript reconstructed later is a summary, and should say so.
- **Append it before you commit, never after.** The entry is part of the change, so it belongs in
  the same commit as the work it describes — `git add docs/prompt.md` alongside everything else. A
  log written after the push is a second commit that nobody makes, which is how turns go
  unrecorded; and even when it does land, the entry is then separated from the diff it explains.
  If a turn ends without a commit, the entry is still appended — the trigger is the end of the
  turn, not the commit.
- **Record the reasoning and the misses**, not just the diff — why an approach was chosen, what a
  verification actually returned, and anything that turned out wrong. Git already stores the diff;
  the log's value is everything git cannot show.
- **Number entries sequentially** and keep them in chronological order.
- It is a plain log, not a doc for a reader: no need to keep it in sync with behavior the way
  principle 6 requires of `SKILL.md` / `README.md` / `docs/USAGE.md`.
