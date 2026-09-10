package com.example.widgets;

/** Persists widgets. */
public class WidgetStore {

    /** Store one widget. */
    public Widget save(Widget item) {
        return item;
    }
}

/** Applies widget rules, then persists. */
class WidgetService {

    private final WidgetStore store;

    public WidgetService(WidgetStore store) {
        this.store = store;
    }

    /** Place one widget through the store. */
    public Widget place(Widget item) {
        return this.store.save(item);
    }
}

/** HTTP entry point for widgets. */
@RestController
@RequestMapping("/widgets")
class WidgetController {

    private final WidgetService service;

    public WidgetController(WidgetService service) {
        this.service = service;
    }

    /** POST /widgets. */
    @PostMapping
    public Widget create(@RequestBody Widget item) {
        return this.service.place(item);
    }
}
