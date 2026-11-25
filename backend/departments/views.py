from django.contrib import messages
from django.contrib.auth import get_user_model
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
