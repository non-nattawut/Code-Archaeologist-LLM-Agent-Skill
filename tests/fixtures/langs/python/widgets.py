"""Python extraction fixture: store, service, controller, one route."""

# Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
# used on decoded text would shift every name, line and doc below this point.
LABEL = "寸法 📦 größe"


class WidgetStore:
    """Persists widgets."""

    def save(self, item):
        """Store one widget — größe 寸法 📦."""
        return item

    def größe(self):
        """Größe of the store — 寸法."""
        return 0


def grade(score, bonus):
    """Hand-counted: complexity 6 (1 + for, if, and, if, elif), depth 2, 2 params."""
    total = score
    for b in bonus:
        if b > 0 and total < 100:
            total += b
    if total > 90:
        return "A"
    elif total > 50:
        return "B"
    return "C"


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
