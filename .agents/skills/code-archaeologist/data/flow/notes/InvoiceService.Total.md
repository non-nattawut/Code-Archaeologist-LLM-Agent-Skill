---
entity: InvoiceService.Total
kind: method
layer: service
class: InvoiceService
source: sample_src/services/orders_cs/InvoiceService.cs:35
lang: csharp
approx: true
desc_source: docstring
---
# InvoiceService.Total

## What it does
Total for a quantity at a price. This is an overload: both signatures share one node id, which is one of the reasons this tier is marked approximate.

## Signature
`Total(request)`
`Total(unitPrice, units)`

## Calls
_None._

## Called by
- [[InvoiceService.Issue]]
