# Phoenix route table: verb routes inside a scope with an alias, a resource cut down with only:,
# a nested scope, and a route to a controller that exists nowhere -- which must produce no route.
# Größe — 寸法 📦: non-ASCII before the table, so its line numbers are exercised too.
defmodule ShopWeb.Router do
  use ShopWeb, :router

  scope "/api", ShopWeb do
    get "/orders", OrderController, :index
    post "/orders", OrderController, :create
    resources "/invoices", InvoiceController, only: [:index, :show]

    scope "/admin", Admin do
      get "/reports", ReportController, :summary
    end

    get "/missing", GhostController, :boo
  end
end
