from core.crud import BaseModelForm, date_widgets

from .models import AuditFinding, LeaveRequest, Project, StandApplication


class LeaveForm(BaseModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "reason"]
        widgets = date_widgets("start_date", "end_date")

    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]:
            self.add_error("end_date", "End date is before the start date.")
        return data


class StandForm(BaseModelForm):
    class Meta:
        model = StandApplication
        fields = ["applicant_name", "national_id", "phone", "stand_type", "preferred_location", "ward", "notes"]


class ProjectForm(BaseModelForm):
    class Meta:
        model = Project
        fields = ["name", "category", "department", "ward", "location", "description", "budget", "budget_line", "funder",
                  "start_date", "end_date", "progress", "status", "manager"]
        widgets = date_widgets("start_date", "end_date")


class FindingForm(BaseModelForm):
    class Meta:
        model = AuditFinding
        fields = ["audit_type", "department", "title", "finding", "risk_rating", "recommendation", "implementation_date"]
        widgets = date_widgets("implementation_date")
