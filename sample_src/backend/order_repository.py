"""Persistence layer for orders."""


class OrderRepository:
    """Reads and writes orders to the database."""

    def save(self, order):
        """Insert a new order row."""
        raise NotImplementedError

    def get(self, order_id):
        """Select an order by id."""
        raise NotImplementedError
