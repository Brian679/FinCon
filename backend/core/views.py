from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.decorators import cap_required, staff_required

from .models import AuditLog, Department, Notification, ServiceStandard


def landing(request):
    if request.user.is_authenticated:
        return redirect("accounts:home")
    return render(request, "core/landing.html", {"standards": ServiceStandard.objects.all()})


def charter(request):
    return render(request, "core/charter.html", {"standards": ServiceStandard.objects.all()})


def offline(request):
    return render(request, "core/offline.html")


def service_worker(request):
    return HttpResponse(render_to_string("core/sw.js"), content_type="application/javascript")


def manifest(request):
    return JsonResponse({
        "name": "Chipinge RDC Council System",
        "short_name": "Chipinge RDC",
        "start_url": "/staff/" if getattr(request, "site_kind", "") == "staff" else "/portal/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#1f7a3a",
        "icons": [{"src": "/static/img/logo.svg", "sizes": "any", "type": "image/svg+xml"}],
    })


def pending_approvals(user):
    """Documents waiting for this user's decision."""
    from finance import services
    from finance.models import Licence, PaymentVoucher, Receipt, Requisition

    items = []
    open_reqs = Requisition.objects.alive().exclude(status__in=[Requisition.Status.DRAFT, Requisition.Status.ORDERED,
                                                                 Requisition.Status.REJECTED, Requisition.Status.CANCELLED])
    for r in open_reqs.select_related("requested_by")[:200]:
        stage = services.requisition_next_action(user, r)
        if stage and r.requested_by_id != user.pk:
            items.append({"kind": "Requisition", "ref": r.number, "text": f"{r.get_department_display()} – ${r.total}", "stage": stage, "url": f"/staff/finance/requisitions/{r.pk}/"})
    for v in PaymentVoucher.objects.alive().filter(status__in=[PaymentVoucher.Status.PREPARED, PaymentVoucher.Status.CHECKED, PaymentVoucher.Status.APPROVED])[:200]:
        stage = services.voucher_next_action(user, v)
        if stage and v.prepared_by_id != user.pk:
            items.append({"kind": "Payment voucher", "ref": v.number, "text": f"{v.payee_name} – {v.currency} {v.amount}", "stage": stage, "url": f"/staff/finance/vouchers/{v.pk}/"})
    from workflow import funds as fr

    for r in fr.awaiting(user):
        items.append({"kind": "Request for funds", "ref": r.reference, "text": f"{r.get_department_display()} – {r.title} – {r.currency} {r.total:,.2f}",
                      "stage": fr.STAGE_LABEL.get(r.status, ""), "url": f"/staff/funds/{r.pk}/"})
    if user.has_cap("voucher.prepare"):
        from workflow.models import FundsRequest

        for r in FundsRequest.objects.alive().filter(status=FundsRequest.Status.PENDING_PAYMENT)[:50]:
            items.append({"kind": "Request for funds", "ref": r.reference, "text": f"{r.title} – {r.currency} {r.total:,.2f}",
                          "stage": "Prepare payment voucher", "url": f"/staff/funds/{r.pk}/"})
    if user.has_cap("receipt.void_approve"):
        for r in Receipt.objects.alive().filter(status=Receipt.Status.VOID_REQUESTED).exclude(void_requested_by=user)[:50]:
            items.append({"kind": "Receipt void", "ref": r.number, "text": r.void_reason, "stage": "Approve void", "url": f"/staff/finance/receipts/{r.pk}/"})
    if user.has_cap("licence.inspect"):
        for lic in Licence.objects.alive().filter(status=Licence.Status.INSPECTION)[:50]:
            items.append({"kind": "Licence", "ref": lic.number, "text": lic.business_name, "stage": "Inspection", "url": f"/staff/finance/licences/{lic.pk}/"})
    if user.has_cap("licence.approve"):
        for lic in Licence.objects.alive().filter(status__in=[Licence.Status.APPLIED, Licence.Status.INSPECTED])[:50]:
            items.append({"kind": "Licence", "ref": lic.number, "text": lic.business_name, "stage": "Approval", "url": f"/staff/finance/licences/{lic.pk}/"})
    if user.has_cap("leave.approve"):
        from departments.models import LeaveRequest

        qs = LeaveRequest.objects.alive().filter(status=LeaveRequest.Status.PENDING).exclude(employee=user)
        if not user.is_ceo:
            qs = qs.filter(employee__department=user.department)
        for lv in qs[:50]:
            items.append({"kind": "Leave", "ref": str(lv.employee), "text": f"{lv.get_leave_type_display()} {lv.days} day(s)", "stage": "Approval", "url": f"/staff/leave/{lv.pk}/"})
    return items


