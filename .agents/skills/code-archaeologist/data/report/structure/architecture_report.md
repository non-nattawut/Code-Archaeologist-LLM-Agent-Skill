# Architecture report — graph.json

Generated 2026-09-10 05:43 UTC · 25 nodes · 22 edges

## Health: **D** (69/100)

| Deduction | Points |
| --- | --- |
| dead code | -6 |
| security | -25 |

Dead-code ratio 12.0% · cycles 0 · layer violations 0 · security findings 4

> **12 of 25 nodes are approximate.** Java, Go and C# resolve calls only through declared types, so this grade rests in part on edges that were inferred from declared types. Unresolvable calls (interface dispatch, overloads, lambdas) were dropped, not guessed — so the real coupling is at least this much.

## Census

- Source: 22 file(s), 529 lines (py 23.8%, java 19.3%, csharp 17.0%, ts 17.0%, go 12.5%, js 5.3%, tsx 5.1%)
- Layers: `client` 2, `controller` 7, `repository` 4, `service` 4, `test` 2, `ui` 3, `unknown` 3
- Kinds: `class` 17, `component` 2, `module` 6
- Languages: `csharp` 3, `go` 3, `java` 6, `js` 6, `py` 7
- Edge types: `references` 22

## Entry points (routes)

_None._

## Size & complexity

- 22 file(s), 529 lines — 343 code, 84 comment, 102 blank (comment ratio 16%)
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

### Orphans (no callers, not an entry point) — 3

| Node |
| --- |
| `FlatRate` |
| `OrderPageModule` |
| `TieredRate` |

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
| `ApiClientModule` | 4 | 2 | 0 | 12 | Nattawut Rodthong |
| `OrderRepository` | 3 | 3 | 0 | 12 | non-nattawut |
| `PaymentClient` | 3 | 3 | 0 | 12 | non-nattawut |
| `PricingRule` | 2 | 3 | 0 | 8 | Nattawut Rodthong |
| `OrderService` | 1 | 4 | 2 | 7 | Nattawut Rodthong |
| `OrderPageModule` | 3 | 0 | 1 | 6 | non-nattawut |
| `FlatRate` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `OrderController` | 2 | 0 | 1 | 4 | Nattawut Rodthong |
| `OrderRepositoryTest` | 1 | 0 | 3 | 4 | non-nattawut |
| `OrderWorkflow` | 1 | 1 | 2 | 4 | non-nattawut |

## Debt — 2 marker(s) (FIXME 1, TODO 1), 3 dead node(s)

| Tag | Location | Owner | Note |
| --- | --- | --- | --- |
| FIXME | `sample_src/backend/order_repository.py:14` | `OrderRepository` | parameterize this query (see the demo smell below) |
| TODO | `sample_src/backend/payment_client.py:13` | `PaymentClient` | retry once on a gateway timeout before giving up |

Files where every node is dead: `sample_src/frontend/order_page.ts`

## Tests — 3/23 node(s) named by a test (13.0%)

_2 test file(s). Name-based, not execution coverage: a node counts as referenced when a test file names it._

### Named by no test

| Node | Layer | Location |
| --- | --- | --- |
| `ApiClientModule` | client | `sample_src/frontend/api_client.ts` |
| `EventService` | service | `sample_src/services/orders_go/event_service.go` |
| `EventStore` | repository | `sample_src/services/orders_go/event_store.go` |
| `FlatRate` | unknown | `sample_src/services/orders_java/PricingRule.java` |
| `InvoiceController` | controller | `sample_src/services/orders_cs/InvoiceController.cs` |
| `InvoiceService` | service | `sample_src/services/orders_cs/InvoiceService.cs` |
| `InvoiceStore` | repository | `sample_src/services/orders_cs/InvoiceStore.cs` |
| `OrderApiController` | controller | `sample_src/services/orders_java/OrderApiController.java` |
| `OrderArchive` | repository | `sample_src/services/orders_java/OrderArchive.java` |
| `OrderCard` | ui | `sample_src/frontend/OrderCard.tsx` |
| `OrderController` | controller | `sample_src/backend/order_controller.py` |
| `OrderPageModule` | ui | `sample_src/frontend/order_page.ts` |
| `OrderRouterModule` | controller | `sample_src/api_express/order_router.js` |
| `OrderRoutesModule` | controller | `sample_src/api_flask/order_routes.py` |
| `OrderWorkflow` | service | `sample_src/services/orders_java/OrderWorkflow.java` |

## Dig deeper

```bash
# how does a request travel between two nodes?
python scripts/trace_path.py --graph <graph.json> --from <A> --to <B>
# what breaks if this changes?
python scripts/trace_path.py --graph <graph.json> --impact-of <node>
# what does my current diff affect?
python scripts/trace_path.py --graph <graph.json> --impact-of-diff
```
