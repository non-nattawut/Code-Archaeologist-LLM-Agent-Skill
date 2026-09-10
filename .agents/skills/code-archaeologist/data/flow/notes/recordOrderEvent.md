---
entity: recordOrderEvent
kind: endpoint
layer: controller
class: 
source: sample_src/services/orders_go/router.go:31
lang: go
desc_source: docstring
---
# recordOrderEvent

## What it does
recordOrderEvent appends one event to an order's history.

## Signature
`recordOrderEvent(r, w)`

## Calls
- [[EventService.Record]]

## Called by
_None (entry point)._
