package com.example.widgets

// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.

/** Persists widgets. */
class WidgetStore {
    private val label = "寸法 📦 größe"

    /** Store one widget — größe 寸法 📦. */
    fun save(item: Widget): Widget {
        return item
    }

    /** Größe of the store — 寸法. */
    fun größe(): Int {
        return 0
    }
}

/** Applies widget rules, then persists. */
class WidgetService(private val store: WidgetStore) {

    /** Place one widget through the store. */
    fun place(item: Widget): Widget {
        return store.save(item)
    }

    /** Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params. */
    fun grade(score: Int, bonus: List<Int>): String {
        var total = score
        for (b in bonus) {
            if (b > 0 && total < 100) {
                total += b
            }
        }
        if (total > 90) {
            return "A"
        } else if (total > 50) {
            return "B"
        }
        return "C"
    }
}

/** HTTP entry point for widgets. */
@RestController
@RequestMapping("/widgets")
class WidgetController(private val service: WidgetService) {

    /** POST /widgets. */
    @PostMapping
    fun create(@RequestBody item: Widget): Widget {
        return service.place(item)
    }
}
