// React view for one order: a card that renders a small status badge.
import { useEffect, useState } from "react";
import { getOrder } from "./api_client";

// Renders one order's status as a coloured badge.
export function StatusBadge(props: { status: string }) {
  return <span className={"badge badge-" + props.status}>{props.status}</span>;
}

// Loads one order by id and renders it as a card.
export function OrderCard(props: { orderId: string }) {
  const [order, setOrder] = useState(null);

  useEffect(() => {
    getOrder(props.orderId).then(setOrder);
  }, [props.orderId]);

  if (!order) {
    return <p className="order-card loading">Loading order...</p>;
  }
  return (
    <article className="order-card">
      <h3>{order.sku}</h3>
      <StatusBadge status={order.status} />
    </article>
  );
}
