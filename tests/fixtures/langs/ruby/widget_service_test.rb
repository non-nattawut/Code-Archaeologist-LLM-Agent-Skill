class WidgetServiceTest
  def test_places_through_the_store
    service = WidgetService.new(WidgetStore.new)
    service.place("w")
  end
end
