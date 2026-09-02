---
entity: OrderController.create_order
kind: endpoint
layer: controller
class: OrderController
source: order_controller.py:11
desc_source: docstring
---
# OrderController.create_order

## What it does
POST /orders — create a new order.

## Signature
`create_order(self, payload)`

## Calls
- [[OrderService.place_order]]

## Called by
_None (entry point)._
