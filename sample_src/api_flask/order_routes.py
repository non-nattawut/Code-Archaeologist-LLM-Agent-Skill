"""Flask routes for the legacy orders API.

Two things in this file that no other sample exercises: Flask's normal shape is a
route decorator on a module-level `def` rather than a class method, and one handler
serving several verbs through `methods=[...]`. Mounted under /legacy so it does not
compete with the FastAPI controller for the same paths.
"""
from flask import Flask, jsonify, request

from backend.order_service import OrderService

app = Flask(__name__)


@app.route("/legacy/orders", methods=["GET", "POST"])
def orders():
    """List orders, or place a new one - one handler, two verbs."""
    service = OrderService()
    if request.method == "POST":
        return jsonify(service.place_order(request.json))
    return jsonify([])


@app.route("/legacy/orders/<int:order_id>")
def order_detail(order_id: int):
    """Fetch one order by id. Flask's `<int:id>` converter normalizes like any param."""
    service = OrderService()
    return jsonify(service.find_order(order_id))
