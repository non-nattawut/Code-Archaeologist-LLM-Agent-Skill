# Usage — command reference

**Most people never run these by hand.** The agent does: it reads
[`SKILL.md`](.agents/skills/code-archaeologist/SKILL.md) — which carries the same commands plus the
rules for *when* to run each one — and calls them for you. This file is the human-readable mirror,
for when you want to drive the pipeline yourself, script it in CI, or check what the agent just ran.

Paths below assume the default install (`.agents/skills/code-archaeologist`). If you installed into
another harness, swap that prefix — the installer already rewrites it inside the copied `SKILL.md`.

## Build the maps

Each command builds one map (scan → graph → explorer in one shot):

```bash
# Project structure map  ->  data/structure/{graph.json, vault/}  (+ data/explorer.html)
python .agents/skills/code-archaeologist/scripts/archaeologist.py project --src ./src

# Request/execution flow map  ->  data/flow/{flow_graph.json, notes/}  (+ data/explorer.html)
python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./src

# Monorepo: pass multiple roots (backend + frontend land in one graph)
python .agents/skills/code-archaeologist/scripts/archaeologist.py flow --src ./backend ./frontend

# ...or build both maps
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./src
```

## Orient yourself

One fixed-size digest of everything already built — counts, grade, staleness, entry points, the
biggest/most complex/most churned/riskiest nodes — instead of reading the full report:

```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py brief --src ./src

# same digest, other map / more rows / machine-readable
python .agents/skills/code-archaeologist/scripts/brief.py --map structure --top 3
python .agents/skills/code-archaeologist/scripts/brief.py --json
```

## Find the nodes

Filter the graph instead of grepping the source:

```bash
python .agents/skills/code-archaeologist/scripts/search.py --name "payment|charge"
python .agents/skills/code-archaeologist/scripts/search.py --doc "refund" --limit 10
python .agents/skills/code-archaeologist/scripts/search.py --layer repository --kind method
python .agents/skills/code-archaeologist/scripts/search.py --calls OrderRepository.save
python .agents/skills/code-archaeologist/scripts/search.py --orphans --format json
```

## Query the graphs

Trace paths or impact on either graph (structure is the default; add `--graph` for flow). These print compact text - `A > B > C` for a path, a heading plus one node per line for an impact set; add `--format json` for the full envelope:

```bash
# structure: how are two classes connected?
python .agents/skills/code-archaeologist/scripts/trace_path.py --from OrderController --to OrderRepository

# flow: how does a request travel, method by method?
python .agents/skills/code-archaeologist/scripts/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json \
  --from OrderController.create_order --to OrderRepository.save

# blast-radius: everything that breaks if a method changes
python .agents/skills/code-archaeologist/scripts/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --impact-of PaymentClient.charge
```

## Everything about one node

```bash
# one budgeted pack: facts, size, churn, description, callers/callees with their
# own descriptions, and the risks attributed to it
python .agents/skills/code-archaeologist/scripts/context.py --node OrderService.place_order

# every node the current diff touches, two hops out, in 8000 chars or less
python .agents/skills/code-archaeologist/scripts/context.py --diff --depth 2 --max-chars 8000
```

## Keep them honest

Freshness, changeset impact, and the deterministic smell checks:

```bash
# freshness: are the maps stale vs the current source? (rebuild if so)
python .agents/skills/code-archaeologist/scripts/archaeologist.py check --src ./src

# changeset blast-radius: what does my current git diff affect?
python .agents/skills/code-archaeologist/scripts/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --impact-of-diff

# smells + health grade: cycles, orphans, layer violations, hubs, god objects, idioms
python .agents/skills/code-archaeologist/scripts/analyze.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json

# the same, as lines instead of JSON
python .agents/skills/code-archaeologist/scripts/analyze.py --format text
```

## Review pass

The whole codebase in one shot — grade, risks and hotspots:

