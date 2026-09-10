#!/usr/bin/env python3
"""grammars.py — which tree-sitter grammars are installed, and a parser for each.

One answer to "can this language be parsed here", for everyone who needs it. The
grammars are separate wheels, installed on demand rather than all up front, so a
repo that is pure Go never pays for Scala -- which means "what can be parsed" is
a property of the machine, not of the skill, and every pass has to agree on it.

Three callers, for three different reasons:

  extract/    picks a parser and skips files whose grammar is absent
  manifest.py records the installed set, so a graph that is smaller because a
              wheel was missing does not look like a graph of a smaller codebase
  brief.py    tells the agent which languages were skipped

That middle one is the subtle one. The same repo on two machines with different
grammars installed yields different graphs, which would break determinism if the
grammar set were invisible; recording it turns a silent difference into a
reported staleness.

The wheels live in `<skill>/vendor`, put on `sys.path` by `paths.py` -- the one
skill module `core/` imports, because it sits below the categories and knows
where the skill's own files are. Installing there rather than into the user's
Python is the same bargain `@babel/parser` already takes in `<skill>/node_modules`:
the dependency cannot collide with anything the user runs, and deleting the skill
folder removes it. A machine that installed the wheels straight into site-packages
still works -- the vendor entry is a preference, not a requirement.

Importing this module never imports a grammar. Loading is lazy and cached, so
listing what is available costs one `find_spec` per language.

Zero external dependencies at import time. Python 3.10+.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import VENDOR_DIR  # noqa: E402  (also puts sibling script dirs on sys.path)

# Our language key (taxonomy.LANG_BY_EXT values) -> the wheel that provides it.
# A language is supported when it is in this table AND its wheel is installed AND
# extract/ has a query for it; this table answers only the middle question.
GRAMMAR_MODULES = {
    "java": "tree_sitter_java",
    "go": "tree_sitter_go",
    "csharp": "tree_sitter_c_sharp",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "tsx": "tree_sitter_typescript",
}

# `pip install` name per module, for the message a user is asked to run.
PIP_NAMES = {
    "tree_sitter_java": "tree-sitter-java",
    "tree_sitter_go": "tree-sitter-go",
    "tree_sitter_c_sharp": "tree-sitter-c-sharp",
    "tree_sitter_javascript": "tree-sitter-javascript",
    "tree_sitter_typescript": "tree-sitter-typescript",
}

# The factory to call on the module, when it is not the usual `language()`.
# `tree-sitter-typescript` ships two grammars in one wheel, and they are not
# interchangeable: `.tsx` will not parse under `language_typescript` (`<` is
# ambiguous between a type argument and a JSX tag) and vice versa.
LANGUAGE_FACTORY = {
    "typescript": "language_typescript",
    "tsx": "language_tsx",
}

_parsers: dict[str, object] = {}
_runtime: list = []  # [module | None, error message] -- one import attempt, cached


def runtime_available() -> bool:
    """Is the `tree-sitter` runtime itself installed?

    A spec check, not an import: this is asked once per language while listing
    what is available, and importing a native extension to answer it would make
    listing cost more than parsing. Whether it actually *loads* is `runtime()`.
    """
    return importlib.util.find_spec("tree_sitter") is not None


def runtime():
    """The imported `tree_sitter` module, or None with `runtime_error()` set.

    Split from `runtime_available()` because the two can disagree, and the way
    they disagree is nasty. The runtime wheel is built for one interpreter minor
    version (`cp314-cp314-win_amd64`); the grammars are `abi3` and are not. So a
    user who upgrades Python keeps a `vendor/` directory that still *looks*
    installed -- `find_spec` finds it -- and fails at the `import`. Left to raise,
    that surfaces as a traceback out of whichever pass happened to parse first.
    Caught here, it is one sentence naming the fix.
    """
    if not _runtime:
        try:
            _runtime.extend([importlib.import_module("tree_sitter"), ""])
        except ImportError as exc:
            where = "vendored " if _under_vendor(_module_path("tree_sitter")) else ""
            _runtime.extend([None, (
                f"tree-sitter runtime found but not loadable ({exc}). The {where}wheel is built"
                f" for one Python version; this is {_pyver()}. Re-run the install to rebuild it.")])
    return _runtime[0]


def runtime_error() -> str:
    """Why the runtime would not load, or "" when it did (or was never there).

    Callers print this *instead of* the missing-grammar hint. Reporting a broken
    runtime as an absent grammar would send the user to install a wheel they
    already have, which is worse than saying nothing.
    """
    runtime()
    return _runtime[1]


def _pyver() -> str:
    return f"Python {sys.version_info.major}.{sys.version_info.minor}"


def _module_path(mod: str) -> str:
    """Where `mod` would be imported from, without importing it."""
    try:
        spec = importlib.util.find_spec(mod)
    except (ImportError, ValueError):
        return ""
    if spec is None:
        return ""
    if spec.origin and spec.origin != "built-in":
        return spec.origin
    return (spec.submodule_search_locations or [""])[0]


def _under_vendor(path: str) -> bool:
    if not path:
        return False
    try:
        return os.path.commonpath([os.path.abspath(path), VENDOR_DIR]) == VENDOR_DIR
    except ValueError:  # different drives on Windows
        return False


def origins() -> dict[str, str]:
    """Where each installed piece resolved from: "vendored" or "site-packages".

    Two copies of a grammar can be installed at once -- someone who ran the old
    plain `pip install` and then a vendored one has both, and `sys.path` order
    silently decides which is used. That is a version difference with no visible
    cause, so the answer to "which one am I actually running" is reported rather
    than inferred.
    """
    out: dict[str, str] = {}
    for mod in ["tree_sitter"] + [GRAMMAR_MODULES[l] for l in available()]:
        path = _module_path(mod)
        if path:
            out[mod] = "vendored" if _under_vendor(path) else "site-packages"
    return out


def have(lang: str) -> bool:
    """Can this machine parse `lang` -- grammar *and* runtime?

    Both, deliberately: a grammar wheel without the runtime parses nothing, so
    reporting it as present would let a language be skipped without appearing in
    the skipped list.
    """
    mod = GRAMMAR_MODULES.get(lang)
    return bool(mod) and runtime_available() and importlib.util.find_spec(mod) is not None


def available() -> list[str]:
    """Every language this machine can currently parse, sorted."""
    if not runtime_available():
        return []
    return sorted(lang for lang in GRAMMAR_MODULES if have(lang))


def missing(langs) -> list[str]:
    """Of `langs`, the ones we know a wheel for but do not have installed."""
    return sorted({l for l in langs if l in GRAMMAR_MODULES and not have(l)})


def install_hint(langs) -> str:
    """The exact command to enable `langs` -- named, never a vague 'install it'.

    Includes the runtime when that is what is missing, so the message is one
    command a user can paste rather than one that fails and needs a second.

    It installs into `<skill>/vendor`, never into the user's environment, and the
    flags are load-bearing rather than decoration: `--only-binary :all:` fails
    loudly instead of trying to compile a grammar from source, and
    `--no-cache-dir` keeps pip from writing the wheels to a cache outside the
    skill folder -- which is the difference between "delete the skill and nothing
    is left" being true and being nearly true.
    """
    # Deduplicated by *package*, not by language: one wheel can provide several
    # (`tree-sitter-typescript` ships both `typescript` and `tsx`), and naming it
    # twice in a command the user is meant to paste looks like a mistake.
    pkgs: list[str] = []
    for lang in sorted(set(langs)):
        pkg = PIP_NAMES.get(GRAMMAR_MODULES.get(lang, ""), "")
        if pkg and pkg not in pkgs:
            pkgs.append(pkg)
    if not pkgs:
        return ""
    if not runtime_available():
        pkgs.insert(0, "tree-sitter")
    return ("pip install --only-binary :all: --no-cache-dir"
            f" --target \"{VENDOR_DIR}\" {' '.join(pkgs)}")


def versions() -> dict[str, str]:
    """Installed grammar versions, for the manifest.

    A grammar release can rename node types, which makes a query match nothing
    and the language silently report zero nodes. Recording the version is what
    lets `check` call that out instead of absorbing it.
    """
    out: dict[str, str] = {}
    for lang in available():
        try:
            out[lang] = importlib.metadata.version(PIP_NAMES[GRAMMAR_MODULES[lang]])
        except Exception:
            out[lang] = "?"
    return out


def parser_for(lang: str):
    """A cached `tree_sitter.Parser` for `lang`, or None when it is unavailable."""
    if lang in _parsers:
        return _parsers[lang]
    ts = runtime() if have(lang) else None
    if ts is None:
        _parsers[lang] = None
        return None
    _parsers[lang] = ts.Parser(_language(ts, lang))
    return _parsers[lang]


def _language(ts, lang):
    """The `tree_sitter.Language` for `lang`, whichever factory its wheel uses."""
    grammar = importlib.import_module(GRAMMAR_MODULES[lang])
    return ts.Language(getattr(grammar, LANGUAGE_FACTORY.get(lang, "language"))())


def query(lang: str, source: str):
    """Compile a query string against `lang`'s grammar."""
    ts = runtime()
    return ts.Query(_language(ts, lang), source)
