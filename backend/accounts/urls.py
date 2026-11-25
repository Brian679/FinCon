from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("home/", views.home, name="home"),
    path("password/", views.password_change, name="password_change"),
    path("users/", views.UserListView.as_view(), name="users"),
    path("users/new/", views.user_form, name="user_new"),
    path("users/<int:pk>/", views.user_form, name="user_edit"),
    path("users/<int:pk>/unlock/", views.user_unlock, name="user_unlock"),
]
