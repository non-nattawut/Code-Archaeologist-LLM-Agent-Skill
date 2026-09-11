// Thin HTTP client for the orders backend.
import axios from "axios";

// `axios.create(...)` is how most apps actually reach an API, so the sample uses
// it: calls on `api` are recognised as HTTP the same way `axios.get(...)` is.
const api = axios.create({ baseURL: "/" });

export async function createOrder(payload: object) {
  const res = await fetch("/orders", { method: "POST", body: JSON.stringify(payload) });
  return res.json();
}

// Deliberate copy-paste, so the duplicate pass has something to find: this is
// `createOrder` with every identifier renamed and nothing else changed. The
// token shapes are identical, so the two must cluster despite the new names.
export async function createInvoice(body: object) {
  const response = await fetch("/invoices", { method: "POST", body: JSON.stringify(body) });
  return response.json();
}

export async function getOrder(orderId: string) {
  const res = await fetch(`/orders/${orderId}`, { method: "GET" });
  return res.json();
}

// Reads the status through the Express router, which registers the path relative
// to its mount point - so this only links via the unique-suffix fallback.
export async function getOrderStatus(orderId: string) {
  const res = await api.get(`/api/orders/${orderId}/status`);
  return res.data;
}

// Reads an order's event history from the Go service. The Go router registers
// this path exactly, so the cross-stack edge comes from an exact (METHOD, path)
// match rather than the unique-suffix fallback that getOrderStatus needs.
export async function getOrderEvents(orderId: string) {
  const res = await api.get(`/go/orders/${orderId}/events`);
  return res.data;
}
