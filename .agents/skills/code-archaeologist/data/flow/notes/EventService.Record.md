---
entity: EventService.Record
kind: method
layer: service
class: EventService
source: sample_src/services/orders_go/event_service.go:14
lang: go
approx: true
desc_source: docstring
---
# EventService.Record

## What it does
Record appends one event for an order.

## Signature
`Record(kind, orderID)`

## Calls
- [[EventStore.Append]]

## Called by
- [[recordOrderEvent]]
