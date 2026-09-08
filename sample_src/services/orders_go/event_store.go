package orders

// EventStore is the in-memory event log. Stands in for a real database.
type EventStore struct {
	rows map[string][]string
}

// List returns the events recorded against one order.
func (s *EventStore) List(orderID string) []string {
	return s.rows[orderID]
}

// Append records one event against an order.
func (s *EventStore) Append(orderID string, kind string) {
	s.rows[orderID] = append(s.rows[orderID], kind)
}
