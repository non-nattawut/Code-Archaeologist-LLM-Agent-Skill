#!/usr/bin/env python3
"""console.py — keep stdout alive on a non-UTF-8 console.

Every script that echoes text taken from the repo (node ids, descriptions, file
paths, git author names) can hit a character the terminal cannot encode: a
Windows console is cp1252, cp874 or similar, and one accented author name is
enough to end a run with UnicodeEncodeError. Files this skill writes stay UTF-8;
only the console degrades.

Call `safe_stdout()` first thing in `main()`.
"""
from __future__ import annotations

import sys


def safe_stdout() -> None:
    """Replace unencodable characters instead of raising."""
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):    # not a real stream, or already closed
        pass
