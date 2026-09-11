---
entity: getOrderEvents
kind: function
layer: client
class: 
source: sample_src/frontend/api_client.ts:36
lang: js
precision: name-matched
desc_source: docstring
---
# getOrderEvents

## What it does
match rather than the unique-suffix fallback that getOrderStatus needs.

## Signature
`getOrderEvents()`

## Calls
- [[handleOrderEvents]]

## Called by
- [[loadOrderHistory]]

## HTTP calls
- `GET /go/orders/:orderId/events`
