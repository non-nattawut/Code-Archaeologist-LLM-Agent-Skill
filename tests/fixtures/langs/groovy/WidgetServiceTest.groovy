class WidgetServiceTest {
    void placesThroughTheStore() {
        WidgetService service = new WidgetService(store: new WidgetStore())
        service.place("w")
    }
}
