---
entity: EventStore.Append
kind: method
layer: repository
class: EventStore
source: sample_src/services/orders_go/event_store.go:14
lang: go
desc_source: docstring
---
# EventStore.Append

## What it does
Append records one event against an order.

## Signature
`Append(kind, orderID)`

## Calls
_None._

## Called by
- [[EventService.Record]]
