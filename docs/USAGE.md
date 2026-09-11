# Usage — command reference

**Most people never run these by hand.** The agent does: it reads
[`SKILL.md`](../.agents/skills/code-archaeologist/SKILL.md) — which carries the same commands plus the
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

`data/explorer.html` is written by every one of these. It is a single file with the data *and* the
graph library embedded, so it opens straight from `file://` with the network off — commit it, or
email it to someone who has no access to the repo.

## Orient yourself

One fixed-size digest of everything already built — counts, grade, staleness, entry points, the
biggest/most complex/most churned/riskiest nodes — instead of reading the full report:

```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py brief --src ./src

# same digest, other map / more rows / machine-readable
# (--src is optional here too: the freshness line falls back to the recorded roots)
python .agents/skills/code-archaeologist/scripts/review/brief.py --map structure --top 3
python .agents/skills/code-archaeologist/scripts/review/brief.py --json
```

## Find the nodes

Filter the graph instead of grepping the source:

```bash
python .agents/skills/code-archaeologist/scripts/query/search.py --name "payment|charge"
python .agents/skills/code-archaeologist/scripts/query/search.py --doc "refund" --limit 10
python .agents/skills/code-archaeologist/scripts/query/search.py --layer repository --kind method
python .agents/skills/code-archaeologist/scripts/query/search.py --calls OrderRepository.save
python .agents/skills/code-archaeologist/scripts/query/search.py --orphans --format json

# one language at a time: py, js, java, go, csharp, kotlin, rust, swift, scala, groovy,
# dart, c, cpp, ruby, php, elixir
python .agents/skills/code-archaeologist/scripts/query/search.py --lang java
```

Nodes carry `precision` when a specific loss is known — `interface-dispatch`, `overloads` or
`name-matched`. Every language is parsed with tree-sitter, so the declarations are exact; what is
partial everywhere is **resolution** — a call is followed only through a declared
type, and anything else is dropped rather than guessed, so their edges are a lower bound.
`context.py` prints the caveat on the node itself, and the report opens with how many nodes it
covers. To see what the extractor made of those files directly:

```bash
python .agents/skills/code-archaeologist/scripts/extract/ts_extract.py --src ./src
```

Needs the tree-sitter runtime plus the wheel per language, installed **into the skill folder**
rather than into your Python:

```bash
python .agents/skills/code-archaeologist/scripts/core/grammars.py --install              # every grammar
python .agents/skills/code-archaeologist/scripts/core/grammars.py --install python go    # only these
python .agents/skills/code-archaeologist/scripts/core/grammars.py --print                # show the pip command
```

It runs `pip install --only-binary :all: --no-cache-dir --target <skill>/vendor` with the Python you
ran it with, at the versions pinned in `grammars.PINS` — exact for each grammar, a range for the
runtime. If `brief` prints `UNPINNED`, an installed grammar is not its pin; re-run `--install`.
They land in `<skill>/vendor`, which is git-ignored: your own environment is untouched, nothing can
collide with your projects' versions, and removing the skill removes them. `tree-sitter-javascript`
covers `.js`/`.jsx` and `tree-sitter-typescript` covers `.ts` *and* `.tsx`. **Python needs
`tree-sitter-python` like any other language** — it used to be read with the standard library and
is not any more. Any grammar that is
missing is named in the build output with the exact command, those files produce no nodes, and
`brief` prints a `SKIPPED` block — the graph is smaller than the codebase and says so.

`vendor/` is built for the Python that installed it. If a build reports *"runtime found but not
loadable"*, you changed Python version — re-run the command above.

## Check the skill itself

Repo tools, not part of the installed skill -- they need files (`README.md`, `CLAUDE.md`,
`tests/fixtures/`) that no installed copy has:

```bash
python tools/check_docs.py            # every script is documented, every quoted path exists
python tools/check_langs.py           # every graphed language still produces its nodes and edges
python tools/check_py_oracle.py       # Python read by tree-sitter agrees with the stdlib `ast`
python tools/check_graph.py           # every edge real, every range right, every count consistent
python tools/check_graph.py --self-test   # proves each of those checks can actually fail
python tools/check_regressions.py     # one case per silent failure this project has had
```

`check_graph.py` reads the graphs under `data/` and resolves node sources against the roots the last
build recorded, so it works on any codebase you have built, not only the sample: build yours, then
run it. It takes `--map flow|structure` and `--src <roots>` to override either.

`check_langs.py` takes language names to narrow it (`python tools/check_langs.py go java`) and
`--update` to re-record expectations from what the extractors currently do -- useful, and dangerous
for the same reason, so read the diff it writes.

`check_py_oracle.py` takes a source root (default `./sample_src`); point it at a large Python
codebase to get a far better test than the sample can give -- that is how the wrapped-signature bug
was found.

## Query the graphs

Trace paths or impact on either graph (structure is the default; add `--graph` for flow). These print compact text - `A > B > C` for a path, a heading plus one node per line for an impact set; add `--format json` for the full envelope:

```bash
# structure: how are two classes connected?
python .agents/skills/code-archaeologist/scripts/query/trace_path.py --from OrderController --to OrderRepository

# flow: how does a request travel, method by method?
python .agents/skills/code-archaeologist/scripts/query/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json \
  --from OrderController.create_order --to OrderRepository.save

# blast-radius: everything that breaks if a method changes
python .agents/skills/code-archaeologist/scripts/query/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --impact-of PaymentClient.charge
```

## Everything about one node

