// Demo frontend test (Jest/Vitest style). Detected by the `.test.ts` suffix, so
// it counts as the test suite rather than as application code.
import { loadOrder, submitOrder } from "./order_page";

describe("order page", () => {
  it("submits a new order", async () => {
    await submitOrder({ sku: "demo" });
  });

  it("loads an order for display", async () => {
    await loadOrder("1");
  });
});
