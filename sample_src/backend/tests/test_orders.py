"""Demo tests: both common Python styles, so the skill has real test code to classify.

These call the production classes directly, which is what gives the flow map its
test -> production edges — the ones `context.py` reports under "Covered by".
"""
import unittest

from order_repository import OrderRepository
from order_service import OrderService
from payment_client import PaymentClient


def test_place_order_charges_and_saves():
    """pytest style: placing an order goes through payment and persistence."""
    service = OrderService(OrderRepository(), PaymentClient())
    assert service.place_order({"id": 1})


class OrderRepositoryTest(unittest.TestCase):
    """unittest style: detected the same way, by the file it lives in."""

    def test_get_returns_the_row(self):
        """Reading an order back by id returns something."""
        repository = OrderRepository()
        self.assertIsNotNone(repository.get(1))
