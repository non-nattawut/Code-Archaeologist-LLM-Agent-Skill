---
entity: OrderController
layer: controller
source: sample_src/backend/order_controller.py:9
end: 23
kind: class
lang: py
---
# OrderController

## Summary
Handles inbound order requests and delegates to the service layer.

## Bases
_None._

## Decorators
_None._

## Methods
- `__init__()`
- `create_order()` — POST /orders — create a new order.
- `get_order()` — GET /orders/{id} — fetch a single order.

## References
- [[OrderService]]
