from django.urls import path

from . import views as v

app_name = "portal"
urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("login/", v.ClientLoginView.as_view(), name="login"),
    path("register/", v.register, name="register"),
    path("accounts/", v.accounts, name="accounts"),
    path("accounts/link/", v.link, name="link"),
    path("accounts/<uuid:pk>/", v.account_detail, name="account"),
    path("pay/", v.pay, name="pay"),
    path("payments/<str:ref>/", v.payment, name="payment"),
    path("receipts/", v.receipts, name="receipts"),
    path("receipts/<uuid:pk>/", v.receipt, name="receipt"),
    path("licences/", v.licences, name="licences"),
    path("licences/apply/", v.licence_apply, name="licence_apply"),
    path("licences/<uuid:pk>/certificate/", v.licence_certificate, name="licence_certificate"),
    path("complaints/", v.complaints, name="complaints"),
    path("complaints/new/", v.complaint_new, name="complaint_new"),
    path("problems/", v.requests_list, name="requests"),
    path("problems/new/", v.request_new, name="request_new"),
    path("stands/", v.stands, name="stands"),
    path("stands/new/", v.stand_new, name="stand_new"),
    path("notifications/", v.notifications, name="notifications"),
    path("my-stands/", v.claims, name="claims"),
    path("building-plans/", v.plans, name="plans"),
    path("building-plans/new/", v.plan_new, name="plan_new"),
    path("my-stands/register/", v.claim_new, name="claim_new"),
]
