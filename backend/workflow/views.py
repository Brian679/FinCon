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


# ============================================================ funds requests
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import PermissionDenied  # noqa: E402
from django.db import transaction  # noqa: E402

from . import funds as fr  # noqa: E402
from . import memos as mm  # noqa: E402
from .models import FundsRequest, Memo  # noqa: E402

User = get_user_model()


class FundsList(GenericListView):
    model = FundsRequest
    required_caps = ("funds.request",)
    title = "Requests for funds & purchases"
    columns = [("Ref.", "reference"), ("Date", "created_at"), ("Type", "request_type"), ("What for", "title"), ("Department", "department"),
               ("Requested by", "requested_by"), ("Amount", lambda r: f"{r.currency} {r.total:,.2f}"),
               ("Where is it now", lambda r: fr.where_now(r) if r.is_open or r.status == "RETURNED" else "—"),
               ("Days", lambda r: r.days_waiting if r.is_open else "—"), ("Status", "status")]
    search_fields = ["reference", "title", "purpose", "requested_by__first_name", "requested_by__last_name"]
    detail_url_name = "workflow:fund"
    create_url_name = "workflow:fund_new"

    def boxes(self):
        u = self.request.user
        b = [("mine", "My requests")]
        if u.is_head or u.has_cap("funds.admin_approve", "funds.treasurer_approve", "funds.ceo_approve"):
            b.append(("awaiting", f"Waiting for my approval ({len(fr.awaiting(u))})"))
        if u.is_head:
            b.append(("department", "My department"))
        if u.has_cap("funds.view_all", "funds.admin_approve") or u.sees_all_departments():
            b.append(("all", "All departments"))
        return b

    def box(self):
        keys = [k for k, _l in self.boxes()]
        want = self.request.GET.get("box")
        if want in keys:
            return want
        return "awaiting" if "awaiting" in keys and fr.awaiting(self.request.user) else "mine"

    def scope(self, qs):
        u = self.request.user
        qs = fr.funds_scope(u, qs.select_related("requested_by", "voucher"))
        box = self.box()
        if box == "mine":
            return qs.filter(requested_by=u)
        if box == "awaiting":
            return qs.filter(pk__in=[r.pk for r in fr.awaiting(u)])
        if box == "department":
            return qs.filter(department=u.department)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tabs"] = [(k, lbl, k == self.box()) for k, lbl in self.boxes()]
        ctx["box"] = self.box()
        ctx["extra_qs"] = f"&box={ctx['box']}"
        ctx["route_help"] = True
        return ctx

    def get_template_names(self):
        return ["workflow/funds_list.html"]


@staff_required
def fund_form(request, pk=None):
    req = None
    if pk:
        req = get_object_or_404(FundsRequest, pk=pk, requested_by=request.user, status__in=[FundsRequest.Status.DRAFT, FundsRequest.Status.RETURNED])
    form = forms.FundsRequestForm(request.POST or None, request.FILES or None, instance=req, user=request.user)
    formset = forms.LineFormSet(request.POST or None, instance=req or FundsRequest())
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            if obj._state.adding:
                obj.requested_by = request.user
                obj.department = request.user.department
                obj.created_by = request.user
            obj.save()
            formset.instance = obj
            formset.save()
            obj.recalc_total()
        if "submit" in request.POST:
            run_action(request, fr.submit, obj, success="Request submitted – you will be notified at every stage.")
        else:
            messages.success(request, "Saved as draft.")
        return redirect("workflow:fund", pk=obj.pk)
    return render(request, "workflow/fund_form.html", {"form": form, "formset": formset,
                                                       "title": "Edit request" if req else "New request for funds / purchase"})


