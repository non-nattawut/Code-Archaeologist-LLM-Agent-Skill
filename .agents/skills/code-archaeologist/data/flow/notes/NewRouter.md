---
entity: NewRouter
kind: function
layer: controller
class: 
source: sample_src/services/orders_go/router.go:10
lang: go
desc_source: docstring
---
# NewRouter

## What it does
NewRouter wires the Go order-event endpoints. Two registration shapes, deliberately: a named handler, whose route attaches to that function's own node, and an inline literal, which has no node to attach to and so becomes an endpoint of its own.

## Signature
`NewRouter()`

## Calls
_None._

## Called by
_None (entry point)._
