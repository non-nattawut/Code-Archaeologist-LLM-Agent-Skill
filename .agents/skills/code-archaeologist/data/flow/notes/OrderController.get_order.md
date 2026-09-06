---
entity: OrderController.get_order
kind: endpoint
layer: controller
class: OrderController
source: sample_src/backend/order_controller.py:21
lang: py
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
- [[getOrder]]
