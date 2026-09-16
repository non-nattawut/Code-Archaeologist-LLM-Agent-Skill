#!/usr/bin/env python3
"""call_ctx.py -- where a call is written: its line, and whether a loop or a branch holds it.

A call link used to carry nothing about its call site, so a node calling five others
could not say which call is written first, or that one of them only runs inside an
`if`. Every producer now asks this module about each call node it reads, and
`build_flow` carries the answer onto the link:

- `line`  the line the call is written on
- `loop`  the call is written inside a loop's body, so it may run many times
- `cond`  the call is written inside a branch -- an `if`/`else`, a `switch` or `match`
          arm, a ternary's result, a `catch` -- so it may not run at all
- `arms`  outer to inner, each either/or branch the call sits on one side of, as
          `"<line>:<col>/<arm>"` -- the branch's first line and column, and which side, counted
          in source order (an `if` is 0, its `else if` 1, its `else` 2). Two calls on different
          arms of one branch are alternatives: exactly one of them runs

What it reads is the syntax, never the run: the line is the order calls are *written*
in, not the order they execute. Two rules keep it honest:

- **Only a body counts.** A call in a `for` header's iterable (`range service.Events()`)
  or initializer runs once, and a call in an `if` condition always runs, so neither is
  marked. A loop node counts a call that arrived through a repeating field (`body`,
  `condition`, `increment`, `update`); a branch node, one that arrived through a result
  field (`consequence`, `alternative`, `body`, ...). Kotlin and Swift leave some bodies
  unnamed, so for their loop and `if` types an unnamed *block* child counts too. An arm
  node (`else_clause`, `catch_clause`, `when_entry`, ...) makes everything under it
  conditional.
- **A type not listed reports nothing.** Node types are named explicitly, per grammar,
  from a probe of all seventeen: a lower bound, like the call links themselves. Known
  gaps, deliberately left: a Python ternary (its fields are unnamed), short-circuit
  `&&` / `??`, a Go `for cond {}` condition, the second `for` of a nested comprehension
  (read as an iterable, though it runs once per outer item), and Elixir, whose
  `if`/`case`/`for` are macro calls with no typed node. A callback handed to `.map()` / `.forEach()` is not
  a loop: syntactically it is not in one.

**An arm is an alternative only where the sides exclude each other**: an `if` / `else if` /
`else` chain, however the grammar nests it; a ternary; a `match` or `when`; a `select`; and a
`switch` only where a case cannot run on into the next -- Java's `case X ->`, C#, Go and Swift
(unless the switch says `fallthrough`), Dart, Ruby's `case`. A C, C++, JS/TS, PHP or Java/Groovy
`case X:` falls through without `break`, and a `catch` runs after its `try` has run, so neither
records an arm; both still set `cond`.

Pure: it imports nothing and duck-types the tree-sitter node (`type`, `parent`, `id`,
`children`, `start_point`, `field_name_for_child`), so it sits in `core/` below every
producer, beside `doc_text.py`.
"""
from __future__ import annotations

# A loop, and the fields of it that run once per iteration. Any other field -- an
# iterable, an initializer, a Go `range_clause` -- runs once, and marks nothing.
LOOP_NODES = frozenset({
    "for_statement", "for_in_statement", "enhanced_for_statement", "foreach_statement",
    "for_range_loop", "for_clause", "for_loop_parts", "for_expression",
    "while_statement", "while_expression", "do_statement", "do_while_statement",
    "repeat_while_statement", "loop_expression",
    "list_comprehension", "set_comprehension", "dictionary_comprehension", "generator_expression",
    "for", "while", "until", "while_modifier", "until_modifier",                   # Ruby
})
REPEAT_FIELDS = frozenset({"body", "condition", "increment", "update"})

# A branch, and the fields of it that hold a result rather than the test.
BRANCH_NODES = frozenset({
    "if_statement", "if_expression", "ternary_expression", "conditional_expression",
    "switch_statement", "switch_expression", "expression_switch_statement",
    "type_switch_statement", "match_statement", "match_expression", "guard_statement",
    "if", "unless", "conditional", "if_modifier", "unless_modifier",                # Ruby
})
RESULT_FIELDS = frozenset({"consequence", "alternative", "body", "if_true", "if_false",
                           "return_expression"})

