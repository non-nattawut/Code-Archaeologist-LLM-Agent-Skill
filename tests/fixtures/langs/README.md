# Per-language extraction fixtures

**Every language the skill claims to graph has a fixture here that proves it does.** Without one,
adding a grammar is an unverified claim — and the failure is silent: a language whose queries are
subtly wrong produces zero nodes, and a graph that is empty for want of a query looks exactly like
a graph of a small codebase.

Run them with:

```bash
python tools/check_langs.py            # every language
python tools/check_langs.py go java    # just these
```

Expectations live in `expected.json`, not in prose. Adding a language is one directory plus one
row there.

## Why these are not in `sample_src/`

The two have different jobs and the plan (`docs/ROADMAP_PLAN.md`, 2g) keeps them apart:

| | `sample_src/` | here |
| --- | --- | --- |
| Job | the readable worked example | prove extraction works |
| Ships to users | yes, via `package.json`'s `files` allowlist | no |
| Size | stays as it is | one small set of files per language |
| Expectations | `CLAUDE.md`'s expected-numbers block, in prose | a JSON table asserted by a script |

Every language added to `sample_src/` perturbs its node counts, edge counts, grades, orphan counts,
LOC totals and language mix — all of which are pinned by hand in `CLAUDE.md`. Fixtures here cost
one row.

## The shape, which is the same for every language

Deliberately minimal and deliberately identical, so a new language is a copy-and-translate rather
than a design exercise, and so the fixtures are comparable to each other:

1. **A store type with a method** — `WidgetStore.save`.
2. **A service that calls it through a declared field** — `WidgetService.place`. This is the point
   of the fixture: it exercises *receiver resolution*, not just parsing. A language whose grammar
   works but whose field-type rule is wrong still produces the two nodes and **not** the edge.
3. **A controller with a route** — `WidgetController.create`, `POST` on a `/widgets` path, in that
   language's mainstream framework.
4. **A test file** — so `taxonomy.is_test_file` is exercised per language, and the node it names
   gets `layer: test`.

That last one matters more than it looks: test detection is per-language convention (`_test.go`,
`*Test.java`, `[Fact]`, `test_*.py`), and it decides whether `analyze.py` calls a node dead code.

## What a fixture must assert

`expected.json` carries, per language: the node ids, the resolved call edges, the routes, which
nodes are `layer: test`, and each node's **line** and **doc**. **The edges are the load-bearing
part** — nodes alone only prove the grammar loaded.

**Every fixture carries non-ASCII before its nodes** — a comment and a string with 2-, 3- and
4-byte UTF-8 (`größe`, `寸法`, `📦`), a non-ASCII doc on the store's save, and one node with a
non-ASCII name (`größe`). tree-sitter reports byte offsets; slicing *decoded* text with one shifts
every name, line and doc after the first multi-byte character, silently. The `lines` and `docs`
columns are what catch it. A new fixture keeps all three.

For a dynamically typed language (none graphed yet — Ruby, PHP, Elixir, Lua) the fixture must
assert *sparseness*: nodes yes, edges few or none. That is what keeps the honest-limitations
section honest. A fixture that quietly returns zero edges and is never asserted is how that section
starts lying.
