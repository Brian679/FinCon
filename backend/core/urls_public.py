from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("charter/", views.charter, name="charter"),
    path("offline/", views.offline, name="offline"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
