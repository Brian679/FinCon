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


from django import forms  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from core.crud import BootstrapFormMixin  # noqa: E402

from .models import Asset, BuildingPlan, CommunityActivity, CouncilMeeting, ICTTicket, Incident, Policy, Resolution, Risk  # noqa: E402


def _staff():
    U = get_user_model()
    return U.objects.filter(user_type=U.UserType.STAFF, is_active=True)


class IncidentForm(BaseModelForm):
    class Meta:
        model = Incident
        fields = ["incident_type", "title", "description", "ward", "location", "occurred_at", "households_affected", "people_injured",
                  "deaths", "livestock_lost", "crops_hectares", "lead_officer"]
        widgets = {"occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["lead_officer"].queryset = _staff().filter(department="SOCIAL")


class ActivityForm(BaseModelForm):
    class Meta:
        model = CommunityActivity
        fields = ["activity_type", "title", "department", "ward", "venue", "date"]
        widgets = date_widgets("date")


class BuildingPlanForm(BaseModelForm):
    class Meta:
        model = BuildingPlan
        fields = ["applicant_name", "phone", "stand_number", "location", "ward", "development_type", "description", "floor_area"]


class AssetForm(BaseModelForm):
    class Meta:
        model = Asset
        fields = ["name", "category", "department", "serial_number", "location", "ward", "acquisition_date", "cost", "useful_life_years",
                  "custodian", "condition", "status", "notes"]
        widgets = date_widgets("acquisition_date")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["custodian"].queryset = _staff()


class RiskForm(BaseModelForm):
    class Meta:
        model = Risk
        fields = ["department", "title", "description", "category", "likelihood", "impact", "existing_controls", "mitigation", "owner",
                  "review_date", "status"]
        widgets = date_widgets("review_date")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["owner"].queryset = _staff()
        for f in ("likelihood", "impact"):
            self.fields[f].widget = forms.Select(choices=[(i, str(i)) for i in range(1, 6)], attrs={"class": "form-select"})


class MeetingForm(BaseModelForm):
    class Meta:
        model = CouncilMeeting
        fields = ["meeting_type", "title", "date", "venue", "agenda", "minutes", "status"]
        widgets = {"date": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class ResolutionForm(BaseModelForm):
    class Meta:
        model = Resolution
        fields = ["text", "department", "responsible", "due_date"]
        widgets = date_widgets("due_date")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["responsible"].queryset = _staff()


class TicketForm(BaseModelForm):
    class Meta:
        model = ICTTicket
        fields = ["category", "subject", "description", "priority", "asset"]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["asset"].queryset = Asset.objects.alive().filter(category__in=["ICT", "EQUIP"])
        self.fields["asset"].required = False


class PolicyForm(BaseModelForm):
    class Meta:
        model = Policy
        fields = ["title", "kind", "department", "version", "summary", "status", "adopted_on", "review_date", "document"]
        widgets = date_widgets("adopted_on", "review_date")
