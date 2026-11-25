from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views as v

app_name = "api"
urlpatterns = [
    path("health/", v.health, name="health"),
    path("auth/login/", v.LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/register/", v.register_client, name="register"),
    path("me/", v.MeView.as_view(), name="me"),
    path("sync/pull/", v.PullView.as_view(), name="pull"),
    path("sync/push/", v.PushView.as_view(), name="push"),
    path("client/link-account/", v.LinkAccountView.as_view(), name="link_account"),
    path("payments/", v.PaymentView.as_view(), name="payments"),
    path("payments/<str:ref>/", v.PaymentStatusView.as_view(), name="payment"),
    path("payments/paynow/result/", v.paynow_result, name="paynow_result"),
]
