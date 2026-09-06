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

import re

# Allowed `layer` values, with the name/decorator patterns used to infer them.
# First match wins.
LAYER_RULES = [
    (re.compile(r"controller|handler|router|resource|endpoint", re.I), "controller"),
    (re.compile(r"service|usecase|manager", re.I), "service"),
    (re.compile(r"repository|repo|dao|store|mapper", re.I), "repository"),
    (re.compile(r"model|entity|schema|dto|record", re.I), "model"),
    (re.compile(r"client|gateway|adapter|api", re.I), "client"),
    (re.compile(r"config|settings|env", re.I), "config"),
    (re.compile(r"component|view|page|screen|widget", re.I), "ui"),
]
LAYERS = [
    "controller", "service", "repository", "model", "client",
    "config", "ui", "function", "module", "unknown",
]

# Allowed `kind` values (what the node physically is).
KINDS = ["class", "method", "function", "module", "endpoint", "component"]

# Decorators / patterns that mark a route handler (HTTP endpoint).
ROUTE_DECORATOR_RE = re.compile(r"route|get|post|put|patch|delete|mapping|endpoint", re.I)


def infer_layer(name: str, decorators=(), bases=()) -> str:
    haystack = " ".join([name, *decorators, *bases])
    for pattern, layer in LAYER_RULES:
        if pattern.search(haystack):
            return layer
    return "unknown"
