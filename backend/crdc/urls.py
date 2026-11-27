"""Development / single-host URLs: client site at /, staff site at /staff/.

In production the two sites run on separate hosts (see CLIENT_HOSTS and
STAFF_HOSTS) using crdc.urls_public and crdc.urls_staff.
"""
from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("", core_views.landing, name="landing"),
    path("sw.js", core_views.service_worker, name="sw"),
    path("system-admin/", admin.site.urls),
    path("staff/", include("accounts.urls")),
    path("", include("core.urls")),
    path("staff/finance/", include("finance.urls")),
    path("staff/", include("workflow.urls")),
    path("staff/", include("payroll.urls")),
    path("staff/", include("departments.urls")),
    path("staff/social/", include("social.urls")),
    path("staff/", include("departments.registers")),
    path("portal/", include("portal.urls")),
    path("api/v1/", include("api.urls")),
]

handler403 = "core.views.permission_denied"
