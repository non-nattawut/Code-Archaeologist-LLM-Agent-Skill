---
entity: InvoiceService
layer: service
source: sample_src/services/orders_cs/InvoiceService.cs
kind: class
lang: csharp
---
# InvoiceService

## Summary
Invoice rules: work out the total, then store it.

## Bases
_None._

## Decorators
_None._

## Methods
- `Issue()` — Issue an invoice and store it.
- `Find()` — Read one invoice back.
- `Total()` — Total for a whole request.
- `Total()` — Total for a quantity at a price. This is an overload: both signatures share one node id, which is one of the reasons this tier is marked approximate.

## References
- [[InvoiceStore]]
