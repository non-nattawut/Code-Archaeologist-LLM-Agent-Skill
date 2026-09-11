# Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
# used on decoded text would shift every name, line and doc below this point.
defmodule WidgetStore do
  @moduledoc "Persists widgets."
  @label "寸法 📦 größe"

  @doc "Store one widget — größe 寸法 📦."
  def save(item) do
    item
  end

  @doc "Größe of the store — 寸法."
  def größe do
    0
  end
end

defmodule WidgetService do
  @moduledoc "Applies widget rules, then persists."

  @doc "Place one widget through the store."
  def place(item) do
    WidgetStore.save(item)
  end

  @doc "Hand-counted: complexity 6 (1 + for, if, and, if, if), depth 2, 2 params."
  def grade(score, bonus) do
    total = score
    for b <- bonus do
      if b > 0 and total < 100 do
        IO.puts(b)
      end
    end
    if total > 90 do
      "A"
    else
      if total > 50 do
        "B"
      else
        "C"
      end
    end
  end
end
