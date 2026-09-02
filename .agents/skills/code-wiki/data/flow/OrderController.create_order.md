---
entity: OrderController.create_order
kind: endpoint
layer: controller
class: OrderController
source: sample_src/backend/order_controller.py:16
lang: py
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
- [[createOrder]]
