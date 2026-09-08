---
entity: orders
kind: endpoint
layer: controller
class: 
source: sample_src/api_flask/order_routes.py:16
lang: py
desc_source: docstring
---
# orders

## What it does
List orders, or place a new one - one handler, two verbs.

## Signature
`orders()`

## Calls
- [[OrderService.place_order]]

## Called by
_None (entry point)._
