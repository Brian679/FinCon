"""Staff website - council employees only."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core import views as core_views

urlpatterns = [
    path("", RedirectView.as_view(url="/staff/", permanent=False), name="landing"),
    path("sw.js", core_views.service_worker, name="sw"),
    path("system-admin/", admin.site.urls),
    path("staff/", include("accounts.urls")),
    path("", include("core.urls")),
    path("staff/finance/", include("finance.urls")),
    path("staff/", include("workflow.urls")),
    path("staff/", include("departments.urls")),
    path("api/v1/", include("api.urls")),
]

handler403 = "core.views.permission_denied"
