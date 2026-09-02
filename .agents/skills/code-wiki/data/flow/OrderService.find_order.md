---
entity: OrderService.find_order
kind: method
layer: service
class: OrderService
source: order_service.py:18
desc_source: docstring
---
# OrderService.find_order

## What it does
Look up an order by id.

## Signature
`find_order(self, order_id)`

## Calls
- [[OrderRepository.get]]

## Called by
- [[OrderController.get_order]]
