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
    r"|\bunittest\.TestCase\b|^\s*import\s+pytest\b", re.M)         # Python
TEST_CONTENT_BYTES = 8192


def is_test_path(path: str) -> bool:
    """True when a path follows any language's test-file convention."""
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
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

# Decorators / patterns that mark a route handler (HTTP endpoint).
ROUTE_DECORATOR_RE = re.compile(r"route|get|post|put|patch|delete|mapping|endpoint", re.I)


def infer_layer(name: str, decorators=(), bases=()) -> str:
    haystack = " ".join([name, *decorators, *bases])
    for pattern, layer in LAYER_RULES:
        if pattern.search(haystack):
            return layer
    return "unknown"
