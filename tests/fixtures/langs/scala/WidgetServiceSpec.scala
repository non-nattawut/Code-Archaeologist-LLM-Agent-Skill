package widgets

class WidgetServiceSpec {
  def placesThroughTheStore(): Unit = {
    val service = new WidgetService(new WidgetStore())
    service.place("w")
  }
}
