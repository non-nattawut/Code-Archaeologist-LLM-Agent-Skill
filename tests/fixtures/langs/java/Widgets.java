package com.example.widgets;

// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.

/** Persists widgets. */
public class WidgetStore {

    static final String LABEL = "寸法 📦 größe";

    /** Store one widget — größe 寸法 📦. */
    public Widget save(Widget item) {
        return item;
    }

    /** Größe of the store — 寸法. */
    public int größe() {
        return 0;
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
