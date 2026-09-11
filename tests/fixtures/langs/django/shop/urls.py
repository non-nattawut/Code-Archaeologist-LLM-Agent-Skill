"""Django URL table: a function view, a class-based view, a regex route, an include, and a
reference to a view that exists nowhere -- which must produce no route at all."""
from django.urls import include, path, re_path

from . import views
from .views import OrderView

# Größe — 寸法 📦: non-ASCII before the table, so its line numbers are exercised too.
urlpatterns = [
    path("orders/", views.order_list, name="order-list"),
    path("orders/<int:order_id>/", OrderView.as_view(), name="order-detail"),
    re_path(r"^legacy/(?P<slug>[-\w]+)/$", views.legacy_order),
    path("api/", include("shop.api_urls")),
    path("missing/", views.not_defined_anywhere),
]
