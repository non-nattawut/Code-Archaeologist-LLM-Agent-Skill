# Architecture report — flow_graph.json

Generated 2026-09-08 15:12 UTC · 50 nodes · 31 edges

## Health: **D** (69/100)

| Deduction | Points |
| --- | --- |
| dead code | -6 |
| security | -25 |

Dead-code ratio 12.0% · cycles 0 · layer violations 0 · security findings 4

> **23 of 50 nodes are approximate.** Java, Go and C# are read textually rather than parsed, so this grade rests in part on edges that were inferred from declared types. Unresolvable calls (interface dispatch, overloads, lambdas) were dropped, not guessed — so the real coupling is at least this much.

## Census

- Source: 22 file(s), 520 lines (py 24.2%, java 19.4%, csharp 17.3%, ts 15.8%, go 12.7%, js 5.4%, tsx 5.2%)
- Layers: `client` 5, `controller` 18, `repository` 8, `service` 10, `test` 2, `ui` 5, `unknown` 2
- Kinds: `component` 2, `endpoint` 16, `function` 10, `method` 22
- Languages: `csharp` 7, `go` 8, `java` 8, `js` 14, `py` 13
- Edge types: `calls` 27, `http` 4

## Entry points (routes)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/orders` | `createOrderHandler` |
| POST | `/cs/Invoice` | `InvoiceController.Create` |
| GET | `/cs/Invoice/{id}` | `InvoiceController.Find` |
| GET | `/go/healthz` | `GET /go/healthz` |
| GET | `/go/orders/{id}/events` | `handleOrderEvents` |
| POST | `/go/orders/{id}/events` | `recordOrderEvent` |
| POST | `/java/orders` | `OrderApiController.create` |
| GET | `/java/orders/{id}` | `OrderApiController.findOne` |
| GET | `/legacy/orders` | `orders` |
| POST | `/legacy/orders` | `orders` |
| GET | `/legacy/orders/<int:order_id>` | `order_detail` |
| POST | `/nest/orders` | `OrdersController.create` |
| GET | `/nest/orders/:id` | `OrdersController.findOne` |
| POST | `/orders` | `OrderController.create_order` |
| GET | `/orders/:id/status` | `GET /orders/:id/status` |
| GET | `/orders/{order_id}` | `OrderController.get_order` |

## Size & complexity

- 22 file(s), 520 lines — 339 code, 80 comment, 101 blank (comment ratio 15%)
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
| `sample_src/services/orders_cs/InvoiceService.cs` | 39 | 26 |
| `sample_src/services/orders_go/router.go` | 34 | 21 |
| `sample_src/frontend/api_client.ts` | 31 | 18 |
| `sample_src/api_express/order_router.js` | 28 | 14 |
| `sample_src/api_flask/order_routes.py` | 28 | 21 |
| `sample_src/services/orders_cs/InvoiceController.cs` | 28 | 21 |
| `sample_src/services/orders_java/OrderWorkflow.java` | 28 | 17 |
| `sample_src/frontend/OrderCard.tsx` | 27 | 20 |
| `sample_src/backend/tests/test_orders.py` | 25 | 18 |
| `sample_src/services/orders_java/OrderApiController.java` | 25 | 17 |

## Smells

### Circular dependencies

_None._

### Backwards layer dependencies

_None._

### Orphans (no callers, not an entry point) — 6

| Node |
| --- |
| `FlatRate.price` |
| `TieredRate.price` |
| `getOrderStatus` |
| `loadOrder` |
| `loadOrderHistory` |
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
| `getOrder` | 2 | 2 | 1 | 8 | Nattawut Rodthong |
| `OrderController.create_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderController.get_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderRepository.save` | 3 | 1 | 0 | 6 | non-nattawut |
| `OrderService.place_order` | 1 | 3 | 2 | 6 | Nattawut Rodthong |
| `PaymentClient.charge` | 3 | 1 | 0 | 6 | non-nattawut |
| `createOrder` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `getOrderEvents` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderService.find_order` | 1 | 2 | 1 | 4 | Nattawut Rodthong |

## Debt — 2 marker(s) (FIXME 1, TODO 1), 6 dead node(s)

| Tag | Location | Owner | Note |
| --- | --- | --- | --- |
| FIXME | `sample_src/backend/order_repository.py:14` | `OrderRepository.get` | parameterize this query (see the demo smell below) |
| TODO | `sample_src/backend/payment_client.py:13` | `PaymentClient.charge` | retry once on a gateway timeout before giving up |

Files where every node is dead: `sample_src/frontend/order_page.ts`, `sample_src/services/orders_java/PricingRule.java`

## Tests — 4/46 node(s) named by a test (8.7%)

_2 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `EventService.Events` | service | `sample_src/services/orders_go/event_service.go:9` |
| `EventService.Record` | service | `sample_src/services/orders_go/event_service.go:14` |
| `EventStore.Append` | repository | `sample_src/services/orders_go/event_store.go:14` |
| `EventStore.List` | repository | `sample_src/services/orders_go/event_store.go:9` |
| `FlatRate.price` | unknown | `sample_src/services/orders_java/PricingRule.java:13` |
| `GET /go/healthz` | controller | `sample_src/services/orders_go/router.go:16` |
| `GET /orders/:id/status` | controller | `sample_src/api_express/order_router.js:24` |
| `InvoiceController.Create` | controller | `sample_src/services/orders_cs/InvoiceController.cs:17` |
| `InvoiceController.Find` | controller | `sample_src/services/orders_cs/InvoiceController.cs:24` |
| `InvoiceService.Find` | service | `sample_src/services/orders_cs/InvoiceService.cs:21` |
| `InvoiceService.Issue` | service | `sample_src/services/orders_cs/InvoiceService.cs:14` |
| `InvoiceService.Total` | service | `sample_src/services/orders_cs/InvoiceService.cs:35` |
| `InvoiceStore.Get` | repository | `sample_src/services/orders_cs/InvoiceStore.cs:19` |
| `InvoiceStore.Put` | repository | `sample_src/services/orders_cs/InvoiceStore.cs:11` |
| `NewRouter` | controller | `sample_src/services/orders_go/router.go:10` |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
