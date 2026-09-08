---
entity: EventService.Events
kind: method
layer: service
class: EventService
source: sample_src/services/orders_go/event_service.go:9
lang: go
approx: true
desc_source: docstring
---
# EventService.Events

## What it does
Events returns every recorded event for one order.

## Signature
`Events(orderID)`

## Calls
- [[EventStore.List]]

## Called by
- [[handleOrderEvents]]
