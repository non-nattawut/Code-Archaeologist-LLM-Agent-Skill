---
entity: RouterModule
layer: controller
source: sample_src/services/orders_go/router.go
kind: module
lang: go
approx: true
---
# RouterModule

## Summary
_No docstring provided._

## Bases
_None._

## Decorators
_None._

## Methods
- `NewRouter()` — NewRouter wires the Go order-event endpoints.
- `handleOrderEvents()` — handleOrderEvents writes one order's event history.
- `recordOrderEvent()` — recordOrderEvent appends one event to an order's history.

## References
- [[EventService]]
