// TypeScript extraction fixture: a Nest controller, whose route is split across
// two decorators (@Controller gives the prefix, @Post the verb and suffix).
import { Controller, Post } from "@nestjs/common";

// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
const LABEL = "寸法 📦 größe";

/** Persists widgets. */
export class WidgetStore {
  // Store one widget — größe 寸法 📦.
  save(item: object) {
    return item;
  }

  // Größe of the store — 寸法.
  größe() {
    return 0;
  }
}

/** Applies widget rules, then persists. */
export class WidgetService {
  // Place one widget through the store.
  place(item: object) {
    return new WidgetStore().save(item);
  }

  // Hand-counted: complexity 6 (1 + for-of, if, &&, if, else if), depth 2, 2 params.
  grade(score: number, bonus: number[]) {
    let total = score;
    for (const b of bonus) {
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

@Controller("widgets")
export class WidgetController {
  // POST /widgets.
  @Post()
  create(item: object) {
    return new WidgetService().place(item);
  }
}
