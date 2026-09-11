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
Python means the dependency cannot collide with anything the user runs, and
deleting the skill folder removes it. A machine that installed the wheels
straight into site-packages still works -- the vendor entry is a preference, not
a requirement.

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
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "tsx": "tree_sitter_typescript",
    # Phase 7: every language the review passes already knew, now graphed too.
    "kotlin": "tree_sitter_kotlin",
    "rust": "tree_sitter_rust",
    "swift": "tree_sitter_swift",
    "scala": "tree_sitter_scala",
    "groovy": "tree_sitter_groovy",
    "dart": "tree_sitter_dart",
    "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp",
    "ruby": "tree_sitter_ruby",
    "php": "tree_sitter_php",
    "elixir": "tree_sitter_elixir",
}

# `pip install` name per module, for the message a user is asked to run.
PIP_NAMES = {
    "tree_sitter_java": "tree-sitter-java",
    "tree_sitter_go": "tree-sitter-go",
    "tree_sitter_c_sharp": "tree-sitter-c-sharp",
    "tree_sitter_python": "tree-sitter-python",
    "tree_sitter_javascript": "tree-sitter-javascript",
    "tree_sitter_typescript": "tree-sitter-typescript",
    "tree_sitter_kotlin": "tree-sitter-kotlin",
    "tree_sitter_rust": "tree-sitter-rust",
    "tree_sitter_swift": "tree-sitter-swift",
    "tree_sitter_scala": "tree-sitter-scala",
    "tree_sitter_groovy": "tree-sitter-groovy",
    "tree_sitter_dart": "tree-sitter-dart",
    "tree_sitter_c": "tree-sitter-c",
    "tree_sitter_cpp": "tree-sitter-cpp",
    "tree_sitter_ruby": "tree-sitter-ruby",
    "tree_sitter_php": "tree-sitter-php",
    "tree_sitter_elixir": "tree-sitter-elixir",
}

# The version every install asks for -- one table, read by `install_hint()`, by
# `--install`, and through that by `bin/cli.js`. A grammar release can rename node
# types, and a query written against the old names then matches nothing: the
# language silently reports zero nodes on every fresh install from that day on.
# Grammars are exact -- they are abi3 wheels, so an exact pin installs on any
# Python. The runtime is a range: its wheels are built per interpreter, so an
# exact pin would stop installing on the first Python released after it, and the
# node-type names this skill depends on come from the grammars, not the runtime.
# Bump a pin only together with a green `tools/check_langs.py`.
PINS = {
    "tree-sitter": ">=0.26,<0.27",
    "tree-sitter-java": "==0.23.5",
    "tree-sitter-go": "==0.25.0",
    "tree-sitter-c-sharp": "==0.23.5",
    "tree-sitter-python": "==0.25.0",
    "tree-sitter-javascript": "==0.25.0",
    "tree-sitter-typescript": "==0.23.2",
    # Phase 7, each checked to load under the runtime above and to parse its fixture
    # with no error node before it was pinned.
    "tree-sitter-kotlin": "==1.1.0",
    "tree-sitter-rust": "==0.24.2",
    "tree-sitter-swift": "==0.7.3",
    "tree-sitter-scala": "==0.26.2",
    "tree-sitter-groovy": "==0.1.2",
    "tree-sitter-dart": "==0.1.0",
    "tree-sitter-c": "==0.24.2",
    "tree-sitter-cpp": "==0.23.4",
    "tree-sitter-ruby": "==0.23.1",
    "tree-sitter-php": "==0.24.1",
    "tree-sitter-elixir": "==0.3.5",
}

