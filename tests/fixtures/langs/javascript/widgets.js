// JavaScript extraction fixture: store, service, an Express route with a named handler.
const express = require("express");

// Größe — 寸法 📦: 2-, 3- and 4-byte UTF-8 before every node, so a byte offset
// used on decoded text would shift every name, line and doc below this point.
const LABEL = "寸法 📦 größe";

const router = express.Router();

// Store one widget — größe 寸法 📦.
function saveWidget(item) {
  return item;
}

// Größe of the store — 寸法.
function größe() {
  return 0;
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
