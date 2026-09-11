// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
let label = "寸法 📦 größe"

/// Persists widgets.
class WidgetStore {
    /// Store one widget — größe 寸法 📦.
    func save(_ item: String) -> String {
        return item
    }

    /// Größe of the store — 寸法.
    func größe() -> Int {
        return 0
    }
}

/// Applies widget rules, then persists.
class WidgetService {
    let store: WidgetStore

    init(store: WidgetStore) {
        self.store = store
    }

    /// Place one widget through the store.
    func place(_ item: String) -> String {
        return store.save(item)
    }

    /// Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params.
    func grade(score: Int, bonus: [Int]) -> String {
        var total = score
        for b in bonus {
            if b > 0 && total < 100 {
                total += b
            }
        }
        if total > 90 {
            return "A"
        } else if total > 50 {
            return "B"
        }
        return "C"
    }
}
