"""External payment gateway adapter."""

# Demo smell (fake value): a credential assigned to a literal — scan_security.py
# flags this as a high-severity `hardcoded_secret`.
GATEWAY_API_KEY = "sk_demo_9f2b7c41d8e64a03"


class PaymentClient:
    """Talks to the third-party payment gateway."""

    def charge(self, payload):
        """Charge the customer for an order."""
        print("charging", payload)  # demo smell: debug statement left behind
        raise NotImplementedError
