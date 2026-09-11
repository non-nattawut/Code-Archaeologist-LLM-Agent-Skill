"""Views the URL tables point at."""


class OrderView:
    """Class-based view: one handler per HTTP method it defines."""

    def get(self, request, order_id):
        """Show one order."""
        return order_id

    def post(self, request, order_id):
        """Update one order."""
        return order_id


def order_list(request):
    """List orders."""
    return fetch_orders()


def legacy_order(request, slug):
    """The old slug URL."""
    return slug


def api_status(request):
    """Health of the API."""
    return "ok"


def fetch_orders():
    """Every order."""
    return []
