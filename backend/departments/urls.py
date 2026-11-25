from django.urls import path

from . import views as v

app_name = "departments"
urlpatterns = [
    path("leave/", v.LeaveList.as_view(), name="leave"),
    path("leave/new/", v.LeaveCreate.as_view(), name="leave_new"),
    path("leave/<uuid:pk>/", v.LeaveDetail.as_view(), name="leave_detail"),
    path("leave/<uuid:pk>/decide/", v.leave_decide, name="leave_decide"),
    path("hr/staff/", v.StaffDirectory.as_view(), name="staff"),
    path("social/stands/", v.StandList.as_view(), name="stands"),
    path("social/stands/new/", v.StandCreate.as_view(), name="stand_new"),
    path("social/stands/<uuid:pk>/", v.StandDetail.as_view(), name="stand"),
    path("social/stands/<uuid:pk>/action/", v.stand_action, name="stand_action"),
    path("technical/projects/", v.ProjectList.as_view(), name="projects"),
    path("technical/projects/new/", v.ProjectCreate.as_view(), name="project_new"),
    path("technical/projects/<uuid:pk>/", v.ProjectDetail.as_view(), name="project"),
    path("technical/projects/<uuid:pk>/edit/", v.ProjectUpdate.as_view(), name="project_edit"),
    path("audit/findings/", v.FindingList.as_view(), name="findings"),
    path("audit/findings/new/", v.FindingCreate.as_view(), name="finding_new"),
    path("audit/findings/<uuid:pk>/", v.FindingDetail.as_view(), name="finding"),
    path("audit/findings/<uuid:pk>/action/", v.finding_action, name="finding_action"),
]
