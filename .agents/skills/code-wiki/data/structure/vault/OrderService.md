---
entity: OrderService
layer: service
source: sample_src/backend/order_service.py
kind: class
---
# OrderService

## Summary
Orchestrates order placement, payment, and persistence.

## Bases
_None._

## Decorators
_None._

## Methods
- `__init__()`
- `place_order()` — Charge payment then persist the order.
- `find_order()` — Look up an order by id.

## References
- [[OrderRepository]]
- [[PaymentClient]]
