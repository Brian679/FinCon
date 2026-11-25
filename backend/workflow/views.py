from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import cap_required, staff_required
from core.crud import GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView, run_action
from core.models import Department

from . import forms, services
from .models import Complaint, Correspondence, ServiceRequest, Task


# --------------------------------------------------------------------- tasks
class TaskList(GenericListView):
    model = Task
    required_caps = ("tasks.view",)
    title = "Tasks, requests & memos"
    columns = [("Ref.", "reference"), ("Title", "title"), ("Type", "kind"), ("Department", "department"), ("Assigned to", "assigned_to"),
               ("From", "assigned_by"), ("Due", "due_date"), ("Priority", "priority"), ("Status", "status")]
    search_fields = ["reference", "title", "description"]
    detail_url_name = "workflow:task"
    create_url_name = "workflow:task_new"
    create_caps = ("tasks.assign_any", "tasks.assign_department")

    def scope(self, qs):
        u = self.request.user
        if u.has_cap("tasks.assign_any"):
            return qs if self.request.GET.get("all") else qs.filter(Q(assigned_by=u) | Q(assigned_to=u) | Q(department=u.department))
        cond = Q(assigned_to=u) | Q(assigned_by=u)
        if u.is_head:
            cond |= Q(department=u.department)
        return qs.filter(cond).select_related("assigned_to", "assigned_by")


