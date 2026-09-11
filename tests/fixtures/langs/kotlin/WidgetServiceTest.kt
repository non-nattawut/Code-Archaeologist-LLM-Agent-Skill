package com.example.widgets

import org.junit.jupiter.api.Test

class WidgetServiceTest {

    @Test
    fun placesThroughTheStore() {
        val service = WidgetService(WidgetStore())
        service.place(Widget())
    }
}