# The factory to call on the module, when it is not the usual `language()`.
# `tree-sitter-typescript` ships two grammars in one wheel, and they are not
# interchangeable: `.tsx` will not parse under `language_typescript` (`<` is
# ambiguous between a type argument and a JSX tag) and vice versa.
LANGUAGE_FACTORY = {
    "typescript": "language_typescript",
    "tsx": "language_tsx",
    # `language_php` is PHP embedded in HTML -- what a `.php` file actually is;
    # `language_php_only` would reject the `<?php` tag every file starts with.
    "php": "language_php",
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
    pkgs = _packages(langs)
    if not pkgs:
        return ""
    if not runtime_available():
        pkgs.insert(0, "tree-sitter")
    # A range carries `<` and `>`, which a shell reads as redirection: quote it.
    reqs = [f'"{r}"' if any(c in r for c in "<>") else r for r in map(requirement, pkgs)]
    return ("pip install --only-binary :all: --no-cache-dir"
            f" --target \"{VENDOR_DIR}\" {' '.join(reqs)}")


def _packages(langs) -> list[str]:
    pkgs: list[str] = []
    for lang in sorted(set(langs)):
        pkg = PIP_NAMES.get(GRAMMAR_MODULES.get(lang, ""), "")
        if pkg and pkg not in pkgs:
            pkgs.append(pkg)
    return pkgs


def requirement(pkg: str) -> str:
    """`pkg` with its pin, as pip reads it: `tree-sitter-go==0.25.0`."""
    return pkg + PINS.get(pkg, "")


def install_args(langs=None) -> list[str]:
    """pip's arguments for installing `langs` (default: every grammar) into vendor/.

    The runtime is always included: this is the full install, not a repair hint.
    """
    pkgs = _packages(langs if langs is not None else GRAMMAR_MODULES)
    return (["-m", "pip", "install", "--only-binary", ":all:", "--no-cache-dir",
             "--target", VENDOR_DIR] + [requirement(p) for p in ["tree-sitter"] + pkgs])


def drift() -> dict[str, tuple[str, str]]:
    """Installed grammars that are not their pinned version: {lang: (installed, pinned)}.

    Not staleness -- the graph agrees with what is installed -- but it is not the
    grammar `check_langs.py` was run against, so a node type may have been renamed
    under it. Said by name so a small graph has a stated cause.
    """
    out: dict[str, tuple[str, str]] = {}
    for lang, ver in versions().items():
        pin = PINS.get(PIP_NAMES[GRAMMAR_MODULES[lang]], "")
        if pin.startswith("==") and ver != pin[2:]:
            out[lang] = (ver, pin[2:])
    return out


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


def main(argv=None) -> int:
    """`--install` the pinned grammars into vendor/ with *this* interpreter, or `--print` the command.

    The interpreter matters: the runtime wheel is built for one Python version, so
    the Python that installs it must be the Python that runs the skill. Running
    this file with that Python is the one way to guarantee it.
    """
    import argparse
    import subprocess
    parser = argparse.ArgumentParser(description="Install the pinned tree-sitter grammars into <skill>/vendor.")
    parser.add_argument("langs", nargs="*", help=f"Languages (default: all of {', '.join(sorted(GRAMMAR_MODULES))})")
    parser.add_argument("--install", action="store_true", help="Run pip now")
    parser.add_argument("--print", action="store_true", help="Print the pip command instead")
    parser.add_argument("--quiet", action="store_true", help="Pass --quiet to pip")
    args = parser.parse_args(argv)
    unknown = sorted(set(args.langs) - set(GRAMMAR_MODULES))
    if unknown:
        print(f"error: no grammar known for: {', '.join(unknown)}", file=sys.stderr)
        return 2
    pip = install_args(args.langs or None) + (["--quiet"] if args.quiet else [])
    if args.print or not args.install:
        # A vendor path may not be ASCII, and the console may be cp874 (constraint 5).
        sys.stdout.reconfigure(errors="replace")
        print(" ".join([sys.executable] + [f'"{a}"' if any(c in a for c in " <>") else a for a in pip]))
        return 0
    return subprocess.call([sys.executable] + pip)


if __name__ == "__main__":
    raise SystemExit(main())
