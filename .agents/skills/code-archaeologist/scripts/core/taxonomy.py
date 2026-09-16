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
    # Not `handler`: in Spring a `MasterDataUploadHandler` is a strategy a service
    # calls, and on a real repository that word turned 24 service->handler calls into
    # "layer violations". A handler that really serves requests still reaches
    # `controller` through its route, its file stem or its annotation.
    (re.compile(r"controller|route|resource|endpoint", re.I), "controller"),
    (re.compile(r"service|usecase|manager", re.I), "service"),
    # A short word must not match a longer one that means something else: `repo` inside
    # `PnoDataReportMail`, `store` inside `StoredFileDto`, `api` inside `Rapid`. On a real
    # repository that put 7 classes in `repository` -- and because this rule runs before
    # `model`, `SetdatNgReportDto` lost its `Dto` -- which then fabricated the report's only
    # layer violation. `(?![a-z])` ends the word where CamelCase or a separator ends it (r78).
    (re.compile(r"repository|repo(?![a-z])|dao(?![a-z])|store(?![a-z])|mapper", re.I), "repository"),
    (re.compile(r"model|entity|schema|dto|record(?![a-z])", re.I), "model"),
    (re.compile(r"client|gateway|adapter|api(?![a-z])", re.I), "client"),
    (re.compile(r"config|settings|env", re.I), "config"),
    (re.compile(r"component|view|page|screen|widget", re.I), "ui"),
]
# Annotations that *declare* a layer, checked before any name rule: a class name is
# a guess, `@Service` is a statement. Exact names only.
ANNOTATION_LAYERS = {
    "RestController": "controller", "Controller": "controller", "ApiController": "controller",
    "ControllerAdvice": "controller", "RestControllerAdvice": "controller",
    "Service": "service",
    "Repository": "repository", "Mapper": "repository",
    "Entity": "model", "Table": "model", "Document": "model", "Embeddable": "model",
    "Configuration": "config", "ConfigurationProperties": "config",
}
# Stereotypes that say "a bean" and nothing about which layer. Kept out of the name
# rules, where Spring's `@Component` matched `component` and made a service `ui`.
NEUTRAL_ANNOTATIONS = frozenset({"Component"})

LAYERS = [
    "controller", "service", "repository", "model", "client",
    "config", "ui", "test", "function", "module", "unknown",
]

# Allowed `kind` values (what the node physically is).
KINDS = ["class", "interface", "abstract", "method", "function", "module", "endpoint", "component", "test"]
# What a class node can be (structure map): the source states it -- `interface`, `trait`,
# `protocol`, an `abstract` modifier, `abc.ABC` -- and it decides which way a base link reads.
CLASS_KINDS = ("class", "interface", "abstract")

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
# Deliberately *not* here: `target`, `out`, `coverage`, `vendor`, `data` -- each is also a
# real source directory name in some repositories, and skipping source is the worse
# mistake. Only names nobody writes code into by hand are listed. `data` was listed
# from the start, for this skill's own output folder, and hid a Next.js route segment
# (`app/[projectId]/data/[type]/page.tsx`) with six files on a real repository; an
# installed skill copy is skipped by `_is_skill_copy` instead.
SKIP_DIRS = frozenset({
    ".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", "dist", "build",
    ".next", ".nuxt", ".svelte-kit", ".angular", ".turbo", ".parcel-cache", ".gradle",
    ".dart_tool",
})


def source_dirs(dirpath: str, dirs) -> list[str]:
    """The children of `dirpath` a source walk should enter.

    Not SKIP_DIRS, and not an installed copy of this skill: a project that installs it
    at `.claude/skills/code-archaeologist/` would otherwise graph the skill's own
    scripts as part of the project -- orphans, dead files and untested nodes that
    belong to neither. Only *children* are tested, so `--src <skill>` still graphs it.
    """
    return [d for d in dirs if d not in SKIP_DIRS
            and not _is_skill_copy(os.path.join(dirpath, d))]


def _is_skill_copy(path: str) -> bool:
    return (os.path.isfile(os.path.join(path, "scripts", "archaeologist.py"))
            and os.path.isfile(os.path.join(path, "SKILL.md")))

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
#   overloads           a call here names an overload set and no single overload
#                       fits the arguments the source states, so it was dropped
#                       (`ambiguous`); or an edge lands on a node that still folds
#                       several signatures because their types could not be read
#   name-matched        a call here went through a receiver whose type the source
#                       does not state, so it was dropped -- and the graph defines
#                       that name (`untyped`), so a link may be missing. It was a
#                       language label (every JS/TS, Ruby, PHP, Elixir and Groovy
#                       node) until finding #25; a node now earns it, in any language.
PRECISION_REASONS = ("interface-dispatch", "overloads", "name-matched")

