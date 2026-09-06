---
entity: createOrder
kind: function
layer: client
class: 
source: sample_src/frontend/api_client.ts:3
lang: js
desc_source: docstring
---
# createOrder

## What it does
Thin HTTP client for the orders backend.

## Signature
`createOrder()`

## Calls
- [[OrderController.create_order]]

## Called by
- [[submitOrder]]

## HTTP calls
- `POST /orders`
