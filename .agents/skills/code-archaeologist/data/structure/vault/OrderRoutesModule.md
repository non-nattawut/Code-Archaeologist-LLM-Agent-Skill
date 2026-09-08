---
entity: OrderRoutesModule
layer: controller
source: sample_src/api_flask/order_routes.py
kind: module
lang: py
approx: false
---
# OrderRoutesModule

## Summary
Flask routes for the legacy orders API.

Two things in this file that no other sample exercises: Flask's normal shape is a
route decorator on a module-level `def` rather than a class method, and one handler
serving several verbs through `methods=[...]`. Mounted under /legacy so it does not
compete with the FastAPI controller for the same paths.

## Bases
_None._

## Decorators
_None._

## Methods
- `orders()` — List orders, or place a new one - one handler, two verbs.
- `order_detail()` — Fetch one order by id. Flask's `<int:id>` converter normalizes like any param.

## References
- [[OrderService]]
