"""Business logic for orders."""
from order_repository import OrderRepository
from payment_client import PaymentClient


class OrderService:
    """Orchestrates order placement, payment, and persistence."""

    def __init__(self, repository: OrderRepository, payments: PaymentClient):
        self.repository = repository
        self.payments = payments

    def place_order(self, payload):
        """Charge payment then persist the order."""
        self.payments.charge(payload)
        return self.repository.save(payload)

    def find_order(self, order_id):
        """Look up an order by id."""
        return self.repository.get(order_id)
