// UI logic for the order page; delegates to the API client.
import { createOrder, getOrder, getOrderEvents } from "./api_client";

export async function submitOrder(form: object) {
  return createOrder(form);
}

export async function loadOrder(id: string) {
  const order = await getOrder(id);
  // Demo smell: raw HTML sink — scan_security.py flags this as medium severity.
  document.getElementById("order").innerHTML = JSON.stringify(order);
  return order;
}

// Loads one order's event history from the Go service.
export async function loadOrderHistory(id: string) {
  return getOrderEvents(id);
}
