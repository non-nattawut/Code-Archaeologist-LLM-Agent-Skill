# Rails route table: verb routes, a resource cut down with only:, a namespace, and a route to a
# controller that exists nowhere -- which must produce no route at all.
# Größe — 寸法 📦: non-ASCII before the table, so its line numbers are exercised too.
Rails.application.routes.draw do
  get "/orders", to: "orders#index"
  post "/orders", to: "orders#create"
  resources :invoices, only: [:index, :show]
  namespace :admin do
    get "reports", to: "reports#summary"
  end
  get "/missing", to: "ghosts#boo"
end
