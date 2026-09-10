---
entity: GET /go/healthz
kind: endpoint
layer: controller
class: 
source: sample_src/services/orders_go/router.go:16
lang: go
desc_source: docstring
---
# GET /go/healthz

## What it does
Liveness probe. No handler function to attach to, so the registration itself becomes the endpoint node.

## Signature
`GET /go/healthz`

## Calls
_None._

## Called by
_None (entry point)._
