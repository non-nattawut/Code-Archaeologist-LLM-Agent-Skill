---
entity: OrderWorkflow
layer: service
source: sample_src/services/orders_java/OrderWorkflow.java:4
end: 28
kind: class
lang: java
---
# OrderWorkflow

## Summary
Application service: price an order, then archive it.

## Bases
_None._

## Decorators
- `Service`

## Methods
- `place()` — Price the order and store the result.
- `find()` — Read one order back out of the archive.

## References
- [[OrderArchive]]
- [[PricingRule]]
