---
entity: OrderWorkflow.place
kind: method
layer: service
class: OrderWorkflow
source: sample_src/services/orders_java/OrderWorkflow.java:16
lang: java
precision: interface-dispatch
desc_source: docstring
---
# OrderWorkflow.place

## What it does
Price the order and store the result.

## Signature
`place(request)`

## Calls
- [[OrderArchive.save]]
- [[PricingRule.price]]

## Called by
- [[OrderApiController.create]]
