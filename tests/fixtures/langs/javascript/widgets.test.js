// JavaScript test fixture: proves is_test_file fires on the *.test.js convention.
const { placeWidget } = require("./widgets");

function testPlacesThroughTheStore() {
  return placeWidget({ sku: "w-1" });
}

module.exports = { testPlacesThroughTheStore };
