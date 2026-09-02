// Thin HTTP client for the orders backend.

export async function createOrder(payload: object) {
  const res = await fetch("/orders", { method: "POST", body: JSON.stringify(payload) });
  return res.json();
}

export async function getOrder(orderId: string) {
  const res = await fetch(`/orders/${orderId}`, { method: "GET" });
  return res.json();
}