PRECISION_CAVEAT = (
    "Call edges are a lower bound in every language: a call is only drawn when the "
    "receiver's type can be read from the source, and anything else is dropped "
    "rather than guessed."
)

PRECISION_NOTES = {
    "interface-dispatch": ("calls through an interface stop at its declaration -- "
                           "which implementation runs is not knowable from the source"),
    "overloads": ("a call to an overloaded method could not be matched to one overload "
                  "from the arguments the source states, so it was dropped"),
    "name-matched": ("a call through an object whose class the source does not state was "
                     "dropped, and the graph defines that name (see `untyped`)"),
}


def precision_of(node: dict, targets: list[dict]) -> list[str]:
    """Named precision losses for one node, given the nodes its edges point at.

    Order follows `PRECISION_REASONS` so the field is deterministic (constraint 2).
    An empty list means nothing *nameable* was lost -- never that the edges are
    complete, which is what `PRECISION_CAVEAT` exists to say.
    """
    reasons = set()
    if node.get("untyped"):
        reasons.add("name-matched")
    if node.get("ambiguous"):
        reasons.add("overloads")
    for t in targets:
        if t.get("declaration"):
            reasons.add("interface-dispatch")
        if len(t.get("signatures") or ()) > 1:
            reasons.add("overloads")
    return [r for r in PRECISION_REASONS if r in reasons]


# --- link direction ----------------------------------------------------------------
# Inheritance links are stored the way they read -- `FlatRate.price -> PricingRule.price`
# -- but a call to the base runs the subclass, so every walk over callers and callees
# (traces, impact, orphans, search, context) reads them backwards. One definition, so no
# walker flips one on its own, and none of them is a call: cycles, layers and coupling
# ignore all three.
#   implements  a class fills in an interface; a method fills in a declaration (no body)
#   extends     a class inherits a class, or an interface an interface (structure map)
#   overrides   a method replaces a base method that has a body of its own (flow map)
INHERITANCE_LINKS = frozenset({"implements", "extends", "overrides"})
REVERSED_LINKS = INHERITANCE_LINKS


def call_direction(source: str, target: str, link_type: str) -> tuple[str, str]:
    """(from, to) as a caller-to-callee walk follows this link."""
    return (target, source) if link_type in REVERSED_LINKS else (source, target)


# --- what a language calls a decoration ------------------------------------------
# The graph field is one (`decorators`) because all three producers read the same
# thing: whatever is written above a declaration. The *word* is not one. Java,
# Kotlin and Groovy have annotations; C# and Rust have attributes; only Python and
# JS/TS (Nest) have decorators. A note heading a Lombok `@Data` "Decorators" names
# it in a language that does not have the concept, so the heading asks here.
# Languages with no such concept at all (Go, C) never fill the list; they take the
# default and print an empty section.
DECORATION_TERMS = {
    "java": "Annotations", "kotlin": "Annotations", "groovy": "Annotations",
    "scala": "Annotations", "dart": "Annotations",
    "csharp": "Attributes", "rust": "Attributes", "swift": "Attributes",
    "php": "Attributes", "elixir": "Attributes",
}


def decoration_term(lang: str) -> str:
    """What `lang` calls the things written above a declaration, as a note heading."""
    return DECORATION_TERMS.get(lang, "Decorators")


# Decorators / patterns that mark a route handler (HTTP endpoint).
ROUTE_DECORATOR_RE = re.compile(r"route|get|post|put|patch|delete|mapping|endpoint", re.I)


# The folder states the layer where the class name does not: `service/pnodata/PnoDataJob.java`
# is a service, `response/masterdata/` holds models, `properties/` holds config. Read **only**
# as a fallback -- an annotation or the name always wins -- and only on an exact folder name,
# nearest folder first, never as a substring: a whole application under `api/` is not six
# hundred clients, which is the mistake `LAYER_RULES` itself made with `repo` (r78). Words that
# name no layer in this taxonomy (`util`, `exception`, `constant`, `integration`) are absent on
# purpose: `unknown` is the honest answer for them (r79).
PATH_LAYERS = {
    "controller": "controller", "controllers": "controller", "resource": "controller",
    "resources": "controller", "route": "controller", "routes": "controller",
    "service": "service", "services": "service", "usecase": "service", "usecases": "service",
    "repository": "repository", "repositories": "repository", "dao": "repository",
    "mapper": "repository", "mappers": "repository",
    "model": "model", "models": "model", "entity": "model", "entities": "model",
    "dto": "model", "dtos": "model", "request": "model", "requests": "model",
    "response": "model", "responses": "model", "payload": "model", "payloads": "model",
    "schema": "model", "schemas": "model",
    "client": "client", "clients": "client", "gateway": "client", "gateways": "client",
    "config": "config", "configs": "config", "configuration": "config",
    "properties": "config", "settings": "config",
    "component": "ui", "components": "ui", "view": "ui", "views": "ui",
    "page": "ui", "pages": "ui",
}


