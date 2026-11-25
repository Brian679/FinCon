from django.contrib import messages
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import cap_required, staff_required
from core import audit
from core.crud import GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView
from core.models import AuditLog
from finance.services import notify

from . import forms
from .models import AuditFinding, LeaveRequest, Project, StandApplication

User = get_user_model()


# ---------------------------------------------------------------------- HR
class LeaveList(GenericListView):
    model = LeaveRequest
    required_caps = ("leave.apply",)
    title = "Leave applications"
    columns = [("Employee", "employee"), ("Type", "leave_type"), ("From", "start_date"), ("To", "end_date"), ("Working days", "days"),
               ("Decided by", "decided_by"), ("Status", "status")]
    detail_url_name = "departments:leave_detail"
    create_url_name = "departments:leave_new"

    def scope(self, qs):
        u = self.request.user
        if u.has_cap("hr.manage") or u.is_ceo:
            return qs
        if u.has_cap("leave.approve"):
            return qs.filter(employee__department=u.department)
        return qs.filter(employee=u)


class LeaveCreate(GenericCreateView):
    model = LeaveRequest
    form_class = forms.LeaveForm
    required_caps = ("leave.apply",)
    title = "Apply for leave"
    success_url = "/staff/leave/"

    def prepare(self, obj):
        obj.employee = self.request.user

    def after_save(self, obj):
        heads = [u for u in User.objects.filter(department=obj.employee.department, is_active=True) if u.is_head and u != obj.employee]
        if obj.employee.is_head:
            heads = [u for u in User.objects.filter(role="CEO", is_active=True)]
        notify(heads, f"Leave application: {obj.employee}", f"{obj.get_leave_type_display()} {obj.start_date} – {obj.end_date}", f"/staff/leave/{obj.pk}/")


