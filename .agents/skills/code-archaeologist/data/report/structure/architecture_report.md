# Architecture report — graph.json

Generated 2026-09-08 14:02 UTC · 10 nodes · 12 edges

## Health: **C** (70/100)

| Deduction | Points |
| --- | --- |
| dead code | -5 |
| security | -25 |

Dead-code ratio 10.0% · cycles 0 · layer violations 0 · security findings 4

## Census

- Source: 9 file(s), 162 lines (py 60.5%, ts 22.8%, tsx 16.7%)
- Layers: `client` 2, `controller` 1, `repository` 1, `service` 1, `test` 2, `ui` 3
- Kinds: `class` 5, `component` 2, `module` 3
- Languages: `js` 4, `py` 6
- Edge types: `references` 12

## Entry points (routes)

_None._

## Size & complexity

- 9 file(s), 162 lines — 112 code, 13 comment, 37 blank (comment ratio 8%)
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
| `sample_src/frontend/OrderCard.tsx` | 27 | 20 |
| `sample_src/backend/tests/test_orders.py` | 25 | 18 |
| `sample_src/backend/order_controller.py` | 23 | 16 |
| `sample_src/backend/order_service.py` | 20 | 15 |
| `sample_src/backend/order_repository.py` | 15 | 9 |
| `sample_src/backend/payment_client.py` | 15 | 8 |
| `sample_src/frontend/order_page.test.ts` | 13 | 9 |
| `sample_src/frontend/order_page.ts` | 13 | 9 |
| `sample_src/frontend/api_client.ts` | 11 | 8 |

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
| `OrderService` | 1 | 3 | 2 | 6 | Nattawut Rodthong |
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

## Tests — 3/8 node(s) named by a test (37.5%)

_2 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `ApiClientModule` | client | `sample_src/frontend/api_client.ts` |
| `OrderCard` | ui | `sample_src/frontend/OrderCard.tsx` |
| `OrderController` | controller | `sample_src/backend/order_controller.py` |
| `OrderPageModule` | ui | `sample_src/frontend/order_page.ts` |
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
