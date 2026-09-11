#!/usr/bin/env python3
"""taxonomy.py — the single source of truth for graph/template field values.

Keeping the allowed `kind` and `layer` values in one place keeps them consistent
across the Python and JS/TS extractors and the Markdown templates. Every
`{{kind}}` / `{{layer}}` written into a page comes from these sets.

  layer  — architectural role of a node (controller, service, ...). Inferred
           from the entity name / decorators; falls back to "unknown".
  kind   — what the node physically is (class, function, method, module, ...).
"""
from __future__ import annotations

import os
import re

# Allowed `layer` values, with the name/decorator patterns used to infer them.
# First match wins.
LAYER_RULES = [
    # `route` rather than `router`, so order_routes.py and order_router.js -- the
    # same thing in two languages -- do not land in different layers.
    (re.compile(r"controller|handler|route|resource|endpoint", re.I), "controller"),
    (re.compile(r"service|usecase|manager", re.I), "service"),
    (re.compile(r"repository|repo|dao|store|mapper", re.I), "repository"),
    (re.compile(r"model|entity|schema|dto|record", re.I), "model"),
    (re.compile(r"client|gateway|adapter|api", re.I), "client"),
    (re.compile(r"config|settings|env", re.I), "config"),
    (re.compile(r"component|view|page|screen|widget", re.I), "ui"),
]
LAYERS = [
    "controller", "service", "repository", "model", "client",
    "config", "ui", "test", "function", "module", "unknown",
]

# Allowed `kind` values (what the node physically is).
KINDS = ["class", "method", "function", "module", "endpoint", "component", "test"]

# --- languages -------------------------------------------------------------------
# One answer to "what language is this file", for the file census (metrics.py) and
# for the `lang` on every graph node. The exact-tier extractors label their nodes
# themselves -- Python nodes are `py` and JS/TS nodes are all `js`, coarser than the
# census -- but everything reading a file off disk asks here.
LANG_BY_EXT = {
    ".py": "py", ".js": "js", ".jsx": "jsx", ".ts": "ts", ".tsx": "tsx",
    ".mjs": "js", ".cjs": "js", ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".go": "go", ".rs": "rust", ".cs": "csharp", ".rb": "ruby", ".php": "php",
    ".swift": "swift", ".scala": "scala", ".groovy": "groovy", ".dart": "dart",
    ".ex": "elixir", ".exs": "elixir", ".c": "c", ".cc": "cpp", ".cpp": "cpp",
    ".h": "c", ".hpp": "cpp",
}


def lang_of(path: str) -> str:
    """Language name for a path, or "other" when the extension is unknown."""
    return LANG_BY_EXT.get(os.path.splitext(path)[1].lower(), "other")

# --- what is not source -----------------------------------------------------------
# Directories no pass reads: VCS and tool state, dependencies, build output, and the
# caches frameworks regenerate while a dev server runs. One definition, because five
# copies had already drifted apart -- the JS/TS and Java-family extractors skipped
# `dist/` and `build/`, the Python builders and the freshness manifest did not -- and
# none skipped `.next/`: on a real Next.js repository 228 of 2,521 flow nodes were
# generated code, and the graph changed every time the dev server recompiled (found
# by tools/time_build.py's read-only guard, phase 9).
#
# Deliberately *not* here: `target`, `out`, `coverage`, `vendor` -- each is also a
# real source directory name in some repositories, and skipping source is the worse
# mistake. Only names nobody writes code into by hand are listed.
SKIP_DIRS = frozenset({
    ".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "data", "dist", "build",
    ".next", ".nuxt", ".svelte-kit", ".angular", ".turbo", ".parcel-cache", ".gradle",
    ".dart_tool",
})

# --- test code -----------------------------------------------------------------
# Test code is *not* dead code: a runner calls it, so nothing in the graph does.
# Detection is by convention, not by parsing, so it also holds for languages this
# skill cannot build a graph for (JUnit 5 / Spring Boot, Go, Rust, .NET, ...).

TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testing"}

# Java/Kotlin/C#/Scala/Swift/Groovy: OrderServiceTest.java, FooTests.kt, PaymentIT.java.
# Case-sensitive on purpose, so `latest.java` or `greatest.cs` are not tests.
TEST_SUFFIX_RE = re.compile(r"(Test|Tests|TestCase|TestCases|IT|ITCase|Spec|Specs)"
                            r"\.(java|kt|kts|cs|scala|groovy|swift)$")

# Everything else follows lowercase conventions.
TEST_FILE_RE = re.compile(
    r"^test_.*\.(py|dart)$"                             # test_orders.py
    r"|^conftest\.py$"                                  # pytest fixtures
    r"|_test\.(py|go|dart|rb|exs|ex|js|jsx|ts|tsx|cc|cpp|c|php)$"   # orders_test.go
    r"|_spec\.(rb|js|jsx|ts|tsx|exs)$"                  # orders_spec.rb
    r"|\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)$"         # orders.test.tsx
    r"|Test\.php$"                                      # PHPUnit: OrderTest.php
    r"|_test\.rs$", re.I)

# Frameworks that mark a file as a test from the inside, for files whose name says
# nothing. Checked against the head of the file only.
TEST_CONTENT_RE = re.compile(
    r"@(Test|ParameterizedTest|RepeatedTest|Nested|SpringBootTest|WebMvcTest|DataJpaTest"
    r"|TestConfiguration|QuarkusTest|MicronautTest)\b"  # JUnit 5 / Spring Boot / Quarkus
    r"|\[(TestMethod|TestClass|Fact|Theory|TestFixture)\]"          # .NET
    r"|#\[(test|cfg\(test\))\]"                                     # Rust
    r"|\bfunc\s+Test[A-Z]\w*\s*\(\s*\w+\s+\*testing\.T"             # Go
    r"|\buse\s+ExUnit\.Case\b|<\s*Minitest::Test\b|\bXCTestCase\b"   # Elixir, Ruby, Swift
    r"|\bextends\s+(?:\\?\w+\\)*TestCase\b|package:(?:flutter_)?test/"  # PHPUnit, Dart
    r"|\bunittest\.TestCase\b|^\s*import\s+pytest\b", re.M)         # Python
