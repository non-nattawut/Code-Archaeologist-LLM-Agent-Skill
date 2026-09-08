---
entity: GET /orders/:id/status
kind: endpoint
layer: controller
class: 
source: sample_src/api_express/order_router.js:24
lang: js
desc_source: docstring
---
# GET /orders/:id/status

## What it does
Report one order's current status.

## Signature
`GET /orders/:id/status`

## Calls
_None._

## Called by
- [[getOrderStatus]]
