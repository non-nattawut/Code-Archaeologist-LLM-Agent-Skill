"""HTTP layer for order operations."""
from fastapi import APIRouter

from order_service import OrderService

router = APIRouter()


class OrderController:
    """Handles inbound order requests and delegates to the service layer."""

    def __init__(self, service: OrderService):
        self.service = service

    @router.post("/orders")
    def create_order(self, payload):
        """POST /orders — create a new order."""
        return self.service.place_order(payload)

    @router.get("/orders/{order_id}")
    def get_order(self, order_id):
        """GET /orders/{id} — fetch a single order."""
        return self.service.find_order(order_id)
