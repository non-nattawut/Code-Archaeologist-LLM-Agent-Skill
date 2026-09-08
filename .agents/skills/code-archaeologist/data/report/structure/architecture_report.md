# Architecture report — graph.json

Generated 2026-09-08 14:11 UTC · 13 nodes · 13 edges

## Health: **C** (71/100)

| Deduction | Points |
| --- | --- |
| dead code | -4 |
| security | -25 |

Dead-code ratio 7.7% · cycles 0 · layer violations 0 · security findings 4

## Census

- Source: 12 file(s), 250 lines (py 50.4%, ts 27.6%, js 11.2%, tsx 10.8%)
- Layers: `client` 2, `controller` 4, `repository` 1, `service` 1, `test` 2, `ui` 3
- Kinds: `class` 6, `component` 2, `module` 5
- Languages: `js` 6, `py` 7
- Edge types: `references` 13

## Entry points (routes)

_None._

## Size & complexity

- 12 file(s), 250 lines — 165 code, 31 comment, 54 blank (comment ratio 12%)
- Complexity is McCabe: 1 + every branch. Python nodes only.

### Longest nodes

| Node | LOC | Complexity | Location |
| --- | --- | --- | --- |
| `OrderController` | 15 | 1 | `sample_src/backend/order_controller.py:9` |
| `OrderService` | 15 | 1 | `sample_src/backend/order_service.py:6` |
| `OrderRepository` | 12 | 1 | `sample_src/backend/order_repository.py:4` |
| `PaymentClient` | 8 | 1 | `sample_src/backend/payment_client.py:8` |
| `OrderRepositoryTest` | 7 | 1 | `sample_src/backend/tests/test_orders.py:19` |

### Most complex nodes

| Node | Complexity | LOC | Location |
| --- | --- | --- | --- |
| `OrderController` | 1 | 15 | `sample_src/backend/order_controller.py:9` |
| `OrderRepository` | 1 | 12 | `sample_src/backend/order_repository.py:4` |
| `OrderRepositoryTest` | 1 | 7 | `sample_src/backend/tests/test_orders.py:19` |
| `OrderService` | 1 | 15 | `sample_src/backend/order_service.py:6` |
| `PaymentClient` | 1 | 8 | `sample_src/backend/payment_client.py:8` |

### Largest files

| File | Lines | Code |
| --- | --- | --- |
| `sample_src/api_express/order_router.js` | 28 | 14 |
| `sample_src/api_flask/order_routes.py` | 28 | 21 |
| `sample_src/frontend/OrderCard.tsx` | 27 | 20 |
| `sample_src/backend/tests/test_orders.py` | 25 | 18 |
| `sample_src/backend/order_controller.py` | 23 | 16 |
| `sample_src/frontend/api_client.ts` | 23 | 14 |
| `sample_src/api_nest/orders.controller.ts` | 20 | 12 |
| `sample_src/backend/order_service.py` | 20 | 15 |
| `sample_src/backend/order_repository.py` | 15 | 9 |
| `sample_src/backend/payment_client.py` | 15 | 8 |

## Smells

### Circular dependencies

_None._

### Backwards layer dependencies

_None._

### Orphans (no callers, not an entry point) — 1

| Node |
| --- |
| `OrderPageModule` |

## Anti-patterns & idioms

### High coupling (hubs)

_None._

### God objects

_None._

### Detected idioms

_None._

## Security & risk — 4 finding(s) (high 2, medium 1, low 1)

| Severity | Rule | Location | Owner | Snippet |
| --- | --- | --- | --- | --- |
| high | sql_injection | `sample_src/backend/order_repository.py:15` | `OrderRepository` | `return self.cursor.execute(f"SELECT * FROM orders WHERE id = {order_id}")` |
| high | hardcoded_secret | `sample_src/backend/payment_client.py:5` | `PaymentClient` | `GATEWAY_API_KEY = "sk_...redacted"` |
| medium | dangerous_eval | `sample_src/frontend/order_page.ts:11` | `OrderPageModule` | `document.getElementById("order").innerHTML = JSON.stringify(order);` |
| low | debug_statement | `sample_src/backend/payment_client.py:14` | `PaymentClient` | `print("charging", payload)  # demo smell: debug statement left behind` |

## Hotspots (churn × connectivity)

| Node | Commits | Fan-in | Fan-out | Risk | Owner |
| --- | --- | --- | --- | --- | --- |
| `OrderRepository` | 3 | 3 | 0 | 12 | non-nattawut |
| `PaymentClient` | 3 | 3 | 0 | 12 | non-nattawut |
| `OrderService` | 1 | 4 | 2 | 7 | Nattawut Rodthong |
| `OrderController` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `OrderPageModule` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `OrderRepositoryTest` | 1 | 0 | 3 | 4 | non-nattawut |
| `TestOrdersModule` | 1 | 0 | 3 | 4 | non-nattawut |
| `ApiClientModule` | 1 | 2 | 0 | 3 | Nattawut Rodthong |
| `OrderCard` | 1 | 0 | 2 | 3 | non-nattawut |
| `StatusBadge` | 1 | 1 | 0 | 2 | non-nattawut |

## Debt — 2 marker(s) (FIXME 1, TODO 1), 1 dead node(s)

| Tag | Location | Owner | Note |
| --- | --- | --- | --- |
| FIXME | `sample_src/backend/order_repository.py:14` | `OrderRepository` | parameterize this query (see the demo smell below) |
| TODO | `sample_src/backend/payment_client.py:13` | `PaymentClient` | retry once on a gateway timeout before giving up |

Files where every node is dead: `sample_src/frontend/order_page.ts`

## Tests — 3/11 node(s) named by a test (27.3%)

_2 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `ApiClientModule` | client | `sample_src/frontend/api_client.ts` |
| `OrderCard` | ui | `sample_src/frontend/OrderCard.tsx` |
| `OrderController` | controller | `sample_src/backend/order_controller.py` |
| `OrderPageModule` | ui | `sample_src/frontend/order_page.ts` |
| `OrderRouterModule` | controller | `sample_src/api_express/order_router.js` |
| `OrderRoutesModule` | controller | `sample_src/api_flask/order_routes.py` |
| `OrdersController` | controller | `sample_src/api_nest/orders.controller.ts` |
| `StatusBadge` | ui | `sample_src/frontend/OrderCard.tsx` |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
