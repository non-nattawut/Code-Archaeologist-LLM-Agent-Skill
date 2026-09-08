---
entity: createOrder
kind: function
layer: client
class: 
source: sample_src/frontend/api_client.ts:3
lang: js
desc_source: ai
---
# createOrder

## What it does
Frontend API client: POST /orders with the form payload and return the created order JSON.

## Signature
`createOrder()`

## Calls
- [[OrderController.create_order]]

## Called by
- [[submitOrder]]

## HTTP calls
- `POST /orders`