def finance_kpis():
    from finance.models import Bill, ClientAccount, PaymentVoucher, Receipt

    today = timezone.localdate()
    month_start = today.replace(day=1)
    receipts = Receipt.objects.alive().filter(status__in=Receipt.COUNTABLE)
    return {
        "today": receipts.filter(created_at__date=today).aggregate(t=Sum("base_amount"), n=Count("id")),
        "month": receipts.filter(created_at__date__gte=month_start).aggregate(t=Sum("base_amount"), n=Count("id")),
        "paid_out_month": PaymentVoucher.objects.alive().filter(status=PaymentVoucher.Status.PAID, paid_at__date__gte=month_start).aggregate(t=Sum("base_amount"))["t"] or 0,
        "debtors": ClientAccount.objects.alive().filter(balance__gt=0).aggregate(t=Sum("balance"), n=Count("id")),
        "overdue_bills": Bill.objects.alive().filter(status__in=[Bill.Status.UNPAID, Bill.Status.PART_PAID], due_date__lt=today).count(),
    }


@staff_required
def dashboard(request):
    from departments.models import AuditFinding, Project
    from workflow.models import Complaint, ServiceRequest, Task

    user = request.user
    ctx = {"title": "Dashboard", "approvals": pending_approvals(user)}
    ctx["my_tasks"] = Task.objects.alive().filter(assigned_to=user, status__in=[Task.Status.OPEN, Task.Status.IN_PROGRESS])[:10]
    dept_filter = Q() if user.sees_all_departments() else Q(department=user.department)
    from workflow.services import complaint_scope

    ctx["complaints_open"] = complaint_scope(user, Complaint.objects.alive()).exclude(status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED])
    ctx["complaints_unacked"] = ctx["complaints_open"].filter(acknowledged_at__isnull=True).count()
    ctx["requests_open"] = ServiceRequest.objects.alive().filter(dept_filter).exclude(
        status__in=[ServiceRequest.Status.RESOLVED, ServiceRequest.Status.CLOSED, ServiceRequest.Status.REJECTED])
    ctx["requests_overdue"] = ctx["requests_open"].filter(due_at__lt=timezone.now()).count()
    ctx["complaints_open_count"] = ctx["complaints_open"].count()
    ctx["requests_open_count"] = ctx["requests_open"].count()
    from workflow import funds as fr
    from workflow.models import FundsRequest

    ctx["my_funds"] = [{"obj": r, "where": fr.where_now(r)} for r in FundsRequest.objects.alive().filter(
        requested_by=user, status__in=FundsRequest.OPEN + ("RETURNED",))[:8]]
    if user.has_cap("finance.view_all", "finance.view"):
        from finance.views import finance_dashboard_context

        ctx.update(finance_dashboard_context(user))
    if user.has_cap("projects.view"):
        ctx["projects"] = Project.objects.alive().exclude(status=Project.Status.COMPLETED)[:6]
    if user.has_cap("audit.findings_view", "audit.respond"):
        qs = AuditFinding.objects.alive().exclude(status=AuditFinding.Status.CLOSED)
        if not user.sees_all_departments():
            qs = qs.filter(department=user.department)
        ctx["open_findings"] = qs.count()
    return render(request, "core/dashboard.html", ctx)


