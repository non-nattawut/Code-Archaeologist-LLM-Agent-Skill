---
entity: OrderController.get_order
kind: endpoint
layer: controller
class: OrderController
source: order_controller.py:15
desc_source: docstring
---
# OrderController.get_order

## What it does
GET /orders/{id} — fetch a single order.

## Signature
`get_order(self, order_id)`

## Calls
- [[OrderService.find_order]]

## Called by
_None (entry point)._
