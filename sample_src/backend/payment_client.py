"""External payment gateway adapter."""


class PaymentClient:
    """Talks to the third-party payment gateway."""

    def charge(self, payload):
        """Charge the customer for an order."""
        raise NotImplementedError
