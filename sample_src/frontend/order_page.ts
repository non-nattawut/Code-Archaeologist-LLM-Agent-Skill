// UI logic for the order page; delegates to the API client.
import { createOrder, getOrder } from "./api_client";

export async function submitOrder(form: object) {
  return createOrder(form);
}

export async function loadOrder(id: string) {
  return getOrder(id);
}
