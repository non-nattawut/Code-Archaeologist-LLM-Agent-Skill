// TypeScript test fixture: proves is_test_file fires on the *.test.ts convention.
import { WidgetService } from "./widgets.controller";

export function testPlacesThroughTheStore() {
  return new WidgetService().place({ sku: "w-1" });
}