@cap_required("tasks.assign_any", "tasks.assign_department")
def task_new(request):
    form = forms.TaskForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        task = run_action(request, services.create_task, success="Task sent.", **form.cleaned_data)
        if task:
            return redirect("workflow:task", pk=task.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Assign a task / request / memo"})


@staff_required
def task_detail(request, pk):
    task = get_object_or_404(Task.objects.alive(), pk=pk)
    if not services.can_view_task(request.user, task):
        messages.error(request, "This task is not assigned to you.")
        return redirect("workflow:tasks")
    if request.method == "POST":
        run_action(request, services.update_task, task, status=request.POST.get("status") or None,
                   progress=request.POST.get("progress") or None, comment=request.POST.get("comment", "").strip(), success="Task updated.")
        return redirect("workflow:task", pk=pk)
    return render(request, "workflow/task_detail.html", {"task": task, "title": str(task), "statuses": Task.Status.choices,
                                                          "comments": task.comments.alive().select_related("author")})


# ---------------------------------------------------------------- complaints
class ComplaintList(GenericListView):
    model = Complaint
    required_caps = ("complaints.department", "complaints.view_all")
    title = "Complaints, compliments, suggestions & enquiries"
    columns = [("Ref.", "reference"), ("Received", "created_at"), ("Type", "kind"), ("From", "name"), ("Subject", "subject"),
               ("Department", "department"), ("Ack. due", "acknowledge_due"), ("Acknowledged", "acknowledged_at"), ("Status", "status")]
    search_fields = ["reference", "subject", "name", "phone", "details"]
    detail_url_name = "workflow:complaint"
    create_url_name = "workflow:complaint_new"

    def scope(self, qs):
        qs = services.complaint_scope(self.request.user, qs)
        if self.request.GET.get("breached"):
            qs = qs.filter(acknowledged_at__isnull=True, acknowledge_due__lt=timezone.now())
        return qs


class ComplaintCreate(GenericCreateView):
    model = Complaint
    form_class = forms.ComplaintForm
    required_caps = ("complaints.department",)
    title = "Record complaint / feedback"
    detail_url_name = "workflow:complaint"
    offline_capable = True

    def form_valid(self, form):
        c = run_action(self.request, services.log_complaint, success="Recorded. Acknowledge within 48 hours.", **form.cleaned_data)
        if not c:
            return self.form_invalid(form)
        self.object = c
        return redirect(self.get_success_url())


@staff_required
def complaint_detail(request, pk):
    c = get_object_or_404(services.complaint_scope(request.user, Complaint.objects.alive()), pk=pk)
    if request.method == "POST":
        from django.contrib.auth import get_user_model

        assignee = get_user_model().objects.filter(pk=request.POST.get("assignee") or 0).first()
        run_action(request, services.act_on_complaint, c, request.POST.get("action"), note=request.POST.get("note", "").strip(),
                   assignee=assignee, department=request.POST.get("department"), success="Updated.")
        return redirect("workflow:complaint", pk=pk)
    return render(request, "workflow/complaint_detail.html", {
        "c": c, "title": str(c), "officers": forms.staff_queryset(c.department), "departments": Department.choices,
    })


# ---------------------------------------------------------- service requests
class RequestList(GenericListView):
    model = ServiceRequest
    required_caps = ("requests.department", "requests.view_all")
    title = "Service requests & fault reports"
    columns = [("Ref.", "reference"), ("Reported", "created_at"), ("Category", "category"), ("Location", "location"), ("Ward", "ward"),
               ("Department", "department"), ("Due (charter)", "due_at"), ("Assigned", "assigned_to"), ("Priority", "priority"), ("Status", "status")]
    search_fields = ["reference", "location", "description", "reporter_name"]
    detail_url_name = "workflow:request"
    create_url_name = "workflow:request_new"

    def scope(self, qs):
        qs = services.request_scope(self.request.user, qs)
        if self.request.GET.get("overdue"):
            qs = qs.filter(due_at__lt=timezone.now()).exclude(status__in=["RESOLVED", "CLOSED", "REJECTED"])
        return qs


class RequestCreate(GenericCreateView):
    model = ServiceRequest
    form_class = forms.ServiceRequestForm
    required_caps = ("requests.department",)
    title = "Log service request / fault"
    detail_url_name = "workflow:request"
    offline_capable = True

    def form_valid(self, form):
        sr = run_action(self.request, services.report_service_request, success="Service request logged.", **form.cleaned_data)
        if not sr:
            return self.form_invalid(form)
        self.object = sr
        return redirect(self.get_success_url())


@staff_required
def request_detail(request, pk):
    sr = get_object_or_404(services.request_scope(request.user, ServiceRequest.objects.alive()), pk=pk)
    if request.method == "POST":
        from django.contrib.auth import get_user_model

        assignee = get_user_model().objects.filter(pk=request.POST.get("assignee") or 0).first()
        run_action(request, services.act_on_request, sr, request.POST.get("action"), note=request.POST.get("note", "").strip(),
                   assignee=assignee, success="Updated.")
        return redirect("workflow:request", pk=pk)
    return render(request, "workflow/request_detail.html", {"sr": sr, "title": str(sr), "officers": forms.staff_queryset(sr.department)})


# ------------------------------------------------------------ correspondence
class CorrespondenceList(GenericListView):
    model = Correspondence
    required_caps = ("correspondence.manage", "tasks.assign_department", "tasks.assign_any")
    title = "Correspondence register (respond within 7 working days)"
    columns = [("Ref.", "reference"), ("Received", "date_received"), ("From", "sender"), ("Subject", "subject"), ("Department", "department"),
               ("Assigned", "assigned_to"), ("Response due", "response_due"), ("Status", "status")]
    search_fields = ["reference", "sender", "subject", "file_reference"]
    detail_url_name = "workflow:correspondence_edit"
    create_url_name = "workflow:correspondence_new"
    create_caps = ("correspondence.manage",)

    def scope(self, qs):
        u = self.request.user
        if u.has_cap("correspondence.manage") or u.sees_all_departments():
            return qs
        return qs.filter(department=u.department)


class CorrespondenceCreate(GenericCreateView):
    model = Correspondence
    form_class = forms.CorrespondenceForm
    required_caps = ("correspondence.manage",)
    success_url = "/staff/correspondence/"


class CorrespondenceUpdate(GenericUpdateView):
    model = Correspondence
    form_class = forms.CorrespondenceForm
    required_caps = ("correspondence.manage", "tasks.assign_department", "tasks.assign_any")
    success_url = "/staff/correspondence/"

    def form_valid(self, form):
        if form.instance.status == Correspondence.Status.RESPONDED and not form.instance.responded_at:
            form.instance.responded_at = timezone.now()
        return super().form_valid(form)
