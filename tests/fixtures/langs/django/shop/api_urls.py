"""Included under `api/` by urls.py, so its routes carry that prefix."""
from django.urls import path

from . import views

urlpatterns = [
    path("status/", views.api_status),
]
