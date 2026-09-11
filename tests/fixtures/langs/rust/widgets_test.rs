#[test]
fn places_through_the_store() {
    let service = WidgetService { store: WidgetStore { rows: Vec::new() } };
    service.place(String::from("w"));
}
