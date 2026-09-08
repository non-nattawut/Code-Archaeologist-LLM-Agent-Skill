---
entity: EventService
layer: service
source: sample_src/services/orders_go/event_service.go
kind: class
lang: go
approx: true
---
# EventService

## Summary
EventService reports what has happened to an order.

## Bases
_None._

## Decorators
_None._

## Methods
- `Events()` — Events returns every recorded event for one order.
- `Record()` — Record appends one event for an order.

## References
- [[EventStore]]