# Reached at all, these mean the call is conditional: an arm is only taken sometimes.
ARM_NODES = frozenset({
    "else_clause", "elif_clause", "else_if_clause", "except_clause", "except_group_clause",
    "catch_clause", "catch_block", "switch_case", "switch_default", "switch_section",
    "switch_block_statement_group", "switch_rule", "switch_expression_arm",
    "switch_statement_case", "switch_entry", "case_statement", "expression_case", "type_case",
    "default_case", "communication_case", "when_entry", "match_arm",
    "match_conditional_expression", "match_default_expression",
    "elsif", "else", "when", "rescue",                                              # Ruby
})

# Kotlin and Swift leave these bodies unnamed. Only these types get the fallback, and
# only for a block child, never an expression -- so a Kotlin `for (x in load())` iterable,
# also unnamed, is not mistaken for a body, and Swift's `do { try ... }`, which shares
# the name `do_statement` with a do-while elsewhere, is not a loop.
UNNAMED_BODY_NODES = frozenset({"for_statement", "while_statement", "do_while_statement",
                                "repeat_while_statement", "if_expression", "if_statement",
                                "guard_statement"})
BLOCK_TYPES = frozenset({"block", "statements", "control_structure_body"})

# Branches whose sides exclude each other. An if-family node chains through its else side
# (`else if`), so a whole chain is one branch; a switch-family node's sides are arm nodes.
IF_NODES = frozenset({"if_statement", "if_expression", "ternary_expression",
                      "conditional_expression", "conditional", "if", "unless", "elsif"})
ELSE_WRAPPERS = frozenset({"else_clause", "else"})            # JS/C/C++/Rust, Ruby
SWITCH_NODES = frozenset({"match_statement", "match_expression", "when_expression",
                          "switch_statement", "switch_expression", "expression_switch_statement",
                          "type_switch_statement", "select_statement", "case"})
# Arm node types that never fall into the next arm. Absent on purpose: `switch_case` (JS/TS),
# `case_statement` (C, C++, PHP), `switch_block_statement_group` (Java/Groovy `case X:`).
EXCLUSIVE_ARMS = frozenset({
    "case_clause", "match_arm", "match_conditional_expression", "match_default_expression",
    "when_entry", "switch_entry", "expression_case", "type_case", "default_case",
    "communication_case", "switch_section", "switch_expression_arm", "switch_rule",
    "switch_statement_case",
    "when", "else",                                                                 # Ruby `case`
})
FALLTHROUGH_ARMS = frozenset({"expression_case", "type_case", "default_case", "switch_entry"})  # Go, Swift


def _field(parent, child) -> str | None:
    for i, c in enumerate(parent.children):
        if c.id == child.id:
            return parent.field_name_for_child(i)
    return None


def _where(node) -> str:
    return f"{node.start_point[0] + 1}:{node.start_point[1] + 1}"


def _is_else_if(node) -> tuple:
    """(the if-family node this one is the `else if` of, or None). JS/C/C++/Rust and Ruby wrap
    the else side (`else_clause`, `else`); Java, C#, Go, Dart, Scala, Groovy put the `if` straight
    in `alternative`; Kotlin and Swift leave it unnamed beside the `then` block."""
    up = node.parent
    if up is None or node.type not in IF_NODES:
        return None
    if up.type in ELSE_WRAPPERS and up.parent is not None and up.parent.type in IF_NODES:
        return up.parent
    if up.type in IF_NODES:
        field = _field(up, node)
        if field == "alternative" or (field is None and up.type in UNNAMED_BODY_NODES):
            return up
    return None


def _if_arm(parent, child):
    """(chain root, arm) when `child` is one side of the if-family node `parent`, else None."""
    field = _field(parent, child)
    depth, root = 0, parent
    while (outer := _is_else_if(root)) is not None:
        depth, root = depth + 1, outer
    if field in ("consequence", "if_true", "body"):
        side = 0
    elif field in ("alternative", "if_false"):
        # Python and PHP list every `elif` / `else if` / `else` as its own `alternative` child.
        alts = [c for i, c in enumerate(parent.children) if parent.field_name_for_child(i) == "alternative"]
        side = 1 + next((i for i, c in enumerate(alts) if c.id == child.id), 0)
        if child.type in IF_NODES:
            return None                     # an `else if`: its own sides are counted from it
    elif field is None and parent.type in UNNAMED_BODY_NODES and child.type in BLOCK_TYPES:
        blocks = [c for c in parent.children if c.type in BLOCK_TYPES]
        side = next(i for i, c in enumerate(blocks) if c.id == child.id)
    elif field == "condition" and depth:
        return root, depth                  # an `else if` test runs only when the ones above failed
    else:
        return None
    return root, depth + side


