"""Python extraction fixture: store, service, controller, one route."""


class WidgetStore:
    """Persists widgets."""

    def save(self, item):
        """Store one widget."""
        return item


class WidgetService:
    """Applies widget rules, then persists."""

    def __init__(self, store: WidgetStore):
        self.store = store

    def place(self, item):
        """Place one widget through the store."""
        return self.store.save(item)


class WidgetController:
    """HTTP entry point for widgets."""

    def __init__(self, service: WidgetService):
        self.service = service

    @router.post("/widgets")
    def create(self, item):
        """POST /widgets."""
        return self.service.place(item)
