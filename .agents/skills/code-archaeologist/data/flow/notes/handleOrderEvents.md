---
entity: handleOrderEvents
kind: endpoint
layer: controller
class: 
source: sample_src/services/orders_go/router.go:23
lang: go
desc_source: docstring
---
# handleOrderEvents

## What it does
handleOrderEvents writes one order's event history.

## Signature
`handleOrderEvents(r, w)`

## Calls
- [[EventService.Events]]

## Called by
- [[getOrderEvents]]
