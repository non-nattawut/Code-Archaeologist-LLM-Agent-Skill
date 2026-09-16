---
entity: ApiClientModule
layer: client
source: sample_src/frontend/api_client.ts
end: 
kind: module
lang: js
entry: 
---
# ApiClientModule

## Summary
_No docstring provided._

## Bases
_None._

## Decorators
_None._

## Methods
- `createOrder()`
- `createInvoice()` — Deliberate copy-paste, so the duplicate pass has something to find: this is `createOrder` with every identifier renamed and nothing else changed. The token shapes are identical, so the two must cluster despite the new names.
- `getOrder()`
- `getOrderStatus()` — Reads the status through the Express router, which registers the path relative to its mount point - so this only links via the unique-suffix fallback.
- `getOrderEvents()` — Reads an order's event history from the Go service. The Go router registers this path exactly, so the cross-stack edge comes from an exact (METHOD, path) match rather than the unique-suffix fallback that getOrderStatus needs.

## References
_None._
