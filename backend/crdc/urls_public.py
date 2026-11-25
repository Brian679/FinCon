"""Public client website (residents, ratepayers, shop owners). No staff pages."""
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("", core_views.landing, name="landing"),
    path("sw.js", core_views.service_worker, name="sw"),
    path("", include("accounts.urls_public")),
    path("", include("core.urls_public")),
    path("portal/", include("portal.urls")),
    path("api/v1/", include("api.urls")),
]

handler403 = "core.views.permission_denied"
