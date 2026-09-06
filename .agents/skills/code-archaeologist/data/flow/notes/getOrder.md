---
entity: getOrder
kind: function
layer: client
class: 
source: sample_src/frontend/api_client.ts:8
lang: js
desc_source: auto
---
# getOrder

## What it does
Delegates to [[OrderController.get_order]].

## Signature
`getOrder()`

## Calls
- [[OrderController.get_order]]

## Called by
- [[loadOrder]]

## HTTP calls
- `GET /orders/:orderId`
