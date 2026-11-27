from django.apps import AppConfig


class DepartmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "departments"
    verbose_name = "Departmental registers"

    def ready(self):
        from core import audit

        from . import models as m

        audit.register(m.LeaveRequest, m.StandApplication, m.Project, m.AuditFinding, m.Asset, m.AssetMaintenance, m.Incident,
                       m.CommunityActivity, m.BuildingPlan, m.Risk, m.CouncilMeeting, m.Resolution, m.ICTTicket, m.Policy, m.Road, m.PublicLight,
                       m.WorkOrder, m.RecordFile)