def _switch_arm(arm):
    """(switch node, arm index) when `arm` is an arm of a switch whose arms exclude each other."""
    if arm.type not in EXCLUSIVE_ARMS or arm.parent is None:
        return None
    container = arm.parent if arm.parent.type in SWITCH_NODES else arm.parent.parent
    if container is None or container.type not in SWITCH_NODES:
        return None
    stack = [container] if arm.type in FALLTHROUGH_ARMS else []
    while stack:                            # Go / Swift `fallthrough` runs on into the next arm
        n = stack.pop()
        if n.type == "fallthrough_statement" or (
                n.type == "control_transfer_statement" and (n.text or b"").startswith(b"fallthrough")):
            return None
        stack.extend(n.children)
    # Named children only: Kotlin's `when` keyword is an anonymous token of the same type name
    # as Ruby's `when` arm, and counted as one it shifted every arm by one.
    siblings = [c for c in arm.parent.named_children if c.type in EXCLUSIVE_ARMS]
    return container, next(i for i, c in enumerate(siblings) if c.id == arm.id)


def site(call, stop=None) -> dict:
    """`{"line": N}`, plus `"loop": True` / `"cond": True` and `"arms"` where earned, for one
    call node.

    Walks from the call up to `stop` -- the definition the call belongs to -- and never
    past it: a method declared inside an `if` does not make its own calls conditional. A whole
    `else if` chain is one branch, so once a side of it is found the walk continues from the
    chain's first `if`.
    """
    out = {"line": call.start_point[0] + 1}
    arms: list[str] = []
    child, parent = call, call.parent
    while parent is not None and (stop is None or child.id != stop.id):
        found = _switch_arm(child) if child.type in EXCLUSIVE_ARMS else None
        if found is None and parent.type in IF_NODES:
            found = _if_arm(parent, child)
        if found is not None:
            root, arm = found
            arms.append(f"{_where(root)}/{arm}")
            out["cond"] = True              # one side of an either/or never has to run
            if root.id != parent.id and (stop is None or root.id != stop.id):
                child, parent = root, root.parent
                continue
        kind = parent.type
        if kind in ARM_NODES:
            out["cond"] = True
        elif kind in LOOP_NODES or kind in BRANCH_NODES:
            field = _field(parent, child)
            body = field is None and kind in UNNAMED_BODY_NODES and child.type in BLOCK_TYPES
            if kind in LOOP_NODES and (field in REPEAT_FIELDS or body):
                out["loop"] = True
            if kind in BRANCH_NODES and (field in RESULT_FIELDS or body):
                out["cond"] = True
        child, parent = parent, parent.parent
    if arms:
        out["arms"] = arms[::-1]
    return out


def facts(call: dict) -> dict:
    """The call-site keys of a producer's call entry, and nothing else."""
    return {k: (list(call[k]) if k == "arms" else call[k])
            for k in ("line", "loop", "cond", "arms") if k in call}


def merge(into: dict, other: dict) -> dict:
    """Fold a second site of the same call into `into`, in place.

    The first line wins; a loop if *any* site is in one; a branch only if *every* site is
    -- a call also made unconditionally always runs; and `arms` keeps only the sides every
    site shares, outermost first -- a call made in both the `if` and the `else` is on neither.
    Order-independent, so a build stays byte-identical however the sites are visited. A site
    with no line adds nothing.
    """
    if "line" not in other:
        return into
    if "line" not in into:
        into.update(facts(other))
        return into
    into["line"] = min(into["line"], other["line"])
    if other.get("loop"):
        into["loop"] = True
    if not other.get("cond"):
        into.pop("cond", None)
    shared = []
    for a, b in zip(into.get("arms", []), other.get("arms", [])):
        if a != b:
            break
        shared.append(a)
    if shared:
        into["arms"] = shared
    else:
        into.pop("arms", None)
    return into
