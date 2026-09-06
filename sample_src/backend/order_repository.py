"""Persistence layer for orders."""


class OrderRepository:
    """Reads and writes orders to the database."""

    def save(self, order):
        """Insert a new order row."""
        raise NotImplementedError

    def get(self, order_id):
        """Select an order by id."""
        # Demo smell: SQL built by interpolation — scan_security.py flags this.
        return self.cursor.execute(f"SELECT * FROM orders WHERE id = {order_id}")
