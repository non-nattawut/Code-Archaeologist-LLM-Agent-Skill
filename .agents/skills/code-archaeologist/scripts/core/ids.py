#!/usr/bin/env python3
"""ids.py -- node ids: bare where a name is defined once, file-qualified where it is not.

Both maps name their nodes after the code: a flow node is `place_order` or
`OrderService.place_order`, a structure node is `OrderService`. Names carry no
file, so the same name in two files used to be ONE node -- the flow map merged
both definitions and their call edges, the structure map kept the first and
dropped the rest. Either way the graph was quietly wrong.

`SharedNames` is given every definition's (name, file) before any node exists,
and answers two questions:

  id(name, file)            the id that definition gets -- unchanged unless two
                            or more files define `name`, then qualified by its
                            file (`tests_map.build`), else by its path
  target(name, from_file)   the id a reference to `name` means -- the only one
                            if there is one, the referencing file's own if it
                            is shared, and None otherwise: name-based resolution
                            cannot know which of several an import meant, and a
                            wrong edge is worse than a missing one

Qualifiers are compared case-insensitively, because every node is also a note
file `<id>.md`, and on Windows and macOS `Widgets.X` and `widgets.X` are one file.

Pure logic, no imports from the skill -- which is why it lives in `core/`, below
the two `extract/` builders that both use it.
"""
from __future__ import annotations

import sys


def _qualifiers(rel: str) -> list[str]:
    """Ways to name a file, shortest first: stem, path without extension, full path."""
    base = rel.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return [stem, rel[: len(rel) - len(base)] + stem, rel]


class SharedNames:
    """Every definition's name and file, and the final id each one gets."""

    def __init__(self, defs):
        self.defined: dict[str, set[str]] = {}
        for name, rel in defs:
            self.defined.setdefault(name, set()).add(rel)
        # Grouped ignoring case: `login` in one file and `Login` in another are two
        # names but one note file on Windows and macOS, so they are qualified exactly
        # like one name two files share. Grouping by exact name missed them (found on
        # a real Next.js repository: a `login` service beside a `Login` page).
        groups: dict[str, list[tuple[str, str]]] = {}
        for name, rels in self.defined.items():
            groups.setdefault(name.lower(), []).extend((name, r) for r in rels)
        self.qualified: dict[tuple[str, str], str] = {}
        taken = set(groups)
        for key in sorted(k for k, group in groups.items() if len(group) > 1):
            group = sorted(groups[key])
            # The shortest qualifier under which every definition is distinct, and
            # none clashes with an id that already exists -- ignoring case.
            for level in range(3):
                ids = [f"{_qualifiers(r)[level]}.{n}" for n, r in group]
                low = [i.lower() for i in ids]
                if len(set(low)) == len(low) and not taken.intersection(low):
                    break
            self.qualified.update(zip(group, ids))
            taken.update(i.lower() for i in ids)

    def id(self, name: str, rel: str) -> str:
        """The id the definition of `name` in `rel` gets."""
        return self.qualified.get((name, rel), name)

    def target(self, name: str, from_rel: str) -> str | None:
        """The id a reference to `name` from `from_rel` means, or None if it cannot be told."""
        rels = self.defined.get(name, ())
        if len(rels) < 2:     # one definition: unambiguous, even if a case twin qualified it
            return self.qualified.get((name, next(iter(rels))), name) if rels else name
        return self.qualified.get((name, from_rel))

    def shared(self) -> list[str]:
        return sorted({n for n, _ in self.qualified})

    def report(self, what: str, limit: int = 5) -> None:
        """One line naming what was qualified -- never silent, never one line per name."""
        shared = self.shared()
        if not shared:
            return
        shown = "; ".join(f"{n} -> {', '.join(sorted(self.qualified[(n, r)] for r in self.defined[n]))}"
                          for n in shared[:limit])
        more = f" (+{len(shared) - limit} more)" if len(shared) > limit else ""
        print(f"  ! {len(shared)} {what}(s) are defined in more than one file (ignoring case), so each definition is"
              f" qualified by its file: {shown}{more}. A reference to one of them from a file that"
              " does not define it is dropped rather than guessed.", file=sys.stderr)
