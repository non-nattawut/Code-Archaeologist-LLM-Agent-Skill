// UI logic for the order page; delegates to the API client.
import { createOrder, getOrder } from "./api_client";

export async function submitOrder(form: object) {
  return createOrder(form);
}

export async function loadOrder(id: string) {
  const order = await getOrder(id);
  // Demo smell: raw HTML sink — scan_security.py flags this as medium severity.
  document.getElementById("order").innerHTML = JSON.stringify(order);
  return order;
}
