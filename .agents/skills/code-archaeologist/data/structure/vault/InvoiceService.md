---
entity: InvoiceService
layer: service
source: sample_src/services/orders_cs/InvoiceService.cs:4
end: 39
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
- `Total()` — Total for a quantity at a price. This is an overload: each signature is its own node, and a call picks one by argument count and then by any argument type the source states.

## References
- [[InvoiceStore]]
