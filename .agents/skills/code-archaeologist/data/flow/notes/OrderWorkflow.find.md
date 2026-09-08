---
entity: OrderWorkflow.find
kind: method
layer: service
class: OrderWorkflow
source: sample_src/services/orders_java/OrderWorkflow.java:25
lang: java
approx: true
desc_source: docstring
---
# OrderWorkflow.find

## What it does
Read one order back out of the archive.

## Signature
`find(id)`

## Calls
- [[OrderArchive.get]]

## Called by
- [[OrderApiController.findOne]]