```bash
# one budgeted pack: facts, size, churn, description, callers/callees with their
# own descriptions, and the risks attributed to it
python .agents/skills/code-archaeologist/scripts/query/context.py --node OrderService.place_order

# every node the current diff touches, two hops out, in 8000 chars or less
python .agents/skills/code-archaeologist/scripts/query/context.py --diff --depth 2 --max-chars 8000
```

## Keep them honest

Freshness, changeset impact, and the deterministic smell checks:

```bash
# freshness: are the maps stale vs the current source? (rebuild if so)
# --src is optional -- without it, the roots the last build recorded are re-used
python .agents/skills/code-archaeologist/scripts/archaeologist.py check --src ./src
python .agents/skills/code-archaeologist/scripts/archaeologist.py check

# changeset blast-radius: what does my current git diff affect?
python .agents/skills/code-archaeologist/scripts/query/trace_path.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json --impact-of-diff

# smells + health grade: cycles, orphans, layer violations, hubs, god objects, idioms
python .agents/skills/code-archaeologist/scripts/review/analyze.py \
  --graph .agents/skills/code-archaeologist/data/flow/flow_graph.json

# the same, as lines instead of JSON
python .agents/skills/code-archaeologist/scripts/review/analyze.py --format text
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
python .agents/skills/code-archaeologist/scripts/review/scan_security.py --src ./src

# git churn/ownership + hotspot ranking (risk = commits x (1 + fan_in + fan_out))
python .agents/skills/code-archaeologist/scripts/review/git_insights.py --src ./src --top 10

# lines of code per file + LOC/complexity/depth per node (Python nodes)
python .agents/skills/code-archaeologist/scripts/review/metrics.py --src ./src --top 10

# TODO/FIXME/HACK markers + nodes nothing calls + files where every node is dead
python .agents/skills/code-archaeologist/scripts/review/debt.py --src ./src --top 10

# which nodes the test suite names, and which it never mentions
# (pytest, Jest, JUnit 5/Spring Boot, Go, Rust, .NET, RSpec, PHPUnit conventions)
python .agents/skills/code-archaeologist/scripts/review/tests_map.py --src ./src --top 15

# copy-pasted functions, found even when the names were changed
python .agents/skills/code-archaeologist/scripts/review/duplicates.py --src ./src --top 10
```

Every stage is runnable on its own (`build_wiki.py`, `build_graph.py`, `build_flow.py`,
`build_html.py`) — `archaeologist.py` only orchestrates them. Each script takes `--help`.

## Worked example

Running against the bundled `sample_src/` (a controller → service → repository/client trio on the
backend, an API client, a page module and two React components on the frontend, plus one small
API per framework shape — FastAPI, Flask, Express and Nest):

```console
# Structure: how two classes connect
$ trace_path.py --from OrderController --to OrderRepository
{ "path": ["OrderController", "OrderService", "OrderRepository"], "found": true }

# Structure: the frontend is in this map too — a component, what it renders and what it calls
$ search.py --kind component
OrderCard    component/ui  sample_src/frontend/OrderCard.tsx  Loads one order by id and renders it as a card.
StatusBadge  component/ui  sample_src/frontend/OrderCard.tsx  Renders one order's status as a coloured badge.

$ trace_path.py --from OrderCard --to StatusBadge
{ "path": ["OrderCard", "StatusBadge"], "found": true }

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
  grade D (69/100), 4 risk finding(s), 18 ranked hotspot(s)
```

Routes come from all four frameworks, and a handler carries a **list** of them because one
handler often serves several:

```console
$ context.py --node orders --graph .../flow_graph.json
**Routes:** `GET /legacy/orders`, `POST /legacy/orders`

$ search.py --kind endpoint --graph .../flow_graph.json
GET /orders/:id/status        endpoint/controller  sample_src/api_express/order_router.js:24
OrderController.create_order  endpoint/controller  sample_src/backend/order_controller.py:16
OrdersController.findOne      endpoint/controller  sample_src/api_nest/orders.controller.ts:16
order_detail                  endpoint/controller  sample_src/api_flask/order_routes.py:25
...
```

`GET /orders/:id/status` is an endpoint node in its own right: the Express route is registered
with an inline arrow, so there is no named function to hang it on. It is also what the
**unique-suffix fallback** exists for — the frontend calls `/api/orders/:id/status` while the
router registers `/orders/:id/status`, and the link is made only because exactly one route
matches. Two routes ending the same way are left unlinked rather than guessed.

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
  FIXME  sample_src/backend/order_repository.py:14 [OrderRepository.get]  parameterize this query
  TODO   sample_src/backend/payment_client.py:13 [PaymentClient.charge]   retry once on a gateway timeout
```

The two React components are *not* in that dead list. Nothing in the graph renders `OrderCard`,
but a framework mounts it — the same reason a route handler has no caller — so `kind: component`
counts as an entry point, exactly like `kind: endpoint`.

It also ships a small suite — `backend/tests/test_orders.py` (one pytest function, one
`unittest.TestCase`) and `frontend/order_page.test.ts` — so the test path has something to show:

```console
$ tests_map.py --src ./sample_src
Tests: 2 test file(s), 4/21 node(s) named by a test (19.0%)
  untested  OrderCard                    sample_src/frontend/OrderCard.tsx:11
  ...

$ context.py --node OrderService.place_order
## Covered by (1 test(s))
- `test_place_order_charges_and_saves`
```

Those two test nodes carry `layer: test`: they are never counted as dead code, their calls never
count as coupling, and the explorer's **Tests** checkbox hides them (25 nodes -> 23).

The generated `data/report/`, `data/structure/` and `data/flow/` folders in this repo are that
demo output, committed so you can read a real example before running anything.
