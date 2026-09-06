---
entity: getOrder
kind: function
layer: client
class: 
source: sample_src/frontend/api_client.ts:8
lang: js
desc_source: ai
---
# getOrder

## What it does
Frontend API client: GET /orders/:id and return the parsed order JSON.

## Signature
`getOrder()`

## Calls
- [[OrderController.get_order]]

## Called by
- [[loadOrder]]

## HTTP calls
- `GET /orders/:orderId`