@cap_required("reports.executive")
def executive(request):
    """CEO's whole-council view, including Client Charter compliance."""
    from departments.models import AuditFinding, LeaveRequest, Project, StandApplication
    from finance.models import Licence, PaymentVoucher, Requisition
    from workflow.models import Complaint, Correspondence, ServiceRequest, Task

    now = timezone.now()
    since = now - timedelta(days=90)
    complaints = Complaint.objects.alive().filter(created_at__gte=since)
    acked = complaints.filter(acknowledged_at__isnull=False)
    acked_in_time = sum(1 for c in acked if c.acknowledged_at <= c.acknowledge_due)
    requests = ServiceRequest.objects.alive().filter(created_at__gte=since)
    resolved = requests.filter(resolved_at__isnull=False)
    resolved_in_time = sum(1 for r in resolved if r.due_at and r.resolved_at <= r.due_at)
    corr = Correspondence.objects.alive().filter(created_at__gte=since, responded_at__isnull=False)
    corr_in_time = sum(1 for c in corr if c.response_due and c.responded_at <= c.response_due)

    def pct(a, b):
        return round(a * 100 / b) if b else None

    departments = []
    for code, label in Department.choices:
        departments.append({
            "label": label,
            "tasks_open": Task.objects.alive().filter(department=code, status__in=[Task.Status.OPEN, Task.Status.IN_PROGRESS]).count(),
            "tasks_overdue": Task.objects.alive().filter(department=code, status__in=[Task.Status.OPEN, Task.Status.IN_PROGRESS], due_date__lt=timezone.localdate()).count(),
            "complaints_open": Complaint.objects.alive().filter(department=code).exclude(status__in=[Complaint.Status.RESOLVED, Complaint.Status.CLOSED]).count(),
            "requests_open": ServiceRequest.objects.alive().filter(department=code).exclude(status__in=[ServiceRequest.Status.RESOLVED, ServiceRequest.Status.CLOSED, ServiceRequest.Status.REJECTED]).count(),
            "findings_open": AuditFinding.objects.alive().filter(department=code).exclude(status=AuditFinding.Status.CLOSED).count(),
        })
    ctx = {
        "title": "Executive overview",
        "fin": finance_kpis(),
        "approvals": pending_approvals(request.user),
        "charter": [
            ("Complaints acknowledged within 48 hours", pct(acked_in_time, complaints.count()), complaints.count()),
            ("Service requests resolved on time", pct(resolved_in_time, resolved.count()), resolved.count()),
            ("Correspondence answered within 7 working days", pct(corr_in_time, corr.count()), corr.count()),
        ],
        "departments": departments,
        "projects": Project.objects.alive().exclude(status=Project.Status.COMPLETED)[:10],
        "big_vouchers": PaymentVoucher.objects.alive().filter(status=PaymentVoucher.Status.APPROVED)[:10],
        "big_reqs": Requisition.objects.alive().filter(status=Requisition.Status.APPROVED)[:10],
        "licences_pending": Licence.objects.alive().filter(status__in=[Licence.Status.APPLIED, Licence.Status.INSPECTION, Licence.Status.INSPECTED]).count(),
        "stands_waiting": StandApplication.objects.alive().filter(status=StandApplication.Status.RECEIVED).count(),
        "staff_on_leave": LeaveRequest.objects.alive().filter(status=LeaveRequest.Status.APPROVED, start_date__lte=timezone.localdate(), end_date__gte=timezone.localdate()).count(),
    }
    return render(request, "core/executive.html", ctx)


@login_required
def notifications(request):
    qs = request.user.notifications.alive().order_by("-created_at")
    if request.method == "POST":
        qs.filter(is_read=False).update(is_read=True, updated_at=timezone.now())
        return redirect(request.path)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "core/notifications.html", {"title": "Notifications", "page": page})


@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    n.is_read = True
    n.save(update_fields=["is_read", "updated_at"])
    return redirect(n.link or "core:notifications")


@cap_required("audit.view_trail")
def audit_trail(request):
    user = request.user
    qs = AuditLog.objects.select_related("user")
    if not user.has_cap("audit.view_all"):
        # Heads such as the Treasurer see their own department's trail.
        cond = Q(department=user.department)
        if user.department == Department.FINANCE:
            cond |= Q(model__startswith="finance.")
        qs = qs.filter(cond)
    f = request.GET
    if f.get("q"):
        qs = qs.filter(Q(object_repr__icontains=f["q"]) | Q(message__icontains=f["q"]) | Q(username__icontains=f["q"]) | Q(object_id=f["q"]))
    if f.get("action"):
        qs = qs.filter(action=f["action"])
    if f.get("model"):
        qs = qs.filter(model=f["model"])
    if f.get("user"):
        qs = qs.filter(username=f["user"])
    if f.get("from"):
        qs = qs.filter(timestamp__date__gte=f["from"])
    if f.get("to"):
        qs = qs.filter(timestamp__date__lte=f["to"])
    chain = None
    if f.get("verify"):
        ok, broken = AuditLog.verify_chain()
        chain = {"ok": ok, "broken": broken}
    page = Paginator(qs, 50).get_page(f.get("page"))
    models = AuditLog.objects.order_by().values_list("model", flat=True).distinct()
    return render(request, "core/audit_trail.html", {
        "title": "Audit trail", "page": page, "actions": AuditLog.Action.choices, "models": sorted(m for m in models if m),
        "chain": chain, "params": f.urlencode(),
    })


def permission_denied(request, exception=None):
    return render(request, "403.html", {"title": "Access denied", "reason": str(exception or "")}, status=403)
