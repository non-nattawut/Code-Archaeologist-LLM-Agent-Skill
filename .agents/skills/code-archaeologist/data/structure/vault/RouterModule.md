---
entity: RouterModule
layer: controller
source: sample_src/services/orders_go/router.go
kind: module
lang: go
---
# RouterModule

## Summary
_No docstring provided._

## Bases
_None._

## Decorators
_None._

## Methods
- `NewRouter()` — NewRouter wires the Go order-event endpoints. Two registration shapes, deliberately: a named handler, whose route attaches to that function's own node, and an inline literal, which has no node to attach to and so becomes an endpoint of its own.
- `handleOrderEvents()` — handleOrderEvents writes one order's event history.
- `recordOrderEvent()` — recordOrderEvent appends one event to an order's history.

## References
- [[EventService]]
