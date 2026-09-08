// Express router for orders.
// Three things this file exercises: a named handler, which attaches its route to
// that function's own node; an inline arrow, which has no node to attach to and so
// becomes an endpoint of its own; and a router-relative path (`/orders/:id/status`)
// that only matches a frontend call once the mount prefix is allowed for.
const express = require("express");

const router = express.Router();

// Create an order and return it.
function createOrderHandler(req, res) {
  const created = saveOrder(req.body);
  res.json(created);
}

// Persist an order. Stands in for a real repository call.
function saveOrder(payload) {
  return { id: 1, ...payload };
}

router.post("/api/orders", createOrderHandler);

// Report one order's current status.
router.get("/orders/:id/status", (req, res) => {
  res.json({ id: req.params.id, status: "open" });
});

module.exports = router;
