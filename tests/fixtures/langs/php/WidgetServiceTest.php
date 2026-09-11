<?php

class WidgetServiceTest
{
    public function testPlacesThroughTheStore(): void
    {
        $service = new WidgetService(new WidgetStore());
        $service->place("w");
    }
}
