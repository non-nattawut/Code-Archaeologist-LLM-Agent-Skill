import XCTest

class WidgetServiceTests: XCTestCase {
    func testPlacesThroughTheStore() {
        let service = WidgetService(store: WidgetStore())
        _ = service.place("w")
    }
}
