package widgets

// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.

/** Persists widgets. */
class WidgetStore {
  private val label = "寸法 📦 größe"

  /** Store one widget — größe 寸法 📦. */
  def save(item: String): String = {
    item
  }

  /** Größe of the store — 寸法. */
  def größe(): Int = {
    0
  }
}

/** Applies widget rules, then persists. */
class WidgetService(store: WidgetStore) {

  /** Place one widget through the store. */
  def place(item: String): String = {
    store.save(item)
  }

  /** Hand-counted: complexity 6 (1 + for, if, &&, if, else if), depth 2, 2 params. */
  def grade(score: Int, bonus: List[Int]): String = {
    var total = score
    for (b <- bonus) {
      if (b > 0 && total < 100) {
        total += b
      }
    }
    if (total > 90) {
      "A"
    } else if (total > 50) {
      "B"
    } else {
      "C"
    }
  }
}
