// JavaScript extraction fixture: store, service, an Express route with a named handler.
const express = require("express");

const router = express.Router();

// Store one widget.
function saveWidget(item) {
  return item;
}

// Place one widget through the store.
function placeWidget(item) {
  return saveWidget(item);
}

// Create a widget.
function createWidgetHandler(req, res) {
  res.json(placeWidget(req.body));
}

router.post("/widgets", createWidgetHandler);

module.exports = router;
