from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("staff/", views.dashboard, name="dashboard"),
    path("staff/executive/", views.executive, name="executive"),
    path("staff/notifications/", views.notifications, name="notifications"),
    path("notifications/<uuid:pk>/", views.notification_open, name="notification_open"),
    path("staff/audit-trail/", views.audit_trail, name="audit_trail"),
    path("charter/", views.charter, name="charter"),
    path("offline/", views.offline, name="offline"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
