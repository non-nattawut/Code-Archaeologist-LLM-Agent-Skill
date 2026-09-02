---
entity: OrderService.place_order
kind: method
layer: service
class: OrderService
source: order_service.py:13
---
# OrderService.place_order

## What it does
Charge payment then persist the order.

## Signature
`place_order(self, payload)`

## Calls
- [[OrderRepository.save]]
- [[PaymentClient.charge]]

## Called by
- [[OrderController.create_order]]
