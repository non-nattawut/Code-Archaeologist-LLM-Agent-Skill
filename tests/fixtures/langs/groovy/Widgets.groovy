// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.

/** Persists widgets. */
class WidgetStore {
    String label = "寸法 📦 größe"

    /** Store one widget — größe 寸法 📦. */
    String save(String item) {
        return item
    }

    /** Größe of the store — 寸法. */
    int größe() {
        return 0
    }
}

/** Applies widget rules, then persists. */
class WidgetService {
    WidgetStore store

    /** Place one widget through the store. */
    String place(String item) {
        return store.save(item)
    }

    /** Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params. */
    String grade(int score, List<Integer> bonus) {
        int total = score
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
