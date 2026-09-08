---
entity: InvoiceController
layer: controller
source: sample_src/services/orders_cs/InvoiceController.cs
kind: class
lang: csharp
approx: true
---
# InvoiceController

## Summary
HTTP entry point for invoices.

## Bases
- `ControllerBase`

## Decorators
- `ApiController`
- `Route`

## Methods
- `Create()` — Issue an invoice for one order.
- `Find()` — Fetch one invoice by id.

## References
- [[InvoiceService]]
