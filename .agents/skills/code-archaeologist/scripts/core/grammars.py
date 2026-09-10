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

Nothing here imports another skill module -- `core/` sits at the bottom of the
layering -- and importing this module never imports a grammar. Loading is lazy
and cached, so listing what is available costs one `find_spec` per language.

Zero external dependencies at import time. Python 3.10+.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util

# Our language key (taxonomy.LANG_BY_EXT values) -> the wheel that provides it.
# A language is supported when it is in this table AND its wheel is installed AND
# extract/ has a query for it; this table answers only the middle question.
GRAMMAR_MODULES = {
    "java": "tree_sitter_java",
    "go": "tree_sitter_go",
    "csharp": "tree_sitter_c_sharp",
}

# `pip install` name per module, for the message a user is asked to run.
PIP_NAMES = {
    "tree_sitter_java": "tree-sitter-java",
    "tree_sitter_go": "tree-sitter-go",
    "tree_sitter_c_sharp": "tree-sitter-c-sharp",
}

_parsers: dict[str, object] = {}


def runtime_available() -> bool:
    """Is the `tree-sitter` runtime itself installed?"""
    return importlib.util.find_spec("tree_sitter") is not None


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
    """
    pkgs = [PIP_NAMES[GRAMMAR_MODULES[l]] for l in sorted(set(langs)) if l in GRAMMAR_MODULES]
    if not pkgs:
        return ""
    if not runtime_available():
        pkgs.insert(0, "tree-sitter")
    return f"pip install {' '.join(pkgs)}"


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
    if not runtime_available() or not have(lang):
        _parsers[lang] = None
        return None
    import tree_sitter

    grammar = importlib.import_module(GRAMMAR_MODULES[lang])
    language = tree_sitter.Language(grammar.language())
    _parsers[lang] = tree_sitter.Parser(language)
    return _parsers[lang]


def query(lang: str, source: str):
    """Compile a query string against `lang`'s grammar."""
    import tree_sitter

    grammar = importlib.import_module(GRAMMAR_MODULES[lang])
    return tree_sitter.Query(tree_sitter.Language(grammar.language()), source)
