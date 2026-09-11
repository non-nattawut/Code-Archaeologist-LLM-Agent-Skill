---
entity: InvoiceService.Issue
kind: method
layer: service
class: InvoiceService
source: sample_src/services/orders_cs/InvoiceService.cs:14
lang: csharp
desc_source: docstring
---
# InvoiceService.Issue

## What it does
Issue an invoice and store it.

## Signature
`Issue(request)`

## Calls
- [[InvoiceService.Total(InvoiceRequest)]]
- [[InvoiceStore.Put]]

## Called by
- [[InvoiceController.Create]]
