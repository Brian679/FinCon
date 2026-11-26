from django.urls import path
from .auth import CouncilRefreshView

from . import views as v

app_name = "api"
urlpatterns = [
    path("health/", v.health, name="health"),
    path("auth/login/", v.LoginView.as_view(), name="login"),
    path("auth/refresh/", CouncilRefreshView.as_view(), name="refresh"),
    path("auth/register/", v.register_client, name="register"),
    path("me/", v.MeView.as_view(), name="me"),
    path("auth/password/", v.PasswordView.as_view(), name="password"),
    path("reports/finance/", v.FinanceReportView.as_view(), name="report_finance"),
    path("reports/executive/", v.ExecutiveView.as_view(), name="report_executive"),
    path("audit/", v.AuditTrailView.as_view(), name="audit"),
    path("sync/pull/", v.PullView.as_view(), name="pull"),
    path("sync/push/", v.PushView.as_view(), name="push"),
    path("client/link-account/", v.LinkAccountView.as_view(), name="link_account"),
    path("payments/", v.PaymentView.as_view(), name="payments"),
    path("payments/<str:ref>/", v.PaymentStatusView.as_view(), name="payment"),
    path("payments/paynow/result/", v.paynow_result, name="paynow_result"),
]
