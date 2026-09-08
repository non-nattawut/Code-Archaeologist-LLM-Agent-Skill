---
entity: EventStore.List
kind: method
layer: repository
class: EventStore
source: sample_src/services/orders_go/event_store.go:9
lang: go
approx: true
desc_source: docstring
---
# EventStore.List

## What it does
List returns the events recorded against one order.

## Signature
`List(orderID)`

## Calls
_None._

## Called by
- [[EventService.Events]]
