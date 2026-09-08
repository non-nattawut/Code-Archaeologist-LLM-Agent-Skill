---
entity: order_detail
kind: endpoint
layer: controller
class: 
source: sample_src/api_flask/order_routes.py:25
lang: py
desc_source: docstring
---
# order_detail

## What it does
Fetch one order by id. Flask's `<int:id>` converter normalizes like any param.

## Signature
`order_detail(order_id: int)`

## Calls
- [[OrderService.find_order]]

## Called by
_None (entry point)._