class LeaveDetail(GenericDetailView):
    model = LeaveRequest
    required_caps = ("leave.apply",)
    template_name = "departments/leave_detail.html"
    fields = [("Employee", "employee"), ("Type", "leave_type"), ("From", "start_date"), ("To", "end_date"), ("Working days", "days"),
              ("Reason", "reason"), ("Decided by", "decided_by"), ("Decided at", "decided_at"), ("Comment", "decision_comment")]

    def scope(self, qs):
        return LeaveList.scope(self, qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lv, u = self.object, self.request.user
        ctx["can_decide"] = lv.status == "PENDING" and lv.employee_id != u.pk and (
            u.is_ceo or (u.has_cap("leave.approve") and u.department == lv.employee.department))
        return ctx


@cap_required("leave.approve")
@require_POST
def leave_decide(request, pk):
    lv = get_object_or_404(LeaveRequest, pk=pk, status=LeaveRequest.Status.PENDING)
    if lv.employee_id == request.user.pk or not (request.user.is_ceo or request.user.department == lv.employee.department):
        raise PermissionDenied
    lv.status = LeaveRequest.Status.APPROVED if request.POST.get("decision") == "approve" else LeaveRequest.Status.REJECTED
    lv.decided_by = request.user
    lv.decided_at = timezone.now()
    lv.decision_comment = request.POST.get("comment", "")
    lv.save()
    audit.log(AuditLog.Action.APPROVE if lv.status == "APPROVED" else AuditLog.Action.REJECT, lv)
    notify([lv.employee], f"Leave {lv.get_status_display().lower()}", lv.decision_comment)
    messages.success(request, "Decision recorded.")
    return redirect("departments:leave_detail", pk=pk)


class StaffDirectory(GenericListView):
    model = User
    required_caps = ("hr.view",)
    title = "Staff directory"
    columns = [("Employee no.", "employee_number"), ("Name", lambda u: u.get_full_name()), ("Department", "department"), ("Role", "role"),
               ("Phone", "phone"), ("Email", "email"), ("Active", "is_active")]
    search_fields = ["first_name", "last_name", "employee_number", "phone"]
    filter_field = "department"

    def base_queryset(self):
        return User.objects.filter(user_type=User.UserType.STAFF)


# --------------------------------------------------------- social services
class StandList(GenericListView):
    model = StandApplication
    required_caps = ("stands.view",)
    title = "Stand applications (housing development / stand allocation)"
    columns = [("Ref.", "reference"), ("Applied", "created_at"), ("Applicant", "applicant_name"), ("National ID", "national_id"),
               ("Type", "stand_type"), ("Preferred location", "preferred_location"), ("Allocated stand", "allocated_stand"), ("Status", "status")]
    search_fields = ["reference", "applicant_name", "national_id", "preferred_location"]
    detail_url_name = "departments:stand"
    create_url_name = "departments:stand_new"
    create_caps = ("stands.manage",)


class StandCreate(GenericCreateView):
    model = StandApplication
    form_class = forms.StandForm
    required_caps = ("stands.manage",)
    detail_url_name = "departments:stand"
    offline_capable = True


class StandDetail(GenericDetailView):
    model = StandApplication
    required_caps = ("stands.view",)
    template_name = "departments/stand_detail.html"
    fields = [("Applicant", "applicant_name"), ("National ID", "national_id"), ("Phone", "phone"), ("Stand type", "stand_type"),
              ("Preferred location", "preferred_location"), ("Ward", "ward"), ("Allocated stand", "allocated_stand"),
              ("Allocated by", "allocated_by"), ("Allocated at", "allocated_at"), ("Notes", "notes")]


@cap_required("stands.manage")
@require_POST
def stand_action(request, pk):
    st = get_object_or_404(StandApplication, pk=pk)
    action = request.POST.get("action")
    if action == "shortlist":
        st.status = StandApplication.Status.SHORTLISTED
    elif action == "allocate":
        if not request.user.has_cap("stands.allocate"):
            raise PermissionDenied("Only the Director of Social Services can allocate stands.")
        if not request.POST.get("stand"):
            messages.error(request, "Enter the stand number.")
            return redirect("departments:stand", pk=pk)
        st.status = StandApplication.Status.ALLOCATED
        st.allocated_stand = request.POST["stand"]
        st.allocated_by = request.user
        st.allocated_at = timezone.now()
        notify([st.applicant], f"Stand allocated: {st.allocated_stand}", "Visit council offices to sign the agreement and pay the deposit.")
    elif action == "reject":
        st.status = StandApplication.Status.REJECTED
        notify([st.applicant], f"Stand application {st.reference}", request.POST.get("note", ""))
    st.notes = (st.notes + "\n" + request.POST.get("note", "")).strip()
    st.save()
    messages.success(request, "Updated.")
    return redirect("departments:stand", pk=pk)


# -------------------------------------------------------- technical services
class ProjectList(GenericListView):
    model = Project
    required_caps = ("projects.view",)
    title = "Projects (roads, water, schools & clinics, lighting …)"
    columns = [("Code", "code"), ("Name", "name"), ("Category", "category"), ("Ward", "ward"), ("Budget", "budget"), ("Funder", "funder"),
               ("Progress %", "progress"), ("Status", "status")]
    search_fields = ["code", "name", "location", "funder"]
    detail_url_name = "departments:project"
    create_url_name = "departments:project_new"
    create_caps = ("projects.manage",)


class ProjectCreate(GenericCreateView):
    model = Project
    form_class = forms.ProjectForm
    required_caps = ("projects.manage",)
    detail_url_name = "departments:project"


class ProjectUpdate(GenericUpdateView):
    model = Project
    form_class = forms.ProjectForm
    required_caps = ("projects.manage",)
    detail_url_name = "departments:project"


class ProjectDetail(GenericDetailView):
    model = Project
    required_caps = ("projects.view",)
    edit_url_name = "departments:project_edit"
    edit_caps = ("projects.manage",)
    fields = [("Category", "category"), ("Department", "department"), ("Ward", "ward"), ("Location", "location"), ("Description", "description"),
              ("Budget (USD)", "budget"), ("Budget vote", "budget_line"), ("Funder", "funder"), ("Start", "start_date"), ("End", "end_date"),
              ("Progress %", "progress"), ("Project manager", "manager")]


# ------------------------------------------------------------ internal audit
class FindingList(GenericListView):
    model = AuditFinding
    required_caps = ("audit.findings_view", "audit.respond")
    title = "Internal audit findings"
    columns = [("Ref.", "reference"), ("Raised", "created_at"), ("Type", "audit_type"), ("Department", "department"), ("Title", "title"),
               ("Risk", "risk_rating"), ("Target date", "implementation_date"), ("Status", "status")]
    search_fields = ["reference", "title", "finding"]
    detail_url_name = "departments:finding"
    create_url_name = "departments:finding_new"
    create_caps = ("audit.findings_manage",)

    def scope(self, qs):
        u = self.request.user
        return qs if u.has_cap("audit.findings_view") else qs.filter(department=u.department)


class FindingCreate(GenericCreateView):
    model = AuditFinding
    form_class = forms.FindingForm
    required_caps = ("audit.findings_manage",)
    detail_url_name = "departments:finding"

    def prepare(self, obj):
        obj.auditor = self.request.user

    def after_save(self, obj):
        heads = [u for u in User.objects.filter(department=obj.department, is_active=True) if u.is_head]
        notify(heads + list(User.objects.filter(role="CEO", is_active=True)), f"Audit finding ({obj.get_risk_rating_display()}): {obj.title}",
               "Management response required.", f"/staff/audit/findings/{obj.pk}/")


class FindingDetail(GenericDetailView):
    model = AuditFinding
    required_caps = ("audit.findings_view", "audit.respond")
    template_name = "departments/finding_detail.html"
    fields = [("Type", "audit_type"), ("Department", "department"), ("Risk rating", "risk_rating"), ("Finding", "finding"),
              ("Recommendation", "recommendation"), ("Management response", "management_response"), ("Responded by", "responded_by"),
              ("Implementation date", "implementation_date"), ("Auditor", "auditor")]

    def scope(self, qs):
        return FindingList.scope(self, qs)


@staff_required
@require_POST
def finding_action(request, pk):
    f = get_object_or_404(AuditFinding, pk=pk)
    u = request.user
    action = request.POST.get("action")
    if action == "respond":
        if not (u.has_cap("audit.respond") and (u.department == f.department or u.is_ceo)):
            raise PermissionDenied
        f.management_response = request.POST.get("note", "")
        f.responded_by = u
        f.status = AuditFinding.Status.RESPONDED
        if request.POST.get("date"):
            f.implementation_date = request.POST["date"]
        notify([f.auditor], f"Management responded: {f.reference}", f.management_response[:200])
    elif action in ("implementing", "close"):
        if not u.has_cap("audit.findings_manage"):
            raise PermissionDenied
        f.status = AuditFinding.Status.IMPLEMENTING if action == "implementing" else AuditFinding.Status.CLOSED
    f.save()
    messages.success(request, "Updated.")
    return redirect("departments:finding", pk=pk)


# =====================================================================
# Charter registers: incidents, activities, building plans, assets,
# risks, council meetings & resolutions, ICT helpdesk, policies.
# =====================================================================
from django.db.models import Count, Q, Sum  # noqa: E402

from core.crud import run_action  # noqa: E402
from core.models import Department  # noqa: E402

from . import services  # noqa: E402
from .models import (  # noqa: E402
    Asset, BuildingPlan, CommunityActivity, CouncilMeeting, ICTTicket, Incident, Policy, Resolution, Risk,
)


def _dept_scope(view, qs, field="department"):
    u = view.request.user
    if u.sees_all_departments() or u.has_cap("assets.manage") and qs.model is Asset:
        return qs
    return qs.filter(**{field: u.department})


class ActionDetail(GenericDetailView):
    """Detail page with a list of stage actions rendered by departments/action_detail.html.

    ``actions(obj)`` returns dicts: {title, fields: [(name, label, kind, choices)], buttons: [(value, label, css)]}."""

    template_name = "departments/action_detail.html"
    action_url_name = None
    extra_sections = ()

    def actions(self, obj):
        return []

    def sections(self, obj):
        return []

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["actions"] = self.actions(self.object)
        ctx["sections"] = self.sections(self.object)
        ctx["action_url"] = reverse(self.action_url_name, args=[self.object.pk]) if self.action_url_name else ""
        return ctx


def _post_action(request, fn, obj, success="Updated."):
    data = {k: v for k, v in request.POST.items() if k not in ("csrfmiddlewaretoken", "action")}
    run_action(request, fn, obj, request.POST.get("action"), success=success, **data)


# -------------------------------------------------------------- incidents
class IncidentList(GenericListView):
    model = Incident
    required_caps = ("incidents.view",)
    title = "Incidents & disasters (Public Safety / Natural Resources)"
    columns = [("Ref.", "reference"), ("When", "occurred_at"), ("Type", "incident_type"), ("Title", "title"), ("Ward", "ward"),
               ("Households", "households_affected"), ("Injured", "people_injured"), ("Deaths", "deaths"), ("Status", "status")]
    search_fields = ["reference", "title", "location"]
    detail_url_name = "departments:incident"
    create_url_name = "departments:incident_new"
    create_caps = ("incidents.manage",)


@cap_required("incidents.manage")
def incident_new(request):
    form = forms.IncidentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        inc = run_action(request, services.report_incident, success="Incident reported – HOD and CEO notified.", **form.cleaned_data)
        if inc:
            return redirect("departments:incident", pk=inc.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Report incident / disaster", "offline_capable": False})


class IncidentDetail(ActionDetail):
    model = Incident
    required_caps = ("incidents.view",)
    action_url_name = "departments:incident_action"
    fields = [("Type", "incident_type"), ("Location", "location"), ("Ward", "ward"), ("Occurred", "occurred_at"), ("Description", "description"),
              ("Households affected", "households_affected"), ("People injured", "people_injured"), ("Deaths", "deaths"),
              ("Livestock lost", "livestock_lost"), ("Crops (ha)", "crops_hectares"), ("Response log", "response"),
              ("Reported by", "reported_by"), ("Lead officer", "lead_officer")]

    def actions(self, obj):
        if obj.status == Incident.Status.CLOSED or not self.request.user.has_cap("incidents.manage"):
            return []
        statuses = [(v, l) for v, l in Incident.Status.choices]
        return [{"title": "Update response", "fields": [("response", "Action taken / update", "textarea", None),
                                                        ("households_affected", "Households affected", "number", None),
                                                        ("status", "Status", "select", statuses)],
                 "buttons": [("update", "Save update", "primary")]}]


@cap_required("incidents.manage")
@require_POST
def incident_action(request, pk):
    inc = get_object_or_404(Incident, pk=pk)
    run_action(request, services.update_incident, inc, status=request.POST.get("status") or None, response=request.POST.get("response", ""),
               households_affected=request.POST.get("households_affected") or None, success="Incident updated.")
    return redirect("departments:incident", pk=pk)


# ------------------------------------------------------------- activities
class ActivityList(GenericListView):
    model = CommunityActivity
    required_caps = ("activities.manage", "activities.verify", "dept.overview")
    title = "Community programmes, campaigns & consultations"
    columns = [("Ref.", "reference"), ("Date", "date"), ("Type", "activity_type"), ("Title", "title"), ("Department", "department"),
               ("Ward", "ward"), ("Participants", "participants"), ("Officer", "officer"), ("Status", "status")]
    search_fields = ["reference", "title", "venue"]
    detail_url_name = "departments:activity"
    create_url_name = "departments:activity_new"
    create_caps = ("activities.manage",)

    def scope(self, qs):
        return _dept_scope(self, qs)


@cap_required("activities.manage")
def activity_new(request):
    form = forms.ActivityForm(request.POST or None, initial={"department": request.user.department})
    if request.method == "POST" and form.is_valid():
        act = run_action(request, services.plan_activity, success="Activity planned.", **form.cleaned_data)
        if act:
            return redirect("departments:activity", pk=act.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Plan a community activity / campaign / consultation"})


class ActivityDetail(ActionDetail):
    model = CommunityActivity
    required_caps = ("activities.manage", "activities.verify", "dept.overview")
    action_url_name = "departments:activity_action"
    fields = [("Type", "activity_type"), ("Department", "department"), ("Date", "date"), ("Venue", "venue"), ("Ward", "ward"),
              ("Participants", "participants"), ("Report", "report"), ("Officer", "officer"), ("Verified by", "verified_by")]

    def actions(self, obj):
        u, acts = self.request.user, []
        if obj.status in ("PLANNED", "DONE") and u.has_cap("activities.manage"):
            acts.append({"title": "Submit activity report", "fields": [("participants", "Number of participants", "number", None),
                                                                     ("report", "Report: outcome, issues raised, follow-up", "textarea", None)],
                         "buttons": [("report", "Submit report to HOD", "primary")]})
        if obj.status == "DONE" and services.is_head_of(u, obj.department) and obj.officer_id != u.pk:
            acts.append({"title": "Head of Department verification", "fields": [("note", "Comment", "text", None)],
                         "buttons": [("verify", "Verify report", "success"), ("return", "Return to officer", "outline-danger")]})
        return acts


@staff_required
@require_POST
def activity_action(request, pk):
    act = get_object_or_404(CommunityActivity, pk=pk)
    a = request.POST.get("action")
    if a == "report":
        run_action(request, services.report_activity, act, report=request.POST.get("report", ""), participants=request.POST.get("participants") or 0,
                   success="Report submitted to the head of department.")
    elif a in ("verify", "return"):
        run_action(request, services.verify_activity, act, a == "verify", request.POST.get("note", ""), success="Decision recorded.")
    return redirect("departments:activity", pk=pk)


# --------------------------------------------------------- building plans
class PlanList(GenericListView):
    model = BuildingPlan
    required_caps = ("plans.view",)
    title = "Building plans – development control (30 working days)"
    columns = [("Ref.", "reference"), ("Submitted", "created_at"), ("Applicant", "applicant_name"), ("Stand", "stand_number"),
               ("Location", "location"), ("Type", "development_type"), ("Due (charter)", "due_at"), ("Status", "status")]
    search_fields = ["reference", "applicant_name", "stand_number", "location"]
    detail_url_name = "departments:plan"
    create_url_name = "departments:plan_new"
    create_caps = ("plans.review",)


@cap_required("plans.review")
def plan_new(request):
    form = forms.BuildingPlanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plan = run_action(request, services.submit_building_plan, success="Plan captured.", **form.cleaned_data)
        if plan:
            return redirect("departments:plan", pk=plan.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Capture building plan submission"})


class PlanDetail(ActionDetail):
    model = BuildingPlan
    required_caps = ("plans.view",)
    action_url_name = "departments:plan_action"
    fields = [("Applicant", "applicant_name"), ("Phone", "phone"), ("Stand", "stand_number"), ("Location", "location"), ("Ward", "ward"),
              ("Development", "development_type"), ("Description", "description"), ("Floor area (m²)", "floor_area"), ("Fee", "fee"),
              ("Fee bill", lambda p: f"{p.bill.number} – {p.bill.get_status_display()}" if p.bill else "—"), ("Charter deadline", "due_at"),
              ("Reviewed by", "reviewed_by"), ("Review notes", "review_notes"), ("Decided by", "decided_by"), ("Decision", "decision_notes"),
              ("Inspections", "inspection_log")]

    def actions(self, p):
        u, S, acts = self.request.user, BuildingPlan.Status, []
        note = [("note", "Notes", "textarea", None)]
        if p.status in (S.SUBMITTED, S.UNDER_REVIEW) and u.has_cap("plans.review"):
            acts.append({"title": "Technical review (stage 1)", "fields": note,
                         "buttons": ([("start_review", "Start review", "outline-primary")] if p.status == S.SUBMITTED else []) +
                         [("recommend", "Recommend for approval", "success"), ("return", "Return for corrections", "outline-danger")]})
        if p.status == S.RECOMMENDED and u.has_cap("plans.approve") and p.reviewed_by_id != u.pk:
            acts.append({"title": "District Engineer decision (stage 2)", "fields": note,
                         "buttons": [("approve", "Approve plan", "success"), ("reject", "Reject", "outline-danger")]})
        if p.status in (S.APPROVED, S.CONSTRUCTION) and u.has_cap("plans.review"):
            acts.append({"title": "Site inspections (stage 3)", "fields": [("note", "Inspection stage & findings (e.g. foundations OK)", "textarea", None)],
                         "buttons": [("inspect", "Record inspection", "primary"), ("complete", "Issue completion certificate", "success")]})
        return acts


@staff_required
@require_POST
def plan_action(request, pk):
    plan = get_object_or_404(BuildingPlan, pk=pk)
    run_action(request, services.plan_action, plan, request.POST.get("action"), request.POST.get("note", ""), success="Plan updated.")
    return redirect("departments:plan", pk=pk)


# ------------------------------------------------------------------ assets
class AssetList(GenericListView):
    model = Asset
    required_caps = ("assets.view",)
    title = "Asset & infrastructure register (vehicles, plant, boreholes, ablutions, lights, roads)"
    columns = [("Asset no.", "asset_number"), ("Name", "name"), ("Category", "category"), ("Department", "department"), ("Location", "location"),
               ("Ward", "ward"), ("Cost", "cost"), ("Book value", "book_value"), ("Condition", "condition"), ("Status", "status")]
    search_fields = ["asset_number", "name", "serial_number", "location"]
    filter_field = "category"
    detail_url_name = "departments:asset"
    create_url_name = "departments:asset_new"
    create_caps = ("assets.manage",)

    def scope(self, qs):
        u = self.request.user
        if self.request.GET.get("broken"):
            qs = qs.filter(condition__in=["POOR", "BROKEN"])
        if u.sees_all_departments() or u.has_cap("assets.manage", "finance.view_all"):
            return qs
        return qs.filter(department=u.department)


class AssetCreate(GenericCreateView):
    model = Asset
    form_class = forms.AssetForm
    required_caps = ("assets.manage",)
    detail_url_name = "departments:asset"


class AssetUpdate(GenericUpdateView):
    model = Asset
    form_class = forms.AssetForm
    required_caps = ("assets.manage",)
    detail_url_name = "departments:asset"


class AssetDetail(ActionDetail):
    model = Asset
    required_caps = ("assets.view",)
    action_url_name = "departments:asset_action"
    edit_url_name = "departments:asset_edit"
    edit_caps = ("assets.manage",)
    fields = [("Category", "category"), ("Department", "department"), ("Serial / reg.", "serial_number"), ("Location", "location"),
              ("Ward", "ward"), ("Acquired", "acquisition_date"), ("Cost", "cost"), ("Book value", "book_value"),
              ("Useful life (years)", "useful_life_years"), ("Custodian", "custodian"), ("Condition", "condition"), ("Notes", "notes")]

    def actions(self, a):
        if not self.request.user.has_cap("assets.manage", "assets.condition"):
            return []
        return [{"title": "Condition report / maintenance", "fields": [
            ("condition", "Condition now", "select", Asset.Condition.choices), ("work_done", "Work done / observation", "textarea", None),
            ("cost", "Cost (USD)", "number", None), ("performed_by", "Done by", "text", None)],
            "buttons": [("report", "Save", "primary")]}]

    def sections(self, a):
        return [{"title": "Maintenance & condition history", "rows": [(f"{m.date} – {m.get_condition_after_display()}", f"{m.work_done} (${m.cost}, {m.performed_by})")
                                                                       for m in a.maintenance.alive()]}]


@staff_required
@require_POST
def asset_action(request, pk):
    a = get_object_or_404(Asset, pk=pk)
    run_action(request, services.report_asset_condition, a, condition=request.POST.get("condition"), note=request.POST.get("work_done", ""),
               work_done=request.POST.get("work_done", ""), cost=request.POST.get("cost") or 0, performed_by=request.POST.get("performed_by", ""),
               success="Asset updated.")
    return redirect("departments:asset", pk=pk)


# ------------------------------------------------------------------- risks
class RiskList(GenericListView):
    model = Risk
    required_caps = ("risks.view", "risks.manage")
    title = "Risk register (Internal Audit – risk management)"
    columns = [("Ref.", "reference"), ("Department", "department"), ("Risk", "title"), ("Category", "category"), ("L", "likelihood"),
               ("I", "impact"), ("Score", "score"), ("Rating", lambda r: r.rating), ("Owner", "owner"), ("Review", "review_date"), ("Status", "status")]
    search_fields = ["reference", "title", "description"]
    detail_url_name = "departments:risk_edit"
    create_url_name = "departments:risk_new"
    create_caps = ("risks.manage",)

    def scope(self, qs):
        return qs if self.request.user.has_cap("risks.manage") else _dept_scope(self, qs)

    def row_url(self, obj):
        return reverse("departments:risk_edit", args=[obj.pk]) if self.request.user.has_cap("risks.manage") else None


class RiskCreate(GenericCreateView):
    model = Risk
    form_class = forms.RiskForm
    required_caps = ("risks.manage",)
    success_url = "/staff/audit/risks/"


class RiskUpdate(GenericUpdateView):
    model = Risk
    form_class = forms.RiskForm
    required_caps = ("risks.manage",)
    success_url = "/staff/audit/risks/"


# ------------------------------------------------- meetings & resolutions
class MeetingList(GenericListView):
    model = CouncilMeeting
    required_caps = ("meetings.view",)
    title = "Council & committee meetings (Council Secretariat)"
    columns = [("Ref.", "reference"), ("Date", "date"), ("Type", "meeting_type"), ("Title", "title"), ("Venue", "venue"),
               ("Resolutions", lambda m: m.resolutions.alive().count()), ("Status", "status")]
    search_fields = ["reference", "title", "agenda", "minutes"]
    detail_url_name = "departments:meeting"
    create_url_name = "departments:meeting_new"
    create_caps = ("meetings.manage",)
    extra_buttons = [("Resolutions tracker", "departments:resolutions", ())]


class MeetingCreate(GenericCreateView):
    model = CouncilMeeting
    form_class = forms.MeetingForm
    required_caps = ("meetings.manage",)
    detail_url_name = "departments:meeting"


class MeetingUpdate(GenericUpdateView):
    model = CouncilMeeting
    form_class = forms.MeetingForm
    required_caps = ("meetings.manage",)
    detail_url_name = "departments:meeting"


class MeetingDetail(ActionDetail):
    model = CouncilMeeting
    required_caps = ("meetings.view",)
    template_name = "departments/meeting_detail.html"
    edit_url_name = "departments:meeting_edit"
    edit_caps = ("meetings.manage",)
    fields = [("Type", "meeting_type"), ("Date", "date"), ("Venue", "venue"), ("Agenda", "agenda"), ("Minutes", "minutes")]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["resolutions"] = self.object.resolutions.alive().select_related("responsible")
        ctx["res_form"] = forms.ResolutionForm()
        return ctx


@cap_required("meetings.manage")
@require_POST
def resolution_add(request, pk):
    meeting = get_object_or_404(CouncilMeeting, pk=pk)
    form = forms.ResolutionForm(request.POST)
    if form.is_valid():
        r = form.save(commit=False)
        r.meeting, r.created_by = meeting, request.user
        r.save()
        from finance.services import notify

        notify([r.responsible] + services.heads_of(r.department), f"Council resolution {r.number} assigned to your department", r.text[:200],
               "/staff/resolutions/")
        messages.success(request, f"Resolution {r.number} recorded.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect("departments:meeting", pk=pk)


class ResolutionList(GenericListView):
    model = Resolution
    required_caps = ("meetings.view",)
    title = "Council resolutions – implementation tracker"
    columns = [("No.", "number"), ("Meeting", "meeting.title"), ("Resolution", lambda r: r.text[:90]), ("Department", "department"),
               ("Responsible", "responsible"), ("Due", "due_date"), ("Status", "status")]
    search_fields = ["number", "text"]
    detail_url_name = "departments:resolution"

    def scope(self, qs):
        u = self.request.user
        if u.sees_all_departments() or u.has_cap("meetings.manage"):
            return qs
        return qs.filter(Q(department=u.department) | Q(responsible=u))


class ResolutionDetail(ActionDetail):
    model = Resolution
    required_caps = ("meetings.view",)
    action_url_name = "departments:resolution_action"
    fields = [("Meeting", "meeting"), ("Resolution", "text"), ("Department", "department"), ("Responsible", "responsible"), ("Due", "due_date"),
              ("Progress", "progress_note")]

    def actions(self, r):
        u = self.request.user
        if r.responsible_id == u.pk or u.has_cap("meetings.manage") or services.is_head_of(u, r.department):
            return [{"title": "Report implementation progress", "fields": [("status", "Status", "select", Resolution.Status.choices),
                                                                          ("note", "Progress note", "textarea", None)],
                     "buttons": [("update", "Save", "primary")]}]
        return []


@staff_required
@require_POST
def resolution_action(request, pk):
    r = get_object_or_404(Resolution, pk=pk)
    run_action(request, services.update_resolution, r, status=request.POST.get("status"), note=request.POST.get("note", ""), success="Updated.")
    return redirect("departments:resolution", pk=pk)


# -------------------------------------------------------------- ICT desk
class TicketList(GenericListView):
    model = ICTTicket
    required_caps = ("ict.raise",)
    title = "ICT helpdesk"
    columns = [("Ref.", "reference"), ("Raised", "created_at"), ("By", "raised_by"), ("Department", "department"), ("Category", "category"),
               ("Subject", "subject"), ("Priority", "priority"), ("Assigned", "assigned_to"), ("Status", "status")]
    search_fields = ["reference", "subject", "description"]
    detail_url_name = "departments:ticket"
    create_url_name = "departments:ticket_new"

    def scope(self, qs):
        u = self.request.user
        return qs if u.has_cap("ict.manage") else qs.filter(Q(raised_by=u) | (Q(department=u.department) if u.is_head else Q(pk=None)))


@cap_required("ict.raise")
def ticket_new(request):
    form = forms.TicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        t = run_action(request, services.raise_ticket, success="Ticket raised – ICT notified.", **form.cleaned_data)
        if t:
            return redirect("departments:ticket", pk=t.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Raise ICT support ticket"})


class TicketDetail(ActionDetail):
    model = ICTTicket
    required_caps = ("ict.raise",)
    action_url_name = "departments:ticket_action"
    fields = [("Raised by", "raised_by"), ("Department", "department"), ("Category", "category"), ("Priority", "priority"),
              ("Description", "description"), ("Asset", "asset"), ("Assigned to", "assigned_to"), ("Resolution", "resolution")]

    def scope(self, qs):
        return TicketList.scope(self, qs)

    def actions(self, t):
        u, acts = self.request.user, []
        if u.has_cap("ict.manage") and t.status in ("OPEN", "IN_PROGRESS"):
            acts.append({"title": "ICT action", "fields": [("note", "Resolution / notes", "textarea", None)],
                         "buttons": [("take", "Take ticket", "outline-primary"), ("resolve", "Resolved", "success")]})
        if t.status == "RESOLVED" and (t.raised_by_id == u.pk or u.has_cap("ict.manage")):
            acts.append({"title": "Confirm", "fields": [], "buttons": [("close", "Confirm fixed – close", "success")]})
        return acts


@staff_required
@require_POST
def ticket_action(request, pk):
    t = get_object_or_404(ICTTicket, pk=pk)
    run_action(request, services.ticket_action, t, request.POST.get("action"), request.POST.get("note", ""), success="Ticket updated.")
    return redirect("departments:ticket", pk=pk)


# --------------------------------------------------------------- policies
class PolicyList(GenericListView):
    model = Policy
    required_caps = ("policies.view",)
    title = "Policies, by-laws & procedures"
    columns = [("Title", "title"), ("Kind", "kind"), ("Department", "department"), ("Version", "version"), ("Adopted", "adopted_on"),
               ("Review by", "review_date"), ("Status", "status")]
    search_fields = ["title", "summary"]
    detail_url_name = "departments:policy"
    create_url_name = "departments:policy_new"
    create_caps = ("policies.manage",)


class PolicyCreate(GenericCreateView):
    model = Policy
    form_class = forms.PolicyForm
    required_caps = ("policies.manage",)
    detail_url_name = "departments:policy"


class PolicyUpdate(GenericUpdateView):
    model = Policy
    form_class = forms.PolicyForm
    required_caps = ("policies.manage",)
    detail_url_name = "departments:policy"


class PolicyDetail(GenericDetailView):
    model = Policy
    required_caps = ("policies.view",)
    edit_url_name = "departments:policy_edit"
    edit_caps = ("policies.manage",)
    fields = [("Kind", "kind"), ("Department", "department"), ("Version", "version"), ("Summary", "summary"), ("Adopted", "adopted_on"),
              ("Review by", "review_date"), ("Document", lambda p: p.document.url if p.document else "—")]


# ===================================================== department overview
@cap_required("dept.overview", "dept.overview_all")
def department_overview(request):
    """Everything happening in one department – for its head (and the CEO / auditors for any department)."""
    from departments.models import AuditFinding, LeaveRequest
    from finance.models import BudgetLine, PaymentVoucher, Requisition
    from workflow.models import Complaint, Correspondence, ServiceRequest, Task

    user = request.user
    dept = user.department
    if (user.sees_all_departments() or user.has_cap("dept.overview_all")) and request.GET.get("dept") in Department.values:
        dept = request.GET["dept"]
    if dept == Department.EXECUTIVE and not request.GET.get("dept"):
        dept = Department.EXECUTIVE
    today = timezone.localdate()
    now = timezone.now()
    staff = list(User.objects.filter(department=dept, user_type=User.UserType.STAFF, is_active=True))
    on_leave = set(LeaveRequest.objects.alive().filter(status="APPROVED", start_date__lte=today, end_date__gte=today,
                                                        employee__department=dept).values_list("employee_id", flat=True))
    open_tasks = Task.objects.alive().filter(department=dept, status__in=["OPEN", "IN_PROGRESS"])
    for s in staff:
        s.open_tasks = open_tasks.filter(assigned_to=s).count()
        s.overdue_tasks = open_tasks.filter(assigned_to=s, due_date__lt=today).count()
        s.on_leave = s.pk in on_leave
    lines = BudgetLine.objects.alive().filter(department=dept, financial_year=today.year)
    budget = [{"line": b, "actual": b.actual(), "committed": b.committed(), "pct": b.utilisation_pct()} for b in lines]
    complaints = Complaint.objects.alive().filter(department=dept).exclude(status__in=["RESOLVED", "CLOSED"])
    requests_ = ServiceRequest.objects.alive().filter(department=dept).exclude(status__in=["RESOLVED", "CLOSED", "REJECTED"])
    ctx = {
        "title": f"Department overview – {Department(dept).label}", "dept": dept, "dept_label": Department(dept).label,
        "departments": Department.choices, "staff": staff, "open_tasks": open_tasks.select_related("assigned_to")[:15],
        "reqs_waiting": Requisition.objects.alive().filter(department=dept, status="SUBMITTED"),
        "reqs_recent": Requisition.objects.alive().filter(department=dept).exclude(status="DRAFT")[:10],
        "vouchers": PaymentVoucher.objects.alive().filter(department=dept).exclude(status__in=["PAID", "REJECTED", "CANCELLED"])[:10],
        "leave_pending": LeaveRequest.objects.alive().filter(status="PENDING", employee__department=dept),
        "budget": budget, "complaints": complaints.count(), "complaints_unacked": complaints.filter(acknowledged_at__isnull=True).count(),
        "requests": requests_.count(), "requests_overdue": requests_.filter(due_at__lt=now).count(),
        "correspondence_overdue": Correspondence.objects.alive().filter(department=dept, status__in=["RECEIVED", "ASSIGNED"], response_due__lt=now).count(),
        "findings": AuditFinding.objects.alive().filter(department=dept).exclude(status="CLOSED").count(),
        "risks_high": sum(1 for r in Risk.objects.alive().filter(department=dept).exclude(status="CLOSED") if r.rating in ("HIGH", "CRITICAL")),
        "resolutions": Resolution.objects.alive().filter(department=dept).exclude(status__in=["DONE", "RESCINDED"]).count(),
        "assets_broken": Asset.objects.alive().filter(department=dept, condition__in=["POOR", "BROKEN"]).count(),
        "activities_to_verify": CommunityActivity.objects.alive().filter(department=dept, status="DONE"),
        "can_switch": user.sees_all_departments() or user.has_cap("dept.overview_all"),
    }
    if dept == Department.SOCIAL_SERVICES:
        ctx["special"] = [("Open incidents", Incident.objects.alive().exclude(status="CLOSED").count(), "departments:incidents"),
                          ("Stand applications waiting", StandApplication.objects.alive().filter(status="RECEIVED").count(), "departments:stands"),
                          ("Activities this month", CommunityActivity.objects.alive().filter(date__year=today.year, date__month=today.month).count(), "departments:activities"),
                          ("Boreholes / ablutions not working", Asset.objects.alive().filter(category__in=["BOREHOLE", "ABLUTION", "WATER"], condition="BROKEN").count(), "departments:assets")]
    elif dept == Department.TECHNICAL_SERVICES:
        ctx["special"] = [("Projects ongoing", Project.objects.alive().filter(status="ONGOING").count(), "departments:projects"),
                          ("Plans awaiting decision", BuildingPlan.objects.alive().filter(status__in=["SUBMITTED", "REVIEW", "RECOMMEND"]).count(), "departments:plans"),
                          ("Plans past 30 working days", BuildingPlan.objects.alive().filter(status__in=["SUBMITTED", "REVIEW", "RECOMMEND"], due_at__lt=now).count(), "departments:plans"),
                          ("Street lights / roads faulty", Asset.objects.alive().filter(category__in=["LIGHT", "ROAD", "BRIDGE"], condition__in=["POOR", "BROKEN"]).count(), "departments:assets")]
    elif dept == Department.FINANCE:
        from finance.models import AccountClaim, CashUp, Receipt

        ctx["special"] = [("Collected today (USD)", Receipt.objects.alive().filter(status__in=Receipt.COUNTABLE, created_at__date=today).aggregate(t=Sum("base_amount"))["t"] or 0, "finance:receipts"),
                          ("Cash-ups to verify", CashUp.objects.alive().filter(status="SUBMITTED").count(), "finance:cashups"),
                          ("Stand claims to verify", AccountClaim.objects.alive().filter(status="PENDING").count(), "finance:claims"),
                          ("Vouchers in approval", PaymentVoucher.objects.alive().filter(status__in=["PREPARED", "CHECKED", "APPROVED"]).count(), "finance:vouchers")]
    elif dept == Department.ADMINISTRATION:
        ctx["special"] = [("ICT tickets open", ICTTicket.objects.alive().filter(status__in=["OPEN", "IN_PROGRESS"]).count(), "departments:tickets"),
                          ("Resolutions not implemented", Resolution.objects.alive().exclude(status__in=["DONE", "RESCINDED"]).count(), "departments:resolutions"),
                          ("Meetings scheduled", CouncilMeeting.objects.alive().filter(status="SCHEDULED").count(), "departments:meetings"),
                          ("Policies due for review", Policy.objects.alive().filter(review_date__lte=today).exclude(status="RETIRED").count(), "departments:policies")]
    elif dept == Department.INTERNAL_AUDIT:
        ctx["special"] = [("Open findings (all depts)", AuditFinding.objects.alive().exclude(status="CLOSED").count(), "departments:findings"),
                          ("Overdue management actions", AuditFinding.objects.alive().exclude(status="CLOSED").filter(implementation_date__lt=today).count(), "departments:findings"),
                          ("High / critical risks", sum(1 for r in Risk.objects.alive().exclude(status="CLOSED") if r.rating in ("HIGH", "CRITICAL")), "departments:risks"),
                          ("Risks due for review", Risk.objects.alive().filter(review_date__lte=today).exclude(status="CLOSED").count(), "departments:risks")]
    return render(request, "departments/overview.html", ctx)
