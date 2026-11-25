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
]
