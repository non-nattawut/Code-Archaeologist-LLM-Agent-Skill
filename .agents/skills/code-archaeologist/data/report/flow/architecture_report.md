# Architecture report — flow_graph.json

Generated 2026-09-10 11:01 UTC · 52 nodes · 32 edges

## Health: **D** (68/100)

| Deduction | Points |
| --- | --- |
| dead code | -7 |
| security | -25 |

Dead-code ratio 13.5% · cycles 0 · layer violations 0 · security findings 4

> **24 of 52 nodes are approximate.** Java, Go and C# resolve calls only through declared types, so this grade rests in part on edges that were inferred from declared types. Unresolvable calls (interface dispatch, overloads, lambdas) were dropped, not guessed — so the real coupling is at least this much.

## Census

- Source: 22 file(s), 529 lines (py 23.8%, java 19.3%, csharp 17.0%, ts 17.0%, go 12.5%, js 5.3%, tsx 5.1%)
- Layers: `client` 6, `controller` 18, `repository` 8, `service` 10, `test` 2, `ui` 5, `unknown` 3
- Kinds: `component` 2, `endpoint` 16, `function` 11, `method` 23
- Languages: `csharp` 7, `go` 8, `java` 9, `js` 15, `py` 13
- Edge types: `calls` 28, `http` 4

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

- 22 file(s), 529 lines — 343 code, 84 comment, 102 blank (comment ratio 16%)
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
| `sample_src/frontend/api_client.ts` | 39 | 22 |
| `sample_src/services/orders_cs/InvoiceService.cs` | 39 | 26 |
| `sample_src/services/orders_go/router.go` | 34 | 21 |
| `sample_src/api_express/order_router.js` | 28 | 14 |
| `sample_src/api_flask/order_routes.py` | 28 | 21 |
| `sample_src/services/orders_cs/InvoiceController.cs` | 28 | 21 |
| `sample_src/services/orders_java/OrderWorkflow.java` | 28 | 17 |
| `sample_src/frontend/OrderCard.tsx` | 27 | 20 |
| `sample_src/services/orders_java/PricingRule.java` | 26 | 14 |
| `sample_src/backend/tests/test_orders.py` | 25 | 18 |

## Smells

### Circular dependencies

_None._

### Backwards layer dependencies

_None._

### Orphans (no callers, not an entry point) — 7

| Node |
| --- |
| `FlatRate.price` |
| `TieredRate.price` |
| `createInvoice` |
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
| `getOrder` | 4 | 2 | 1 | 16 | Nattawut Rodthong |
| `createOrder` | 4 | 1 | 1 | 12 | Nattawut Rodthong |
| `getOrderEvents` | 4 | 1 | 1 | 12 | Nattawut Rodthong |
| `OrderRepository.get` | 3 | 2 | 0 | 9 | non-nattawut |
| `getOrderStatus` | 4 | 0 | 1 | 8 | Nattawut Rodthong |
| `OrderController.create_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderController.get_order` | 2 | 1 | 1 | 6 | Nattawut Rodthong |
| `OrderRepository.save` | 3 | 1 | 0 | 6 | non-nattawut |
| `OrderService.place_order` | 1 | 3 | 2 | 6 | Nattawut Rodthong |
| `PaymentClient.charge` | 3 | 1 | 0 | 6 | non-nattawut |

## Debt — 2 marker(s) (FIXME 1, TODO 1), 7 dead node(s)

| Tag | Location | Owner | Note |
| --- | --- | --- | --- |
| FIXME | `sample_src/backend/order_repository.py:14` | `OrderRepository.get` | parameterize this query (see the demo smell below) |
| TODO | `sample_src/backend/payment_client.py:13` | `PaymentClient.charge` | retry once on a gateway timeout before giving up |

Files where every node is dead: `sample_src/frontend/order_page.ts`

## Tests — 4/48 node(s) named by a test (8.3%)

_2 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `EventService.Events` | service | `sample_src/services/orders_go/event_service.go:9` |
| `EventService.Record` | service | `sample_src/services/orders_go/event_service.go:14` |
| `EventStore.Append` | repository | `sample_src/services/orders_go/event_store.go:14` |
| `EventStore.List` | repository | `sample_src/services/orders_go/event_store.go:9` |
| `FlatRate.price` | unknown | `sample_src/services/orders_java/PricingRule.java:14` |
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

## Duplicate code — 1 cluster(s), 4 duplicated line(s)

_Matched on token shape: identifiers and literals are normalized away, so a renamed copy still matches. Similar-looking code can cluster; it is a prompt to look, not proof._

| Tokens | Copies | Nodes |
| --- | --- | --- |
| 42 | 2 | `createInvoice`, `createOrder` |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
