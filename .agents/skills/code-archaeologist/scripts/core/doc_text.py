#!/usr/bin/env python3
"""doc_text.py -- the one rule for turning a doc comment into a node's `doc`.

Every producer used to answer "what documents this node" differently, so the same
comment got three answers depending on the file extension: `langs_extract` joined
the whole block into one line, `js_ts_extract` kept only its first non-empty line
and refused a comment that was not on the line directly above, and Python's
docstring was truncated at its first line by each call site separately.
`langs_extract`'s rule is now the rule, and it lives here.

What the rule is:

- the comment block above the declaration, blank lines invisible, stopping at the
  first non-comment -- a comment separated by code is not the doc (that walk stays
  in each producer, because only it knows its grammar's comment node types)
- consecutive comment blocks are all part of it, which is how a run of `//` lines
  becomes one doc in Go and C#
- markers are stripped and every non-empty line is joined with a space, so a `doc`
  is always exactly one line

`clean()` is for comment text, `join()` for a Python docstring, which has no
markers to strip. Pure string work: this module imports nothing of the skill's,
which is why it can sit in `core/` below every producer.
"""
from __future__ import annotations

import re

# `/**`, `/*` and a trailing `*/` around a block; then per line, a `//`, `///`,
# `//!` (Rust), `*` (Javadoc continuation) or `#` (Ruby/PHP/Elixir) marker.
_BLOCK_EDGES = re.compile(r"^/\*+|\*+/$")
_LINE_MARKER = re.compile(r"^(?://+[/!]?|\*+|#+)\s?")

# C# writes its doc as XML. The named tags are dropped as a unit so their text
# survives; the sweep after them takes the rest, `<param>` and `<returns>` included.
_XML_NAMED = re.compile(r"</?(?:summary|remarks|para)>")
_XML_ANY = re.compile(r"<[^>]+>")


def join(text: str) -> str:
    """Every non-empty line of `text`, joined with a space."""
    return " ".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def clean(blocks: list[str], *, xml: bool = False) -> str:
    """`blocks` -- innermost first, as a sibling walk collects them -- as one line.

    `xml` is for the languages whose doc convention is XML (C#, and JSDoc, which
    borrowed Javadoc's HTML). It is off for the rest because the sweep cannot tell
    a tag from a generic, and `Vec<String>` in a Rust doc comment is not markup.
    """
    lines: list[str] = []
    for block in reversed(blocks):
        block = _BLOCK_EDGES.sub("", block.strip())
        for raw in block.splitlines():
            raw = _LINE_MARKER.sub("", raw.strip())
            if xml:
                raw = _XML_ANY.sub("", _XML_NAMED.sub("", raw))
            if raw.strip():
                lines.append(raw.strip())
    return " ".join(lines).strip()
