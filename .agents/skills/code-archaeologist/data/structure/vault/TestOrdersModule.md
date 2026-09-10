---
entity: TestOrdersModule
layer: test
source: sample_src/backend/tests/test_orders.py
kind: module
lang: py
---
# TestOrdersModule

## Summary
Demo tests: both common Python styles, so the skill has real test code to classify.

These call the production classes directly, which is what gives the flow map its
test -> production edges — the ones `context.py` reports under "Covered by".

## Bases
_None._

## Decorators
_None._

## Methods
- `test_place_order_charges_and_saves()` — pytest style: placing an order goes through payment and persistence.

## References
- [[OrderRepository]]
- [[OrderService]]
- [[PaymentClient]]
