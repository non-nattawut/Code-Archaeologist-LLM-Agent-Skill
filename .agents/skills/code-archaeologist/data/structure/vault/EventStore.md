---
entity: EventStore
layer: repository
source: sample_src/services/orders_go/event_store.go
kind: class
lang: go
---
# EventStore

## Summary
EventStore is the in-memory event log. Stands in for a real database.

## Bases
_None._

## Decorators
_None._

## Methods
- `List()` — List returns the events recorded against one order.
- `Append()` — Append records one event against an order.

## References
_None._
