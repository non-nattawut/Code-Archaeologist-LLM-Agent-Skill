// TypeScript extraction fixture: a Nest controller, whose route is split across
// two decorators (@Controller gives the prefix, @Post the verb and suffix).
import { Controller, Post } from "@nestjs/common";

/** Persists widgets. */
export class WidgetStore {
  // Store one widget.
  save(item: object) {
    return item;
  }
}

/** Applies widget rules, then persists. */
export class WidgetService {
  // Place one widget through the store.
  place(item: object) {
    return new WidgetStore().save(item);
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
