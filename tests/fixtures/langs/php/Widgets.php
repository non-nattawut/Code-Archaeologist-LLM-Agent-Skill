<?php
// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
const LABEL = "寸法 📦 größe";

/** Persists widgets. */
class WidgetStore
{
    /** Store one widget — größe 寸法 📦. */
    public function save(string $item): string
    {
        return $item;
    }

    /** Größe of the store — 寸法. */
    public function größe(): int
    {
        return 0;
    }
}

/** Applies widget rules, then persists. */
class WidgetService
{
    public function __construct(private WidgetStore $store)
    {
    }

    /** Place one widget through the store. */
    public function place(string $item): string
    {
        return $this->store->save($item);
    }

    /** Hand-counted: complexity 6 (1 + foreach, if, &&, if, elseif), depth 2, 2 params. */
    public function grade(int $score, array $bonus): string
    {
        $total = $score;
        foreach ($bonus as $b) {
            if ($b > 0 && $total < 100) {
                $total += $b;
            }
        }
        if ($total > 90) {
            return "A";
        } elseif ($total > 50) {
            return "B";
        }
        return "C";
    }
}
