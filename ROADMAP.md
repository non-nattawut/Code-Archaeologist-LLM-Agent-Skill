# Roadmap — cheaper answers, same determinism

Working document. One goal drives every item here: **an agent using this skill should
spend fewer tokens per question.** Today it spends them in three places —

1. reading `architecture_report.json` (19KB on the 13-node sample; it scales with the repo),
2. opening note files one at a time after a trace,
3. falling back to grep/read over source when the graph cannot answer.

Each feature below removes one of those, by moving the work into a deterministic script.
Same constraints as everything else in this skill: stdlib only, Python 3.10+, sorted output,
paths resolved from the skill root, ASCII on stdout.

Status: `planned` -> `in progress` -> `done`. The near-term five all landed; the backlog is next.

## Near term

| # | Feature | What it removes | Status |
| --- | --- | --- | --- |
| F1 | `metrics.py` | source reads to answer "how big / how tangled" | done |
| F3 | `archaeologist.py brief` | reading the full report to orient | done |
| F2 | `context.py` | N note reads after every trace | done |
| F4 | compact output modes | JSON envelopes around one-line answers | done |
| F5 | `search.py` | grep over source | done |

Order is F1 -> F3 -> F2 -> F4 -> F5: `brief` reports F1's numbers, and `context.py` is
the largest change, so it lands once the smaller pieces have settled the shape.

### F1 — `metrics.py`: line counts and complexity
Per file: total / code / comment / blank lines plus language. Per node: LOC, cyclomatic
complexity, max nesting depth, parameter count. Node entries are keyed by **the same node
ids the graphs use**, so metrics join to either map without a lookup table. Writes
`data/report/metrics.json`; later feeds a "Size & complexity" section in the report and
node sizing in the explorer. Python nodes first; JS/TS nodes need `js_extract.js` to emit
an end line, which is its own follow-up.

### F3 — `archaeologist.py brief`: bounded orientation
A ~40-line digest — grade, layer counts, entry points, top hotspots, top risks, largest and
most complex nodes, staleness — replacing "read the report" at the start of a session. Its
size is fixed no matter how large the repo is; that is the point.

### F2 — `context.py`: one call instead of six
Given a node, return the pack the agent actually needs: that node's note, its immediate
callers and callees trimmed to their summary lines, its file metrics, its risk findings.
`--max-chars` budgets the result so a hub node cannot blow up the context. `--diff` packs
everything the current changeset touches. The single biggest saving in this list.

### F4 — compact output modes
`--format text` on `trace_path.py` and `analyze.py`: `create_order > place_order > save`
instead of a JSON envelope. Small change, applied to the calls the agent makes most often.

### F5 — `search.py`: graph-aware lookup
`--name <regex> --layer --kind --calls <id>` returning node ids, `file:line` and the summary
line. Exists so the agent stops falling back to grep, which is where unbounded reads start.

## Backlog

- ~~**TODO/FIXME + dead-code inventory**~~ — done: `debt.py`, reusing `scan_security`'s file walk
  and node attribution and `analyze`'s orphan detection, plus dead *files*.
- ~~**Test-coverage mapping**~~ — done: `tests_map.py`. Name-based and deterministic; no runner,
  no instrumentation.
- **Duplicate-code clusters** — normalized token hashing of function bodies.
- ~~**Trim `SKILL.md`**~~ — done: 17.8KB -> 13.1KB, all 14 commands kept, prose that duplicated
  README/USAGE cut. It loads into context every session, so this is a per-session win.

## How this gets built

Implementation is delegated to a sub-agent (`agy`, Gemini 3.8 Flash) against a written spec
per feature; the spec, the review of the diff, and the verification run stay here. Every
feature is verified the same way the rest of the skill is — see the "Verify changes" section
of `CLAUDE.md` — and lands with its docs (`SKILL.md`, `README.md`, `USAGE.md`) in the same
commit.
