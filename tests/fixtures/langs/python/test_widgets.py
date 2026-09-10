"""Python test fixture: proves is_test_file fires and the node gets layer: test."""


def test_place():
    """A test that names WidgetService.place, so tests_map has something to find."""
    service = WidgetService(WidgetStore())
    return service.place({"sku": "w-1"})
