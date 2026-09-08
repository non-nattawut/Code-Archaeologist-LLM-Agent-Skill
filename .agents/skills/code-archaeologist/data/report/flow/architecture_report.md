# Architecture report — flow_graph.json

Generated 2026-09-08 14:11 UTC · 25 nodes · 16 edges

## Health: **D** (69/100)

| Deduction | Points |
| --- | --- |
| dead code | -6 |
| security | -25 |

Dead-code ratio 12.0% · cycles 0 · layer violations 0 · security findings 4

## Census

- Source: 12 file(s), 250 lines (py 50.4%, ts 27.6%, js 11.2%, tsx 10.8%)
- Layers: `client` 4, `controller` 10, `repository` 2, `service` 3, `test` 2, `ui` 4
- Kinds: `component` 2, `endpoint` 9, `function` 7, `method` 7
- Languages: `js` 12, `py` 13
- Edge types: `calls` 13, `http` 3

## Entry points (routes)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/orders` | `createOrderHandler` |
| GET | `/legacy/orders` | `orders` |
| POST | `/legacy/orders` | `orders` |
| GET | `/legacy/orders/<int:order_id>` | `order_detail` |
| POST | `/nest/orders` | `OrdersController.create` |
| GET | `/nest/orders/:id` | `OrdersController.findOne` |
| POST | `/orders` | `OrderController.create_order` |
| GET | `/orders/:id/status` | `GET /orders/:id/status` |
| GET | `/orders/{order_id}` | `OrderController.get_order` |

## Size & complexity

- 12 file(s), 250 lines — 165 code, 31 comment, 54 blank (comment ratio 12%)
- Complexity is McCabe: 1 + every branch. Python nodes only.

### Longest nodes

| Node | LOC | Complexity | Location |
| --- | --- | --- | --- |
| `orders` | 6 | 2 | `sample_src/api_flask/order_routes.py:16` |
| `OrderRepository.get` | 5 | 1 | `sample_src/backend/order_repository.py:11` |
| `PaymentClient.charge` | 5 | 1 | `sample_src/backend/payment_client.py:11` |
| `OrderRepositoryTest.test_get_returns_the_row` | 4 | 1 | `sample_src/backend/tests/test_orders.py:22` |
| `OrderService.place_order` | 4 | 1 | `sample_src/backend/order_service.py:13` |
| `order_detail` | 4 | 1 | `sample_src/api_flask/order_routes.py:25` |
| `test_place_order_charges_and_saves` | 4 | 2 | `sample_src/backend/tests/test_orders.py:13` |
| `OrderController.create_order` | 3 | 1 | `sample_src/backend/order_controller.py:16` |
| `OrderController.get_order` | 3 | 1 | `sample_src/backend/order_controller.py:21` |
| `OrderRepository.save` | 3 | 1 | `sample_src/backend/order_repository.py:7` |

### Most complex nodes

| Node | Complexity | LOC | Location |
| --- | --- | --- | --- |
| `orders` | 2 | 6 | `sample_src/api_flask/order_routes.py:16` |
| `test_place_order_charges_and_saves` | 2 | 4 | `sample_src/backend/tests/test_orders.py:13` |
| `OrderController.__init__` | 1 | 2 | `sample_src/backend/order_controller.py:12` |
| `OrderController.create_order` | 1 | 3 | `sample_src/backend/order_controller.py:16` |
| `OrderController.get_order` | 1 | 3 | `sample_src/backend/order_controller.py:21` |
| `OrderRepository.get` | 1 | 5 | `sample_src/backend/order_repository.py:11` |
| `OrderRepository.save` | 1 | 3 | `sample_src/backend/order_repository.py:7` |
| `OrderRepositoryTest.test_get_returns_the_row` | 1 | 4 | `sample_src/backend/tests/test_orders.py:22` |
| `OrderService.__init__` | 1 | 3 | `sample_src/backend/order_service.py:9` |
| `OrderService.find_order` | 1 | 3 | `sample_src/backend/order_service.py:18` |

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

### Orphans (no callers, not an entry point) — 3

| Node |
| --- |
| `getOrderStatus` |
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
| high | sql_injection | `sample_src/backend/order_repository.py:15` | `OrderRepository.get` | `return self.cursor.execute(f"SELECT * FROM orders WHERE id = {order_id}")` |
| high | hardcoded_secret | `sample_src/backend/payment_client.py:5` | — | `GATEWAY_API_KEY = "sk_...redacted"` |
| medium | dangerous_eval | `sample_src/frontend/order_page.ts:11` | `loadOrder` | `document.getElementById("order").innerHTML = JSON.stringify(order);` |
| low | debug_statement | `sample_src/backend/payment_client.py:14` | `PaymentClient.charge` | `print("charging", payload)  # demo smell: debug statement left behind` |

## Hotspots (churn × connectivity)

| Node | Commits | Fan-in | Fan-out | Risk | Owner |
| --- | --- | --- | --- | --- | --- |
| `OrderRepository.get` | 3 | 2 | 0 | 9 | non-nattawut |
| `OrderController.create_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderController.get_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderRepository.save` | 3 | 1 | 0 | 6 | non-nattawut |
| `OrderService.place_order` | 1 | 3 | 2 | 6 | Nattawut Rodthong |
| `PaymentClient.charge` | 3 | 1 | 0 | 6 | non-nattawut |
| `OrderService.find_order` | 1 | 2 | 1 | 4 | Nattawut Rodthong |
| `getOrder` | 1 | 2 | 1 | 4 | Nattawut Rodthong |
| `loadOrder` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `submitOrder` | 2 | 0 | 1 | 4 | Nattawut Rodthong |

## Debt — 2 marker(s) (FIXME 1, TODO 1), 3 dead node(s)

| Tag | Location | Owner | Note |
| --- | --- | --- | --- |
| FIXME | `sample_src/backend/order_repository.py:14` | `OrderRepository.get` | parameterize this query (see the demo smell below) |
| TODO | `sample_src/backend/payment_client.py:13` | `PaymentClient.charge` | retry once on a gateway timeout before giving up |

Files where every node is dead: `sample_src/frontend/order_page.ts`

## Tests — 4/21 node(s) named by a test (19.0%)

_2 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `GET /orders/:id/status` | controller | `sample_src/api_express/order_router.js:24` |
| `OrderCard` | ui | `sample_src/frontend/OrderCard.tsx:11` |
| `OrderController.create_order` | controller | `sample_src/backend/order_controller.py:16` |
| `OrderController.get_order` | controller | `sample_src/backend/order_controller.py:21` |
| `OrderRepository.save` | repository | `sample_src/backend/order_repository.py:7` |
| `OrderService.find_order` | service | `sample_src/backend/order_service.py:18` |
| `OrdersController.create` | controller | `sample_src/api_nest/orders.controller.ts:10` |
| `OrdersController.findOne` | controller | `sample_src/api_nest/orders.controller.ts:16` |
| `PaymentClient.charge` | client | `sample_src/backend/payment_client.py:11` |
| `StatusBadge` | ui | `sample_src/frontend/OrderCard.tsx:6` |
| `createOrder` | client | `sample_src/frontend/api_client.ts:8` |
| `createOrderHandler` | controller | `sample_src/api_express/order_router.js:11` |
| `getOrder` | client | `sample_src/frontend/api_client.ts:13` |
| `getOrderStatus` | client | `sample_src/frontend/api_client.ts:20` |
| `order_detail` | controller | `sample_src/api_flask/order_routes.py:25` |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
