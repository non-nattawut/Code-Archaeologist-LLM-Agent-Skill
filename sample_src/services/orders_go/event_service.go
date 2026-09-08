package orders

// EventService reports what has happened to an order.
type EventService struct {
	store *EventStore
}

// Events returns every recorded event for one order.
func (s *EventService) Events(orderID string) []string {
	return s.store.List(orderID)
}

// Record appends one event for an order.
func (s *EventService) Record(orderID string, kind string) {
	s.store.Append(orderID, kind)
}