TEST_CONTENT_BYTES = 8192
# A graph node's `source` is "<path>:<line>"; the line is not part of the filename.
TEST_LINE_SUFFIX_RE = re.compile(r":\d+$")


def is_test_path(path: str) -> bool:
    """True when a path follows any language's test-file convention.

    Accepts a bare path *or* a graph node's `source`, which carries a `:line`
    suffix. That tolerance is not politeness, it is a bug fix: every flow node is
    keyed by `path:line`, so `is_test_path("api/user_test.go:12")` used to answer
    False and only a `tests/` **directory** could mark a node as test code. Every
    project that names its test files by convention instead -- `user_test.go`,
    `test_user.py`, `UserTest.java` -- had its tests silently classified as
    application code, which means `analyze.py` reported them as dead and
    `scan_security.py` scanned them.

    One caller already stripped the suffix by hand (`tests_map.py`) and another
    did not (`build_flow.py`), which is exactly the drift `taxonomy` exists to
    prevent: every pass must ask the same question and get the same answer.
    Found by the per-language fixtures, whose test files sit next to the code
    they test rather than in a `tests/` directory -- the shape the sample never
    had.
    """
    parts = path.replace("\\", "/").split("/")
    name = TEST_LINE_SUFFIX_RE.sub("", parts[-1])
    if TEST_DIRS.intersection(p.lower() for p in parts[:-1]):
        return True
    return bool(TEST_SUFFIX_RE.search(name) or TEST_FILE_RE.search(name))


def has_test_markers(full_path: str) -> bool:
    """True when the head of a file carries a test-framework marker (@Test, #[test], ...)."""
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
            return bool(TEST_CONTENT_RE.search(fh.read(TEST_CONTENT_BYTES)))
    except OSError:
        return False


def is_test_file(path: str, full_path: str | None = None) -> bool:
    """Convention first (free); only sniff the contents when a real path is given."""
    return is_test_path(path) or (bool(full_path) and has_test_markers(full_path))

# --- precision -----------------------------------------------------------------
# Every language this skill graphs resolves calls only as far as the source lets
# it, so **every** node's outgoing edges are a lower bound. That caveat is stated
# once, globally, by `PRECISION_CAVEAT` -- it used to be a per-node `approx: true`
# on Java/Go/C# alone, which was true when those three were read textually and
# became arbitrary once every language moved to tree-sitter.
#
# What survives per node is narrower and more useful: the cases where a specific
# loss can be *named*. `PRECISION_REASONS` is the closed set, and each one is
# derived from data already in the graph rather than from the language:
#
#   interface-dispatch  an outgoing edge stops at a `declaration: true` node, so
#                       which implementation actually runs is not knowable here
#   overloads           an outgoing edge lands on a node that folds several
#                       signatures into one id, so which one is called is ambiguous
#   name-matched        this node's language resolves calls by name only, so calls
#                       through an object were dropped (measured: the TypeScript
#                       fixture resolves 0 of 3 edges where the typed languages
#                       resolve 3 of 3)
PRECISION_REASONS = ("interface-dispatch", "overloads", "name-matched")

# Languages whose extractor matches call *names* rather than resolving a receiver.
# Ruby, PHP, Elixir and Groovy joined in phase 7: their source usually names no
# receiver type, so a call through an object is dropped unless one is written down.
NAME_MATCHED_LANGS = {"js", "ts", "jsx", "tsx", "ruby", "php", "elixir", "groovy"}

PRECISION_CAVEAT = (
    "Call edges are a lower bound in every language: a call is only drawn when the "
    "receiver's type can be read from the source, and anything else is dropped "
    "rather than guessed."
)

PRECISION_NOTES = {
    "interface-dispatch": ("calls through an interface stop at its declaration -- "
                           "which implementation runs is not knowable from the source"),
    "overloads": ("an overload set is folded into one node, so which signature is "
                  "called is ambiguous"),
    "name-matched": ("JS/TS, Ruby, PHP, Elixir and Groovy calls are matched by name, so a "
                     "call through an object with no declared type was dropped"),
}


def precision_of(node: dict, targets: list[dict]) -> list[str]:
    """Named precision losses for one node, given the nodes its edges point at.

    Order follows `PRECISION_REASONS` so the field is deterministic (constraint 2).
    An empty list means nothing *nameable* was lost -- never that the edges are
    complete, which is what `PRECISION_CAVEAT` exists to say.
    """
    reasons = set()
    if node.get("lang") in NAME_MATCHED_LANGS:
        reasons.add("name-matched")
    for t in targets:
        if t.get("declaration"):
            reasons.add("interface-dispatch")
        if len(t.get("signatures") or ()) > 1:
            reasons.add("overloads")
    return [r for r in PRECISION_REASONS if r in reasons]


# Decorators / patterns that mark a route handler (HTTP endpoint).
ROUTE_DECORATOR_RE = re.compile(r"route|get|post|put|patch|delete|mapping|endpoint", re.I)


def infer_layer(name: str, decorators=(), bases=()) -> str:
    haystack = " ".join([name, *decorators, *bases])
    for pattern, layer in LAYER_RULES:
        if pattern.search(haystack):
            return layer
    return "unknown"
