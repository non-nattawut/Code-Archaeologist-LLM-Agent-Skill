// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
#include <vector>

static const char *LABEL = "寸法 📦 größe";

/// Persists widgets.
class WidgetStore {
public:
    /// Store one widget — größe 寸法 📦.
    int save(int item) {
        return item;
    }

    /// Größe of the store — 寸法.
    int größe() {
        return 0;
    }
};

/// Applies widget rules, then persists.
class WidgetService {
public:
    /// Place one widget through the store.
    int place(int item) {
        return store.save(item);
    }

    /// Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params.
    static const char *grade(int score, const std::vector<int> &bonus) {
        int total = score;
        for (int b : bonus) {
            if (b > 0 && total < 100) {
                total += b;
            }
        }
        if (total > 90) {
            return "A";
        } else if (total > 50) {
            return "B";
        }
        return "C";
    }

private:
    WidgetStore store;
};
