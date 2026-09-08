---
entity: OrderApiController
layer: controller
source: sample_src/services/orders_java/OrderApiController.java
kind: class
lang: java
approx: true
---
# OrderApiController

## Summary
HTTP entry point for the Java side of the order domain.

## Bases
_None._

## Decorators
- `RestController`
- `RequestMapping`

## Methods
- `create()` — Place a new order.
- `findOne()` — Fetch one order by id.

## References
- [[OrderWorkflow]]