```bash
# writes data/report/<map>/architecture_report.md (+ .json, security.json, insights.json)
# and re-renders each viewer with its report: health ring, churn/risk colors,
# ownership, and the Patterns/Security tabs
python .agents/skills/code-archaeologist/scripts/archaeologist.py report --src ./src
```

Its inputs run on their own too:

```bash
# risk scan: hardcoded secrets, interpolated SQL, eval/innerHTML sinks, debug leftovers
python .agents/skills/code-archaeologist/scripts/scan_security.py --src ./src

# git churn/ownership + hotspot ranking (risk = commits x (1 + fan_in + fan_out))
python .agents/skills/code-archaeologist/scripts/git_insights.py --src ./src --top 10

# lines of code per file + LOC/complexity/depth per node (Python nodes)
python .agents/skills/code-archaeologist/scripts/metrics.py --src ./src --top 10

# TODO/FIXME/HACK markers + nodes nothing calls + files where every node is dead
python .agents/skills/code-archaeologist/scripts/debt.py --src ./src --top 10

# which nodes the test suite names, and which it never mentions
python .agents/skills/code-archaeologist/scripts/tests_map.py --src ./src --top 15
```

Every stage is runnable on its own (`build_wiki.py`, `build_graph.py`, `build_flow.py`,
`build_html.py`) — `archaeologist.py` only orchestrates them. Each script takes `--help`.

## Worked example

Running against the bundled `sample_src/` (a controller → service → repository/client trio):

```console
# Structure: how two classes connect
$ trace_path.py --from OrderController --to OrderRepository
{ "path": ["OrderController", "OrderService", "OrderRepository"], "found": true }

# Flow: the actual request path, method by method
$ trace_path.py --graph .../flow_graph.json --from OrderController.create_order --to OrderRepository.save
{ "path": ["OrderController.create_order", "OrderService.place_order", "OrderRepository.save"], "found": true }

# Flow blast-radius: what calls (directly or transitively) into the payment client?
$ trace_path.py --graph .../flow_graph.json --impact-of PaymentClient.charge
{ "impacted": ["OrderController.create_order", "OrderService.place_order",
               "createOrder", "submitOrder"], "count": 4 }
```

The agent then reads only the notes on that path — e.g.
`data/flow/notes/OrderController.create_order.md`, `OrderService.place_order.md`,
`OrderRepository.save.md` — not the whole repo.

The review pass over the same sample (the demo sources carry three deliberate smells) produces
`data/report/flow/architecture_report.md` and its structure-map twin:

```console
$ archaeologist.py report --src ./sample_src
  grade D (67/100), 4 risk finding(s), 13 ranked hotspot(s)
```

| Severity | Rule | Location | Owner node |
| --- | --- | --- | --- |
| high | `sql_injection` | `sample_src/backend/order_repository.py:15` | `OrderRepository.get` |
| high | `hardcoded_secret` | `sample_src/backend/payment_client.py:5` | — (module level) |
| medium | `dangerous_eval` | `sample_src/frontend/order_page.ts:11` | `loadOrder` |
| low | `debug_statement` | `sample_src/backend/payment_client.py:14` | `PaymentClient.charge` |

The same sample carries two deliberate markers, so the debt inventory has something to find:

```console
$ debt.py --src ./sample_src --graph .../flow_graph.json
Debt: 2 marker(s) (FIXME 1, TODO 1), 2 dead node(s), 1 dead file(s)
  FIXME  sample_src/backend/order_repository.py:15 [OrderRepository.get]  parameterize this query
  TODO   sample_src/backend/payment_client.py:13 [PaymentClient.charge]   retry once on a gateway timeout
```

It has no tests, so `tests_map.py` reports `0/11 node(s) named by a test` — which is exactly the
answer that command exists to give.

The generated `data/report/`, `data/structure/` and `data/flow/` folders in this repo are that
demo output, committed so you can read a real example before running anything.
