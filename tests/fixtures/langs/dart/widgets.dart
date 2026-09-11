// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
// (Dart identifiers are ASCII-only, so here the non-ASCII lives in text, not a name.)
const label = "寸法 📦 größe";

/// Persists widgets.
class WidgetStore {
  /// Store one widget — größe 寸法 📦.
  String save(String item) {
    return item;
  }

  /// Size of the store — 寸法.
  int size() {
    return 0;
  }
}

/// Applies widget rules, then persists.
class WidgetService {
  final WidgetStore store;

  WidgetService(this.store);

  /// Place one widget through the store.
  String place(String item) {
    return store.save(item);
  }

  /// Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params.
  String grade(int score, List<int> bonus) {
    var total = score;
    for (final b in bonus) {
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
}
