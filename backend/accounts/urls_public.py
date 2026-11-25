"""The few account URLs the public client site needs (shared names with the staff site)."""
from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("home/", views.home, name="home"),
    path("logout/", views.logout_view, name="logout"),
    path("password/", views.password_change, name="password_change"),
]