class FundsDetail(GenericDetailView):
    model = FundsRequest
    required_caps = ("funds.request",)
    template_name = "workflow/fund_detail.html"
    fields = [("Type", "request_type"), ("What for", "title"), ("Purpose", "purpose"), ("Department", "department"),
              ("Requested by", "requested_by"), ("Date", "created_at"), ("Needed by", "needed_by"),
              ("Destination", "destination"), ("Departure", "depart_date"), ("Return", "return_date"), ("Officers travelling", "travellers"),
              ("Amount", lambda r: f"{r.currency} {r.total:,.2f}"), ("Money paid out", "requires_payment"),
              ("Pay to", lambda r: r.payee_name or r.requested_by.get_full_name()), ("Payment method", "payment_method"),
              ("Bank / mobile money", "payment_details"), ("Budget vote", "budget_line"), ("Payment voucher", "voucher"),
              ("Note from approver", "decision_note")]

    def scope(self, qs):
        return fr.funds_scope(self.request.user, qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        r, u = self.object, self.request.user
        ctx["field_rows"] = [(lbl, val) for lbl, val in ctx["field_rows"] if val not in ("—", "")]
        ctx["route"] = fr.route(r)
        ctx["where"] = fr.where_now(r)
        ctx["can_decide"] = fr.can_decide(u, r)
        ctx["stage"] = fr.STAGE_LABEL.get(r.status)
        ctx["is_owner"] = r.requested_by_id == u.pk
        ctx["can_edit"] = ctx["is_owner"] and r.status in (FundsRequest.Status.DRAFT, FundsRequest.Status.RETURNED)
        ctx["can_remind"] = r.is_open and not ctx["can_decide"] and (ctx["is_owner"] or (u.is_head and u.department == r.department))
        ctx["can_cancel"] = ctx["is_owner"] and r.status in ("DRAFT", "RETURNED") + FundsRequest.PENDING
        ctx["can_pay"] = r.status == FundsRequest.Status.PENDING_PAYMENT and u.has_cap("voucher.prepare")
        ctx["methods"] = FundsRequest.PaymentMethod.choices
        ctx["approvals"] = []  # shown in the tracker instead
        ctx["log"] = fr.history(r)
        return ctx


@staff_required
@require_POST
def fund_action(request, pk):
    req = get_object_or_404(FundsRequest.objects.alive(), pk=pk)
    if not fr.can_view(request.user, req):
        raise PermissionDenied("You cannot see this request.")
    a = request.POST.get("action")
    note = request.POST.get("comment", "").strip()
    if a == "submit":
        run_action(request, fr.submit, req, success="Submitted – you will be notified at every stage.")
    elif a in ("approve", "reject", "return"):
        run_action(request, fr.decide, req, a, note, success={"approve": "Approved – sent to the next stage.", "reject": "Rejected.",
                                                              "return": "Returned to the requester."}[a])
    elif a == "remind":
        run_action(request, fr.remind, req, note, success="Reminder sent.")
    elif a == "cancel":
        run_action(request, fr.cancel, req, note, success="Request cancelled.")
    elif a == "pay":
        v = run_action(request, fr.prepare_payment, req, method=request.POST.get("method") or None,
                       success="Payment voucher prepared – it now goes through payment approval.")
        if v:
            return redirect("finance:voucher", pk=v.pk)
    return redirect("workflow:fund", pk=pk)


# ===================================================================== memos
class MemoList(GenericListView):
    model = Memo
    required_caps = ("memos.send",)
    title = "Memos between departments"
    columns = [("Ref.", "reference"), ("Date", "created_at"), ("Type", "kind"), ("From", lambda m: f"{m.sender.get_full_name()} ({m.get_from_department_display()})"),
               ("To", lambda m: f"{m.to_user.get_full_name() + ' – ' if m.to_user_id else 'Head of '}{m.get_to_department_display()}"),
               ("Subject", "subject"), ("Priority", "priority"), ("Status", "status")]
    search_fields = ["reference", "subject", "body"]
    detail_url_name = "workflow:memo"
    create_url_name = "workflow:memo_new"

    def scope(self, qs):
        u = self.request.user
        qs = mm.memo_scope(u, qs.select_related("sender", "to_user"))
        box = self.request.GET.get("box", "inbox")
        if box == "sent":
            return qs.filter(sender=u)
        if box == "all":
            return qs
        inbox = Q(to_user=u) | Q(task__assigned_to=u)
        if u.is_head:
            inbox |= Q(to_department=u.department)
        return qs.filter(inbox).exclude(sender=u)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        box = self.request.GET.get("box", "inbox")
        ctx["tabs"] = [("inbox", "Received", box == "inbox"), ("sent", "Sent", box == "sent"), ("all", "All", box == "all")]
        ctx["box"] = box
        ctx["extra_qs"] = f"&box={box}"
        return ctx

    def get_template_names(self):
        return ["workflow/funds_list.html"]


@cap_required("memos.send")
def memo_new(request):
    initial = {k: request.GET[k] for k in ("to_department", "subject", "kind") if k in request.GET}
    form = forms.MemoForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        memo = run_action(request, mm.send, kind=d["kind"], to_department=d["to_department"], to_user=d["to_user"], subject=d["subject"],
                          body=d["body"], priority=d["priority"], success="Memo sent.")
        if memo:
            return redirect("workflow:memo", pk=memo.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Send a memo / request to a department"})


@staff_required
def memo_detail(request, pk):
    memo = get_object_or_404(Memo.objects.alive().select_related("sender", "to_user", "task"), pk=pk)
    if not mm.is_participant(request.user, memo):
        raise PermissionDenied("You are not part of this memo.")
    u = request.user
    if request.method == "POST":
        a = request.POST.get("action")
        if a == "task":
            assignee = User.objects.filter(pk=request.POST.get("assigned_to")).first()
            if assignee:
                t = run_action(request, mm.to_task, memo, assigned_to=assignee, due_date=request.POST.get("due_date") or None,
                               success="Assigned as a task.")
                if t:
                    return redirect("workflow:memo", pk=pk)
            else:
                messages.error(request, "Choose the officer.")
        else:
            run_action(request, mm.reply, memo, request.POST.get("body", ""), close=(a == "close"), success="Saved.")
        return redirect("workflow:memo", pk=pk)
    mm.mark_read(u, memo)
    officers = User.objects.filter(department=memo.to_department, is_active=True, user_type=User.UserType.STAFF) \
        if (u.is_head and u.department == memo.to_department and not memo.task_id) else []
    return render(request, "workflow/memo_detail.html", {
        "memo": memo, "title": f"{memo.reference} – {memo.subject}", "replies": memo.replies.alive().select_related("author"),
        "officers": officers, "can_close": memo.status != Memo.Status.CLOSED and (memo.sender_id == u.pk or mm.is_recipient(u, memo)),
    })
