---
entity: OrderWorkflow.place
kind: method
layer: service
class: OrderWorkflow
source: sample_src/services/orders_java/OrderWorkflow.java:16
lang: java
approx: true
desc_source: docstring
---
# OrderWorkflow.place

## What it does
Price the order and store the result.

## Signature
`place(request)`

## Calls
- [[OrderArchive.save]]

## Called by
- [[OrderApiController.create]]
