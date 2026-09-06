# Architecture report — flow_graph.json

Generated 2026-09-06 08:09 UTC · 13 nodes · 9 edges

## Health: **D** (67/100)

| Deduction | Points |
| --- | --- |
| dead code | -8 |
| security | -25 |

Dead-code ratio 15.4% · cycles 0 · layer violations 0 · security findings 4

## Census

- Source: 6 file(s), 95 lines (py 74.7%, ts 25.3%)
- Layers: `client` 3, `controller` 3, `repository` 2, `service` 3, `ui` 2
- Kinds: `endpoint` 3, `function` 4, `method` 6
- Languages: `js` 4, `py` 9
- Edge types: `calls` 7, `http` 2

## Entry points (routes)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/orders` | `OrderController.create_order` |
| GET | `/orders/{order_id}` | `OrderController.get_order` |

## Smells

### Circular dependencies

_None._

### Backwards layer dependencies

_None._

### Orphans (no callers, not an entry point) — 2

| Node |
| --- |
| `loadOrder` |
| `submitOrder` |

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
| high | sql_injection | `sample_src/backend/order_repository.py:14` | `OrderRepository.get` | `return self.cursor.execute(f"SELECT * FROM orders WHERE id = {order_id}")` |
| high | hardcoded_secret | `sample_src/backend/payment_client.py:5` | — | `GATEWAY_API_KEY = "sk_...redacted"` |
| medium | dangerous_eval | `sample_src/frontend/order_page.ts:11` | `loadOrder` | `document.getElementById("order").innerHTML = JSON.stringify(order);` |
| low | debug_statement | `sample_src/backend/payment_client.py:13` | `PaymentClient.charge` | `print("charging", payload)  # demo smell: debug statement left behind` |

## Hotspots (churn × connectivity)

| Node | Commits | Fan-in | Fan-out | Risk | Owner |
| --- | --- | --- | --- | --- | --- |
| `OrderController.create_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderController.get_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderRepository.get` | 2 | 1 | 0 | 4 | Nattawut Rodthong |
| `OrderRepository.save` | 2 | 1 | 0 | 4 | Nattawut Rodthong |
| `OrderService.place_order` | 1 | 1 | 2 | 4 | Nattawut Rodthong |
| `PaymentClient.charge` | 2 | 1 | 0 | 4 | Nattawut Rodthong |
| `loadOrder` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `submitOrder` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `OrderService.find_order` | 1 | 1 | 1 | 3 | Nattawut Rodthong |
| `createOrder` | 1 | 1 | 1 | 3 | Nattawut Rodthong |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
