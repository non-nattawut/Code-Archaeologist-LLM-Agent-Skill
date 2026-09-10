package com.example.widgets;

/** Java test fixture: proves is_test_file fires on the *Test.java convention. */
public class WidgetServiceTest {

    private final WidgetService service = new WidgetService(new WidgetStore());

    @Test
    public void placesThroughTheStore() {
        this.service.place(new Widget());
    }
}
