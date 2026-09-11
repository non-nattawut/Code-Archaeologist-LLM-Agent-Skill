# Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
# used on decoded text would shift every name, line and doc below this point.
LABEL = "寸法 📦 größe"

# Persists widgets.
class WidgetStore
  # Store one widget — größe 寸法 📦.
  def save(item)
    item
  end

  # Größe of the store — 寸法.
  def größe
    0
  end
end

# Applies widget rules, then persists.
class WidgetService
  def initialize(store)
    @store = store
  end

  # Place one widget through the store.
  def place(item)
    validate(item)
    @store.save(item)
  end

  # Reject an empty widget.
  def validate(item)
    item
  end

  # Hand-counted: complexity 6 (1 + for, if, &&, if, elsif), depth 2, 2 params.
  def grade(score, bonus)
    total = score
    for b in bonus
      if b > 0 && total < 100
        total += b
      end
    end
    if total > 90
      "A"
    elsif total > 50
      "B"
    else
      "C"
    end
  end
end
