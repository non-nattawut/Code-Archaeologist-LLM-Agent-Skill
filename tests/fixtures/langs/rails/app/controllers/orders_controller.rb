# Orders, routed by config/routes.rb.
class OrdersController
  # List orders.
  def index
    OrderQuery.new.all
  end

  # Create an order.
  def create
    index
  end
end
