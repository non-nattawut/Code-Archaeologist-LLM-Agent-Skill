# Architecture report — graph.json

Generated 2026-09-06 12:34 UTC · 4 nodes · 3 edges

## Health: **C** (75/100)

| Deduction | Points |
| --- | --- |
| security | -25 |

Dead-code ratio 0.0% · cycles 0 · layer violations 0 · security findings 4

## Census

- Source: 6 file(s), 97 lines (py 75.3%, ts 24.7%)
- Layers: `client` 1, `controller` 1, `repository` 1, `service` 1
- Kinds: `class` 4
- Languages: `py` 4
- Edge types: `references` 3

## Entry points (routes)

_None._

## Size & complexity

- 6 file(s), 97 lines — 65 code, 8 comment, 24 blank (comment ratio 8%)
- Complexity is McCabe: 1 + every branch. Python nodes only.

### Longest nodes

| Node | LOC | Complexity | Location |
| --- | --- | --- | --- |
| `OrderController` | 15 | 1 | `sample_src/backend/order_controller.py:9` |
| `OrderService` | 15 | 1 | `sample_src/backend/order_service.py:6` |
| `OrderRepository` | 12 | 1 | `sample_src/backend/order_repository.py:4` |
| `PaymentClient` | 8 | 1 | `sample_src/backend/payment_client.py:8` |

### Most complex nodes

| Node | Complexity | LOC | Location |
| --- | --- | --- | --- |
| `OrderController` | 1 | 15 | `sample_src/backend/order_controller.py:9` |
| `OrderRepository` | 1 | 12 | `sample_src/backend/order_repository.py:4` |
| `OrderService` | 1 | 15 | `sample_src/backend/order_service.py:6` |
| `PaymentClient` | 1 | 8 | `sample_src/backend/payment_client.py:8` |

### Largest files

| File | Lines | Code |
| --- | --- | --- |
| `sample_src/backend/order_controller.py` | 23 | 16 |
| `sample_src/backend/order_service.py` | 20 | 15 |
| `sample_src/backend/order_repository.py` | 15 | 9 |
| `sample_src/backend/payment_client.py` | 15 | 8 |
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
| `OrderRepository` | 3 | 1 | 0 | 6 | non-nattawut |
| `PaymentClient` | 3 | 1 | 0 | 6 | non-nattawut |
| `OrderController` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `OrderService` | 1 | 1 | 2 | 4 | Nattawut Rodthong |

## Debt — 2 marker(s) (FIXME 1, TODO 1), 0 dead node(s)

| Tag | Location | Owner | Note |
| --- | --- | --- | --- |
| FIXME | `sample_src/backend/order_repository.py:14` | `OrderRepository` | parameterize this query (see the demo smell below) |
| TODO | `sample_src/backend/payment_client.py:13` | `PaymentClient` | retry once on a gateway timeout before giving up |

## Tests — 0/4 node(s) named by a test (0.0%)

_0 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `OrderController` | controller | `sample_src/backend/order_controller.py` |
| `OrderRepository` | repository | `sample_src/backend/order_repository.py` |
| `OrderService` | service | `sample_src/backend/order_service.py` |
| `PaymentClient` | client | `sample_src/backend/payment_client.py` |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
