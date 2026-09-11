defmodule ShopWeb.OrderController do
  @moduledoc "Orders, routed by router.ex."

  @doc "List orders."
  def index(conn, _params) do
    conn
  end

  @doc "Create an order."
  def create(conn, params) do
    index(conn, params)
  end
end