def layer_from_path(path: str) -> str:
    """The layer this file's folders state, nearest folder first, or ""."""
    folders = [p.lower() for p in re.split(r"[\\/]+", path)[:-1]]
    for folder in reversed(folders):
        if folder in PATH_LAYERS:
            return PATH_LAYERS[folder]
    return ""


def infer_layer(name: str, decorators=(), bases=(), path: str = "") -> str:
    for deco in decorators:
        if deco in ANNOTATION_LAYERS:
            return ANNOTATION_LAYERS[deco]
    haystack = " ".join([name, *(d for d in decorators if d not in NEUTRAL_ANNOTATIONS), *bases])
    for pattern, layer in LAYER_RULES:
        if pattern.search(haystack):
            return layer
    return layer_from_path(path) or "unknown"


# --- called by a framework -------------------------------------------------------
# Code the framework invokes has no caller in any graph, so without a named reason it
# is reported dead: on a real Spring + Next.js repository that was every filter,
# scheduled job, bean factory and aspect. A node that matches carries `entry`, naming
# the reason, and analyze.find_orphans never calls it dead. No edge is invented.
FRAMEWORK_ENTRY = frozenset({
    "Scheduled", "Bean", "EventListener", "TransactionalEventListener", "PostConstruct",
    "PreDestroy", "ExceptionHandler", "Around", "Before", "After", "AfterReturning",
    "AfterThrowing", "KafkaListener", "RabbitListener", "JmsListener",
    # Called through its base type -- a filter's doFilterInternal, an interface impl --
    # which is dispatch the graph deliberately does not resolve.
    "Override",
})


# Annotations that say a framework *builds this class and calls into it*: the application
# class holds `main`, a `@Configuration` runs its `@Bean` methods, an aspect's advice is
# woven in, an advice class is handed exceptions. Deliberately **not** `@Component` /
# `@Service` / `@Repository`: Spring instantiates those too, but one nothing injects runs
# nothing, and sparing every one of them would end dead-class detection for a whole Spring
# application. When a framework really does call into such a class, one of its own methods
# says so (`@Scheduled`, `@Bean`, `@EventListener`), which is the second rule below.
CLASS_ENTRY_ANNOTATIONS = frozenset({
    "SpringBootApplication", "Configuration", "Aspect", "ControllerAdvice", "RestControllerAdvice",
})


def container_entry(annotations, method_entries=()) -> str:
    """Why a framework builds this class and calls into it, or "" -- an annotation that
    states it (`@Configuration`, spelled as `framework_entry` spells one), else the first
    `entry` one of its own methods carries."""
    for anno in annotations:
        if anno in CLASS_ENTRY_ANNOTATIONS:
            return f"@{anno}"
    return next((why for why in method_entries if why), "")


def framework_entry(annotations, name: str = "", overrides: bool = False) -> str:
    """Why a framework calls this method, or "" -- `@Scheduled`, `override`, `main`."""
    for anno in annotations:
        if anno in FRAMEWORK_ENTRY:
            return f"@{anno}"
    if overrides:
        return "override"
    return "main" if name in ("main", "Main") else ""


# Next.js calls exported functions by file convention. Applied only inside a Next app
# (a folder holding next.config.* or a package.json that depends on `next`), so a
# `page.tsx` in any other framework is never exempted.
NEXT_APP_DEFAULTS = frozenset({"page", "layout", "template", "loading", "error",
                               "global-error", "not-found", "default"})
NEXT_ROUTE_VERBS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
NEXT_APP_EXPORTS = frozenset({"generateMetadata", "generateStaticParams", "generateViewport"})
NEXT_PAGES_EXPORTS = frozenset({"getServerSideProps", "getStaticProps", "getStaticPaths"})


def next_entry(rel: str, name: str, default: bool) -> str:
    """The convention under which Next.js calls an exported function, or "".

    `rel` is the file's path from the Next app root; `default` says whether the
    function is the file's default export.
    """
    parts = rel.replace("\\", "/").split("/")
    if parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    stem = os.path.splitext(parts[-1])[0]
    if parts[0] == "app" and len(parts) > 1:
        if default and stem in NEXT_APP_DEFAULTS:
            return f"next:{stem}"
        if stem == "route" and name in NEXT_ROUTE_VERBS:
            return "next:route"
        if name in NEXT_APP_EXPORTS:
            return f"next:{name}"
    elif parts[0] == "pages" and len(parts) > 1:
        if default:
            return "next:api" if parts[1] == "api" else "next:page"
        if name in NEXT_PAGES_EXPORTS:
            return f"next:{name}"
    elif len(parts) == 1:
        if stem == "middleware" and (default or name == "middleware"):
            return "next:middleware"
        if stem == "instrumentation" and name == "register":
            return "next:instrumentation"
    return ""
