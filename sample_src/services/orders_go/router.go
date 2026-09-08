package orders

import "net/http"

// NewRouter wires the Go order-event endpoints.
//
// Two registration shapes, deliberately: a named handler, whose route attaches
// to that function's own node, and an inline literal, which has no node to
// attach to and so becomes an endpoint of its own.
func NewRouter() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /go/orders/{id}/events", handleOrderEvents)
	mux.HandleFunc("POST /go/orders/{id}/events", recordOrderEvent)
	// Liveness probe. No handler function to attach to, so the registration
	// itself becomes the endpoint node.
	mux.HandleFunc("GET /go/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	return mux
}

// handleOrderEvents writes one order's event history.
func handleOrderEvents(w http.ResponseWriter, r *http.Request) {
	service := &EventService{store: &EventStore{}}
	for _, event := range service.Events(r.PathValue("id")) {
		w.Write([]byte(event))
	}
}

// recordOrderEvent appends one event to an order's history.
func recordOrderEvent(w http.ResponseWriter, r *http.Request) {
	service := &EventService{store: &EventStore{}}
	service.Record(r.PathValue("id"), r.FormValue("kind"))
}
