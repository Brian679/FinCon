from django.urls import path

from . import views as v

app_name = "workflow"
urlpatterns = [
    path("tasks/", v.TaskList.as_view(), name="tasks"),
    path("tasks/new/", v.task_new, name="task_new"),
    path("tasks/<uuid:pk>/", v.task_detail, name="task"),
    path("complaints/", v.ComplaintList.as_view(), name="complaints"),
    path("complaints/new/", v.ComplaintCreate.as_view(), name="complaint_new"),
    path("complaints/<uuid:pk>/", v.complaint_detail, name="complaint"),
    path("requests/", v.RequestList.as_view(), name="requests"),
    path("requests/new/", v.RequestCreate.as_view(), name="request_new"),
    path("requests/<uuid:pk>/", v.request_detail, name="request"),
    path("correspondence/", v.CorrespondenceList.as_view(), name="correspondence"),
    path("correspondence/new/", v.CorrespondenceCreate.as_view(), name="correspondence_new"),
    path("correspondence/<uuid:pk>/", v.CorrespondenceUpdate.as_view(), name="correspondence_edit"),
    path("correspondence/<uuid:pk>/view/", v.letter_detail, name="letter"),
    path("correspondence/<uuid:pk>/<str:action>/", v.letter_action, name="letter_action"),
    path("correspondence/incoming/", v.letter_new, name="letter_new"),
    path("incoming-mail/", v.InTray.as_view(), name="in_tray"),
    path("phone-messages/", v.phone_messages, name="phone_messages"),
    path("files/<str:kind>/<uuid:pk>/add/", v.attach, name="attach"),
    path("files/<uuid:pk>/", v.attachment_file, name="attachment"),
    path("funds/", v.FundsList.as_view(), name="funds"),
    path("funds/new/", v.fund_form, name="fund_new"),
    path("funds/<uuid:pk>/", v.FundsDetail.as_view(), name="fund"),
    path("funds/<uuid:pk>/edit/", v.fund_form, name="fund_edit"),
    path("funds/<uuid:pk>/action/", v.fund_action, name="fund_action"),
    path("memos/", v.MemoList.as_view(), name="memos"),
    path("memos/new/", v.memo_new, name="memo_new"),
    path("memos/<uuid:pk>/", v.memo_detail, name="memo"),
]
