# Architecture report — graph.json

Generated 2026-09-08 06:44 UTC · 6 nodes · 9 edges

## Health: **C** (75/100)

| Deduction | Points |
| --- | --- |
| security | -25 |

Dead-code ratio 0.0% · cycles 0 · layer violations 0 · security findings 4

## Census

- Source: 8 file(s), 135 lines (py 72.6%, ts 27.4%)
- Layers: `client` 1, `controller` 1, `repository` 1, `service` 1, `test` 2
- Kinds: `class` 5, `module` 1
- Languages: `py` 6
- Edge types: `references` 9

## Entry points (routes)

_None._

## Size & complexity

- 8 file(s), 135 lines — 92 code, 10 comment, 33 blank (comment ratio 7%)
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

### Orphans (no callers, not an entry point) — 0

_None._

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
| medium | dangerous_eval | `sample_src/frontend/order_page.ts:11` | — | `document.getElementById("order").innerHTML = JSON.stringify(order);` |
| low | debug_statement | `sample_src/backend/payment_client.py:14` | `PaymentClient` | `print("charging", payload)  # demo smell: debug statement left behind` |

## Hotspots (churn × connectivity)

| Node | Commits | Fan-in | Fan-out | Risk | Owner |
| --- | --- | --- | --- | --- | --- |
| `OrderRepository` | 3 | 3 | 0 | 12 | non-nattawut |
| `PaymentClient` | 3 | 3 | 0 | 12 | non-nattawut |
| `OrderService` | 1 | 3 | 2 | 6 | Nattawut Rodthong |
| `OrderController` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `OrderRepositoryTest` | 1 | 0 | 3 | 4 | non-nattawut |
| `TestOrdersModule` | 1 | 0 | 3 | 4 | non-nattawut |

## Debt — 2 marker(s) (FIXME 1, TODO 1), 0 dead node(s)

| Tag | Location | Owner | Note |
| --- | --- | --- | --- |
| FIXME | `sample_src/backend/order_repository.py:14` | `OrderRepository` | parameterize this query (see the demo smell below) |
| TODO | `sample_src/backend/payment_client.py:13` | `PaymentClient` | retry once on a gateway timeout before giving up |

## Tests — 3/4 node(s) named by a test (75.0%)

_2 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `OrderController` | controller | `sample_src/backend/order_controller.py` |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
