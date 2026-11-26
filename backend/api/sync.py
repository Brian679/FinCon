"""Offline-first synchronisation for the mobile apps.

PULL  - the phone keeps one cursor (last ``updated_at`` seen) per entity and
        asks for everything changed since. Only records the user is allowed to
        see are returned, so the local database on the phone is a role-scoped
        replica of the server.
PUSH  - work done offline is queued on the phone as *operations* (each with a
        UUID). The server applies them through the same service layer as the
        website - permissions, segregation of duties, charter deadlines and
        the audit trail all apply - and records the outcome per operation, so
        re-sending is always safe.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import Notification, ServiceStandard
from departments.models import AuditFinding, LeaveRequest, Project, StandApplication
from finance import services as fin
from finance.models import (
    Bill, BudgetLine, ClientAccount, Licence, OnlinePayment, PaymentVoucher, Property, Receipt, Requisition, RevenueHead,
)
from payroll import services as pr
from workflow import services as wf
from workflow.models import Complaint, FundsRequest, Memo, ServiceRequest, Task, TaskComment

from . import serializers as s
from .models import SyncOperation

PAGE = 500


def _accounts_for(user):
    return user.client_accounts.alive()


def _receipt_scope(user):
    qs = Receipt.objects.select_related("revenue_head", "account", "received_by")
    if user.is_client:
        return qs.filter(account__in=_accounts_for(user))
    if user.has_cap("finance.view_all"):
        return qs.filter(created_at__gte=timezone.now() - timedelta(days=120))
    if user.has_cap("receipt.create"):
        return qs.filter(received_by=user)
    return None


def _requisition_scope(user):
    qs = Requisition.objects.prefetch_related("items").select_related("requested_by")
    if user.has_cap("finance.view_all", "procurement.order") or user.is_ceo:
        return qs
    if user.is_head:
        return qs.filter(department=user.department)
    return qs.filter(requested_by=user)


def _task_scope(user):
    qs = Task.objects.select_related("assigned_by", "assigned_to")
    if user.has_cap("tasks.assign_any"):
        return qs
    cond = Q(assigned_to=user) | Q(assigned_by=user)
    if user.is_head:
        cond |= Q(department=user.department)
    return qs.filter(cond)


def _leave_scope(user):
    if user.has_cap("hr.manage") or user.is_ceo:
        return LeaveRequest.objects.all()
    if user.has_cap("leave.approve"):
        return LeaveRequest.objects.filter(employee__department=user.department)
    return LeaveRequest.objects.filter(employee=user)


def _finding_scope(user):
    if user.has_cap("audit.findings_view"):
        return AuditFinding.objects.all()
    if user.has_cap("audit.respond"):
        return AuditFinding.objects.filter(department=user.department)
    return None


def staff_entities(user):
    c = user.has_cap
    fin_accounts = c("accounts.manage", "finance.view_all", "receipt.create")
    return {
        "service_standards": (ServiceStandard.objects.all(), s.ServiceStandardSerializer),
        "revenue_heads": (RevenueHead.objects.all(), s.RevenueHeadSerializer),
        "accounts": (ClientAccount.objects.all(), s.ClientAccountSerializer) if fin_accounts else None,
        "properties": (Property.objects.all(), s.PropertySerializer) if fin_accounts else None,
        "bills": (Bill.objects.filter(Q(status__in=["UNPAID", "PART"]) | Q(updated_at__gte=timezone.now() - timedelta(days=120))), s.BillSerializer) if fin_accounts else None,
        "receipts": (_receipt_scope(user), s.ReceiptSerializer) if _receipt_scope(user) is not None else None,
        "licences": (Licence.objects.select_related("account"), s.LicenceSerializer) if c("licence.view")
        else (Licence.objects.filter(Q(status="INSPECTION") | Q(inspected_by=user)).select_related("account"), s.LicenceSerializer)
        if c("licence.inspect") else None,
        "requisitions": (_requisition_scope(user), s.RequisitionSerializer),
        "vouchers": (PaymentVoucher.objects.select_related("prepared_by", "budget_line"), s.VoucherSerializer)
        if c("voucher.prepare", "voucher.check", "voucher.approve", "voucher.authorise", "finance.view_all") else None,
        "budget_lines": (BudgetLine.objects.filter(financial_year=timezone.localdate().year) if c("budget.view")
                         else BudgetLine.objects.filter(financial_year=timezone.localdate().year, department=user.department), s.BudgetLineSerializer),
        "tasks": (_task_scope(user), s.TaskSerializer),
        "task_comments": (TaskComment.objects.filter(task__in=_task_scope(user)).select_related("author"), s.TaskCommentSerializer),
        "complaints": (wf.complaint_scope(user, Complaint.objects.all()), s.ComplaintSerializer),
        "service_requests": (wf.request_scope(user, ServiceRequest.objects.all()), s.ServiceRequestSerializer),
        "stands": (StandApplication.objects.all(), s.StandApplicationSerializer) if c("stands.view") else None,
        "projects": (Project.objects.all(), s.ProjectSerializer) if c("projects.view") else None,
        "audit_findings": (_finding_scope(user), s.AuditFindingSerializer) if _finding_scope(user) is not None else None,
        "leave": (_leave_scope(user).select_related("employee"), s.LeaveRequestSerializer),
        "notifications": (Notification.objects.filter(recipient=user), s.NotificationSerializer),
        # registers added for every department
        "staff": (_staff_scope(user), s.StaffSerializer),
        "trading_areas": (s.TradingArea.objects.all(), s.TradingAreaSerializer) if c("areas.view", "accounts.manage") else None,
        "leases": (s.Lease.objects.select_related("lessee", "premises"), s.LeaseSerializer) if c("leases.view", "leases.manage") else None,
        "claims": (s.AccountClaim.objects.select_related("user", "area", "matched_property__account", "account"), s.ClaimSerializer)
        if c("claims.review") else None,
        "assets": (_dept(user, s.Asset.objects.prefetch_related("maintenance"), all_caps=("assets.manage", "finance.view_all")), s.AssetSerializer)
        if c("assets.view") else None,
        "incidents": (s.Incident.objects.select_related("lead_officer"), s.IncidentSerializer) if c("incidents.view") else None,
        "activities": (_dept(user, s.CommunityActivity.objects.select_related("officer")), s.ActivitySerializer)
        if c("activities.manage", "activities.verify", "dept.overview") else None,
        "building_plans": (s.BuildingPlan.objects.select_related("bill", "reviewed_by"), s.BuildingPlanSerializer) if c("plans.view") else None,
        "risks": (s.Risk.objects.select_related("owner") if c("risks.manage") else _dept(user, s.Risk.objects.select_related("owner")), s.RiskSerializer)
        if c("risks.view", "risks.manage") else None,
        "meetings": (s.CouncilMeeting.objects.all(), s.MeetingSerializer) if c("meetings.view") else None,
        "resolutions": (s.Resolution.objects.select_related("responsible", "meeting") if (user.sees_all_departments() or c("meetings.manage"))
                        else s.Resolution.objects.filter(Q(department=user.department) | Q(responsible=user)).select_related("responsible", "meeting"),
                        s.ResolutionSerializer) if c("meetings.view", "resolutions.update") else None,
        "ict_tickets": (s.ICTTicket.objects.select_related("raised_by") if c("ict.manage") else s.ICTTicket.objects.filter(raised_by=user).select_related("raised_by"),
                        s.TicketSerializer),
        "policies": (s.Policy.objects.all(), s.PolicySerializer) if c("policies.view") else None,
        "funds_requests": (wf.funds_scope(user, FundsRequest.objects.select_related("requested_by", "voucher").prefetch_related("lines")),
                           s.FundsRequestSerializer),
        "memos": (wf.memo_scope(user, Memo.objects.select_related("sender", "to_user").prefetch_related("replies__author")), s.MemoSerializer),
        "tax_tables": (s.TaxTable.objects.prefetch_related("bands"), s.TaxTableSerializer) if c("payroll.view", "payroll.manage") else None,
        "salary_profiles": (pr.salary_scope(user, s.SalaryProfile.objects.select_related("employee")), s.SalaryProfileSerializer),
        "payslips": (pr.payslip_scope(user, s.Payslip.objects.exclude(status="DRAFT") if not pr.can_view_payroll(user) else s.Payslip.objects.all())
                     .select_related("employee").prefetch_related("payments"), s.PayslipSerializer),
        "cashups": ((s.CashUp.objects.select_related("cashier", "verified_by") if c("cashup.verify")
                     else s.CashUp.objects.filter(cashier=user).select_related("cashier", "verified_by")), s.CashUpSerializer)
        if c("cashup.submit", "cashup.verify") else None,
        "suppliers": (s.Supplier.objects.all(), s.SupplierSerializer) if c("supplier.manage", "procurement.order", "voucher.prepare") else None,
        "purchase_orders": (s.PurchaseOrder.objects.select_related("supplier", "requisition"), s.PurchaseOrderSerializer)
        if c("procurement.order", "finance.view_all", "voucher.prepare") else None,
        "bank_accounts": (s.BankAccount.objects.filter(is_active=True), s.BankAccountSerializer) if c("voucher.pay", "bank.manage", "finance.view_all") else None,
        "correspondence": ((s.Correspondence.objects.select_related("assigned_to") if c("correspondence.manage") or user.sees_all_departments()
                            else s.Correspondence.objects.filter(Q(department=user.department) | Q(assigned_to=user)).select_related("assigned_to")),
                           s.CorrespondenceSerializer) if (c("correspondence.manage") or user.is_head) else None,
    }


def _staff_scope(user):
    from accounts.models import User

    qs = User.objects.filter(user_type=User.UserType.STAFF)
    if user.sees_all_departments() or user.has_cap("hr.view", "tasks.assign_any", "payroll.view", "payroll.manage"):
        return qs
    return qs.filter(department=user.department)


def _dept(user, qs, all_caps=()):
    if user.sees_all_departments() or (all_caps and user.has_cap(*all_caps)):
        return qs
    return qs.filter(department=user.department)


def client_entities(user):
    accounts = _accounts_for(user)
    return {
        "service_standards": (ServiceStandard.objects.all(), s.ServiceStandardSerializer),
        "revenue_heads": (RevenueHead.objects.filter(payable_online=True), s.RevenueHeadSerializer),
        "accounts": (ClientAccount.objects.filter(pk__in=accounts.values("pk")), s.ClientAccountSerializer),
        "properties": (Property.objects.filter(account__in=accounts), s.PropertySerializer),
        "bills": (Bill.objects.filter(account__in=accounts), s.BillSerializer),
        "receipts": (_receipt_scope(user), s.ReceiptSerializer),
        "licences": (Licence.objects.filter(Q(account__in=accounts) | Q(applicant=user)).distinct().select_related("account"), s.LicenceSerializer),
        "complaints": (Complaint.objects.filter(client=user), s.ComplaintSerializer),
        "service_requests": (ServiceRequest.objects.filter(reporter=user), s.ServiceRequestSerializer),
        "stands": (StandApplication.objects.filter(applicant=user), s.StandApplicationSerializer),
        "notifications": (Notification.objects.filter(recipient=user), s.NotificationSerializer),
        "online_payments": (OnlinePayment.objects.filter(user=user).select_related("receipt"), s.OnlinePaymentSerializer),
        "claims": (s.AccountClaim.objects.filter(user=user).select_related("area", "account"), s.ClaimSerializer),
        "building_plans": (s.BuildingPlan.objects.filter(applicant=user).select_related("bill"), s.BuildingPlanSerializer),
        "leases": (s.Lease.objects.filter(lessee__in=accounts).select_related("lessee", "premises"), s.LeaseSerializer),
        "trading_areas": (s.TradingArea.objects.filter(is_active=True), s.TradingAreaSerializer),
    }


def entities_for(user):
    ents = client_entities(user) if user.is_client else staff_entities(user)
    return {k: v for k, v in ents.items() if v is not None}


def pull(user, cursors: dict, limit=PAGE):
    ents = entities_for(user)
    out = {}
    for name, (qs, serializer) in ents.items():
        if cursors and name not in cursors and "*" not in cursors:
            continue
        cur = parse_datetime(cursors.get(name) or "") if cursors else None
        q = qs
        if cur:
            q = q.filter(updated_at__gte=cur)
        has_updated = any(f.name == "updated_at" for f in qs.model._meta.get_fields())
        if not has_updated:
            q = qs  # small reference lists (e.g. staff) are always sent in full
        rows = list(q.order_by("updated_at", "pk")[: limit + 1]) if has_updated else list(q[: limit + 1])
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = serializer(rows, many=True).data
        new_cursor = (rows[-1].updated_at.isoformat() if has_updated else None) if rows else (cursors or {}).get(name)
        out[name] = {"items": items, "cursor": new_cursor, "has_more": has_more}
    return {"server_time": timezone.now().isoformat(), "entities": out}


# --------------------------------------------------------------- operations
def _get(model, pk, qs=None):
    try:
        return (qs if qs is not None else model.objects).get(pk=pk)
    except (ObjectDoesNotExist, ValidationError, ValueError):
        raise ValidationError(f"{model.__name__} {pk} not found or not accessible.")


def _dt(v):
    return parse_datetime(v) if isinstance(v, str) and v else None


def _clean(payload, allowed):
    return {k: v for k, v in payload.items() if k in allowed and v not in (None, "")}


def op_receipt_create(user, p):
    head = _get(RevenueHead, p["revenue_head"])
    account = _get(ClientAccount, p["account"]) if p.get("account") else None
    bill = _get(Bill, p["bill"]) if p.get("bill") else None
    r = fin.issue_receipt(user, revenue_head=head, amount=Decimal(str(p["amount"])), payer_name=p.get("payer_name", ""), account=account,
                          bill=bill, currency=p.get("currency", "USD"), method=p.get("method", "CASH"), reference=p.get("reference", ""),
                          description=p.get("description", ""), channel=Receipt.Channel.FIELD, offline_created_at=_dt(p.get("captured_at")),
                          device_id=p.get("device_id", ""), receipt_id=p.get("id"))
    return "receipts", s.ReceiptSerializer(r).data


def op_receipt_void_request(user, p):
    r = fin.request_void(user, _get(Receipt, p["receipt"]), p.get("reason", ""))
    return "receipts", s.ReceiptSerializer(r).data


COMPLAINT_FIELDS = {"id", "kind", "channel", "name", "phone", "email", "ward", "department", "subject", "details"}


def op_receipt_void_decide(user, p):
    r = fin.decide_void(user, _get(Receipt, p["receipt"]), bool(p.get("approve")), p.get("comment", ""))
    return "receipts", s.ReceiptSerializer(r).data


def op_leave_decide(user, p):
    lv = _get(LeaveRequest, p["leave"])
    if lv.status != LeaveRequest.Status.PENDING:
        raise ValidationError("This leave application has already been decided.")
    if lv.employee_id == user.pk or not (user.is_ceo or (user.has_cap("leave.approve") and user.department == lv.employee.department)):
        raise PermissionDenied("You cannot decide on this leave application.")
    lv.status = LeaveRequest.Status.APPROVED if p.get("approve") else LeaveRequest.Status.REJECTED
    lv.decided_by = user
    lv.decided_at = timezone.now()
    lv.decision_comment = p.get("comment", "")
    lv.save()
    fin.notify([lv.employee], f"Leave {lv.get_status_display().lower()}", lv.decision_comment)
    return "leave", s.LeaveRequestSerializer(lv).data


def op_complaint_create(user, p):
    data = _clean(p, COMPLAINT_FIELDS)
    if user.is_client:
        data["channel"] = Complaint.Channel.APP
    created = _dt(p.get("captured_at"))
    if created and created < timezone.now():
        data["created_at"] = created  # charter clock starts when the client actually complained
    c = wf.log_complaint(user, **data)
    return "complaints", s.ComplaintSerializer(c).data


def op_complaint_action(user, p):
    assignee = None
    if p.get("assignee"):
        from django.contrib.auth import get_user_model

        assignee = get_user_model().objects.filter(pk=p["assignee"]).first()
    c = wf.act_on_complaint(user, _get(Complaint, p["complaint"]), p["action"], note=p.get("note", ""), assignee=assignee,
                            department=p.get("department"))
    return "complaints", s.ComplaintSerializer(c).data


SR_FIELDS = {"id", "category", "description", "location", "ward", "latitude", "longitude", "reporter_name", "reporter_phone"}


def op_service_request_create(user, p):
    data = _clean(p, SR_FIELDS)
    created = _dt(p.get("captured_at"))
    if created and created < timezone.now():
        data["created_at"] = created
    sr = wf.report_service_request(user, **data)
    return "service_requests", s.ServiceRequestSerializer(sr).data


def op_service_request_action(user, p):
    assignee = None
    if p.get("assignee"):
        from django.contrib.auth import get_user_model

        assignee = get_user_model().objects.filter(pk=p["assignee"]).first()
    sr = wf.act_on_request(user, _get(ServiceRequest, p["service_request"]), p["action"], note=p.get("note", ""), assignee=assignee)
    return "service_requests", s.ServiceRequestSerializer(sr).data


def op_task_update(user, p):
    t = wf.update_task(user, _get(Task, p["task"]), status=p.get("status") or None, progress=p.get("progress"), comment=p.get("comment", ""))
    return "tasks", s.TaskSerializer(t).data


def op_requisition_decide(user, p):
    r = fin.decide_requisition(user, _get(Requisition, p["requisition"]), bool(p.get("approve")), p.get("comment", ""))
    return "requisitions", s.RequisitionSerializer(r).data


def op_voucher_decide(user, p):
    v = fin.decide_voucher(user, _get(PaymentVoucher, p["voucher"]), bool(p.get("approve")), p.get("comment", ""))
    return "vouchers", s.VoucherSerializer(v).data


def op_licence_inspect(user, p):
    lic = fin.inspect_licence(user, _get(Licence, p["licence"]), bool(p.get("passed")), p.get("notes", ""))
    return "licences", s.LicenceSerializer(lic).data


def op_licence_decide(user, p):
    fee = Decimal(str(p["fee"])) if p.get("fee") not in (None, "") else None
    lic = fin.decide_licence(user, _get(Licence, p["licence"]), bool(p.get("approve")), p.get("comment", ""), fee=fee)
    return "licences", s.LicenceSerializer(lic).data


def op_licence_apply(user, p):
    account = _get(ClientAccount, p["account"])
    prop = None
    if p.get("property"):
        from finance.models import Property

        prop = _get(Property, p["property"], Property.objects.filter(account=account))
    lic = fin.apply_licence(user, account=account, licence_type=p["licence_type"], business_name=p["business_name"], premises=p["premises"],
                            business_activity=p.get("business_activity", ""), ward=p.get("ward"), licence_id=p.get("id"), property=prop)
    return "licences", s.LicenceSerializer(lic).data


def op_leave_apply(user, p):
    if not user.is_staff_member:
        raise PermissionDenied("Staff only.")
    start, end = parse_date(p["start_date"]), parse_date(p["end_date"])
    if not start or not end or end < start:
        raise ValidationError("Invalid leave dates.")
    lv = LeaveRequest.objects.create(id=p.get("id"), employee=user, leave_type=p.get("leave_type", "ANNUAL"), start_date=start, end_date=end,
                                     reason=p.get("reason", ""), created_by=user)
    heads = [u for u in type(user).objects.filter(department=user.department, is_active=True) if u.is_head and u != user]
    fin.notify(heads, f"Leave application: {user}", f"{lv.start_date} – {lv.end_date}", f"/staff/leave/{lv.pk}/")
    return "leave", s.LeaveRequestSerializer(lv).data


def op_stand_create(user, p):
    data = _clean(p, {"id", "applicant_name", "national_id", "phone", "stand_type", "preferred_location", "ward", "notes"})
    if user.is_client:
        data.update(applicant=user, applicant_name=user.get_full_name())
    elif not user.has_cap("stands.manage"):
        raise PermissionDenied("You cannot capture stand applications.")
    st = StandApplication.objects.create(created_by=user, **data)
    return "stands", s.StandApplicationSerializer(st).data


def op_notification_read(user, p):
    n = _get(Notification, p["notification"], Notification.objects.filter(recipient=user))
    n.is_read = True
    n.save(update_fields=["is_read", "updated_at"])
    return "notifications", s.NotificationSerializer(n).data


# ------------------------------------------------- department operations
from departments import services as dept  # noqa: E402


def op_requisition_create(user, p):
    from finance.models import RequisitionItem

    if not user.is_staff_member:
        raise PermissionDenied("Staff only.")
    items = p.get("items") or []
    if not items:
        raise ValidationError("Add at least one item.")
    line = _get(BudgetLine, p["budget_line"]) if p.get("budget_line") else None
    req = Requisition.objects.create(id=p.get("id"), department=user.department, requested_by=user, purpose=p.get("purpose", ""),
                                     budget_line=line, created_by=user)
    for it in items:
        RequisitionItem.objects.create(requisition=req, description=it["description"], quantity=Decimal(str(it.get("quantity") or 1)),
                                       unit_cost=Decimal(str(it["unit_cost"])))
    req.recalc_total()
    if p.get("submit", True):
        fin.submit_requisition(user, req)
    return "requisitions", s.RequisitionSerializer(req).data


def op_task_create(user, p):
    from accounts.models import User

    assignee = User.objects.filter(pk=p["assigned_to"]).first() if p.get("assigned_to") else None
    data = {"kind": p.get("kind", "TASK"), "title": p["title"], "description": p.get("description", ""), "priority": p.get("priority", "NORMAL"),
            "department": p.get("department") or (assignee.department if assignee else user.department), "assigned_to": assignee,
            "due_date": parse_date(p["due_date"]) if p.get("due_date") else None}
    t = wf.create_task(user, **data)
    return "tasks", s.TaskSerializer(t).data


def op_stand_action(user, p):
    st = dept.stand_action(user, _get(StandApplication, p["stand"]), p["action"], stand=p.get("allocated_stand", ""), note=p.get("note", ""))
    return "stands", s.StandApplicationSerializer(st).data


def op_project_update(user, p):
    pr = dept.project_update(user, _get(Project, p["project"]), progress=p.get("progress"), status=p.get("status") or None, note=p.get("note", ""))
    return "projects", s.ProjectSerializer(pr).data


def op_finding_respond(user, p):
    f = dept.respond_finding(user, _get(AuditFinding, p["finding"]), response=p["response"], date=parse_date(p["date"]) if p.get("date") else None)
    return "audit_findings", s.AuditFindingSerializer(f).data


INCIDENT_FIELDS = {"id", "incident_type", "title", "description", "ward", "location", "households_affected", "people_injured", "deaths",
                   "livestock_lost", "crops_hectares"}


def op_incident_create(user, p):
    data = _clean(p, INCIDENT_FIELDS)
    if p.get("captured_at"):
        data["occurred_at"] = _dt(p["captured_at"])
    inc = dept.report_incident(user, **data)
    return "incidents", s.IncidentSerializer(inc).data


def op_incident_update(user, p):
    inc = dept.update_incident(user, _get(s.Incident, p["incident"]), status=p.get("status") or None, response=p.get("response", ""),
                               households_affected=p.get("households_affected"))
    return "incidents", s.IncidentSerializer(inc).data


def op_activity_create(user, p):
    data = _clean(p, {"id", "activity_type", "title", "ward", "venue", "department"})
    if p.get("date"):
        data["date"] = parse_date(p["date"])
    act = dept.plan_activity(user, **data)
    if p.get("report"):
        act = dept.report_activity(user, act, report=p["report"], participants=p.get("participants") or 0)
    return "activities", s.ActivitySerializer(act).data


def op_activity_report(user, p):
    act = dept.report_activity(user, _get(s.CommunityActivity, p["activity"]), report=p["report"], participants=p.get("participants") or 0)
    return "activities", s.ActivitySerializer(act).data


def op_activity_verify(user, p):
    act = dept.verify_activity(user, _get(s.CommunityActivity, p["activity"]), bool(p.get("approve")), p.get("note", ""))
    return "activities", s.ActivitySerializer(act).data


def op_plan_action(user, p):
    plan = dept.plan_action(user, _get(s.BuildingPlan, p["plan"]), p["action"], p.get("note", ""))
    return "building_plans", s.BuildingPlanSerializer(plan).data


def op_plan_create(user, p):
    data = _clean(p, {"id", "applicant_name", "phone", "stand_number", "location", "ward", "development_type", "description", "floor_area"})
    plan = dept.submit_building_plan(user, **data)
    return "building_plans", s.BuildingPlanSerializer(plan).data


def op_asset_condition(user, p):
    a = _get(s.Asset, p["asset"])
    dept.report_asset_condition(user, a, condition=p["condition"], note=p.get("note", ""), work_done=p.get("note", ""),
                                cost=Decimal(str(p.get("cost") or 0)))
    a.refresh_from_db()
    return "assets", s.AssetSerializer(a).data


def op_ict_create(user, p):
    t = dept.raise_ticket(user, **_clean(p, {"id", "category", "subject", "description", "priority"}))
    return "ict_tickets", s.TicketSerializer(t).data


def op_ict_action(user, p):
    t = dept.ticket_action(user, _get(s.ICTTicket, p["ticket"]), p["action"], p.get("note", ""))
    return "ict_tickets", s.TicketSerializer(t).data


def op_resolution_update(user, p):
    r = dept.update_resolution(user, _get(s.Resolution, p["resolution"]), status=p["status"], note=p.get("note", ""))
    return "resolutions", s.ResolutionSerializer(r).data


def op_claim_decide(user, p):
    claim = _get(s.AccountClaim, p["claim"])
    c = fin.decide_claim(user, claim, bool(p.get("approve")), note=p.get("note", ""), create_account=bool(p.get("create_account")),
                         monthly_rates=p.get("monthly_rates") or None)
    return "claims", s.ClaimSerializer(c).data


def op_claim_create(user, p):
    area = _get(s.TradingArea, p["area"]) if p.get("area") else None
    c = fin.submit_claim(user, stand_number=p["stand_number"], area=area, location=p.get("location", ""), business_name=p.get("business_name", ""),
                         id_number=p.get("id_number", ""), phone=p.get("phone", ""), claim_type=p.get("claim_type", "OWNER"), notes=p.get("notes", ""),
                         claim_id=p.get("id"))
    return "claims", s.ClaimSerializer(c).data


def op_reminders_send(user, p):
    from finance.models import Property

    props = Property.objects.alive().filter(is_active=True)
    if p.get("properties"):
        props = props.filter(pk__in=p["properties"])
    elif p.get("area"):
        props = props.filter(area_id=p["area"])
    else:
        raise ValidationError("Choose an area or stands.")
    n = fin.send_compliance_reminders(user, list(props), campaign=p.get("campaign", "Reminder from mobile app"), extra=p.get("extra", ""))
    return "", {"sent": n}


# --------------------------------------------- requests for funds & memos
def op_funds_create(user, p):
    from workflow import funds as fr
    from workflow.models import FundsRequestLine

    if not user.has_cap("funds.request"):
        raise PermissionDenied("Staff only.")
    lines = p.get("lines") or []
    if not lines:
        raise ValidationError("Add at least one line.")
    line = _get(BudgetLine, p["budget_line"]) if p.get("budget_line") else None
    req = FundsRequest.objects.create(
        id=p.get("id"), requested_by=user, created_by=user, department=user.department, request_type=p.get("request_type", "OTHER"),
        title=p["title"], purpose=p.get("purpose", ""), destination=p.get("destination", ""),
        depart_date=parse_date(p["depart_date"]) if p.get("depart_date") else None,
        return_date=parse_date(p["return_date"]) if p.get("return_date") else None, travellers=p.get("travellers", ""),
        currency=p.get("currency", "USD"), needed_by=parse_date(p["needed_by"]) if p.get("needed_by") else None,
        requires_payment=bool(p.get("requires_payment", True)), payee_name=p.get("payee_name", ""), payment_method=p.get("payment_method", "EFT"),
        payment_details=p.get("payment_details", ""), budget_line=line)
    for ln in lines:
        FundsRequestLine.objects.create(request=req, description=ln["description"], quantity=Decimal(str(ln.get("quantity") or 1)),
                                        unit_cost=Decimal(str(ln["unit_cost"])))
    req.recalc_total()
    if p.get("submit", True):
        fr.submit(user, req)
    return "funds_requests", s.FundsRequestSerializer(req).data


def op_funds_action(user, p):
    from workflow import funds as fr

    req = _get(FundsRequest, p["id"])
    if not fr.can_view(user, req):
        raise PermissionDenied("You cannot see this request.")
    a, note = p["action"], p.get("comment", "")
    if a == "submit":
        fr.submit(user, req)
    elif a in ("approve", "reject", "return"):
        fr.decide(user, req, a, note)
    elif a == "remind":
        fr.remind(user, req, note)
    elif a == "cancel":
        fr.cancel(user, req, note)
    elif a == "pay":
        fr.prepare_payment(user, req, method=p.get("method") or None)
    else:
        raise ValidationError("Unknown action.")
    req.refresh_from_db()
    return "funds_requests", s.FundsRequestSerializer(req).data


def op_memo_create(user, p):
    from accounts.models import User
    from workflow import memos as mm

    to_user = User.objects.filter(pk=p["to_user"]).first() if p.get("to_user") else None
    memo = mm.send(user, kind=p.get("kind", "MESSAGE"), to_department=p["to_department"], to_user=to_user, subject=p.get("subject", ""),
                   body=p.get("body", ""), priority=p.get("priority", "NORMAL"), memo_id=p.get("id"))
    return "memos", s.MemoSerializer(memo).data


def op_memo_reply(user, p):
    from accounts.models import User
    from workflow import memos as mm

    memo = _get(Memo, p["id"])
    if p.get("assigned_to"):
        mm.to_task(user, memo, assigned_to=User.objects.get(pk=p["assigned_to"]),
                   due_date=parse_date(p["due_date"]) if p.get("due_date") else None)
    else:
        mm.reply(user, memo, p.get("body", ""), close=bool(p.get("close")))
    memo.refresh_from_db()
    return "memos", s.MemoSerializer(memo).data


# --------------------------------------------- vouchers, cash-ups, orders, correspondence
def op_voucher_prepare(user, p):
    data = {"category": p.get("category", "SUPPLIER"), "description": p["description"],
            "amount": Decimal(str(p["amount"])), "currency": p.get("currency", "USD"), "method": p.get("method", "EFT"),
            "invoice_number": p.get("invoice_number", ""), "department": p.get("department") or user.department}
    if p.get("payee_name"):
        data["payee_name"] = p["payee_name"]
    if p.get("supplier"):
        data["supplier"] = _get(s.Supplier, p["supplier"])
    if p.get("budget_line"):
        data["budget_line"] = _get(BudgetLine, p["budget_line"])
    if p.get("purchase_order"):
        data["purchase_order"] = _get(s.PurchaseOrder, p["purchase_order"])
    if p.get("id"):
        data["id"] = p["id"]
    v = fin.prepare_voucher(user, **data)
    return "vouchers", s.VoucherSerializer(v).data


def op_voucher_pay(user, p):
    v = fin.pay_voucher(user, _get(PaymentVoucher, p["voucher"]), bank_account=_get(s.BankAccount, p["bank_account"]),
                        payment_reference=p.get("payment_reference", ""))
    return "vouchers", s.VoucherSerializer(v).data


def op_cashup_submit(user, p):
    cu = fin.submit_cashup(user, currency=p.get("currency", "USD"), declared_cash=Decimal(str(p["declared_cash"])), notes=p.get("notes", ""))
    return "cashups", s.CashUpSerializer(cu).data


def op_cashup_verify(user, p):
    cu = fin.verify_cashup(user, _get(s.CashUp, p["cashup"]), bool(p.get("ok")), p.get("notes", ""))
    return "cashups", s.CashUpSerializer(cu).data


def op_po_create(user, p):
    po = fin.raise_purchase_order(user, _get(Requisition, p["requisition"]), _get(s.Supplier, p["supplier"]),
                                  Decimal(str(p["amount"])) if p.get("amount") else None,
                                  parse_date(p["expected_delivery"]) if p.get("expected_delivery") else None, p.get("notes", ""))
    return "purchase_orders", s.PurchaseOrderSerializer(po).data


def op_po_receive(user, p):
    po = fin.receive_goods(user, _get(s.PurchaseOrder, p["po"]), p.get("notes", ""))
    return "purchase_orders", s.PurchaseOrderSerializer(po).data


def op_correspondence_create(user, p):
    from accounts.models import User

    c = wf.log_correspondence(user, sender=p["sender"], sender_contact=p.get("sender_contact", ""), subject=p["subject"],
                              department=p["department"], assigned_to=User.objects.filter(pk=p.get("assigned_to") or 0).first(),
                              file_reference=p.get("file_reference", ""), corr_id=p.get("id"))
    return "correspondence", s.CorrespondenceSerializer(c).data


def op_correspondence_update(user, p):
    c = wf.update_correspondence(user, _get(s.Correspondence, p["id"]), status=p.get("status", ""), response_summary=p.get("response_summary", ""))
    return "correspondence", s.CorrespondenceSerializer(c).data


# ------------------------------------------------------------------ payroll
def op_salary_update(user, p):
    from accounts.models import User

    emp = User.objects.filter(pk=p["employee"]).first()
    if emp is None:
        raise ValidationError("Employee not found.")
    data = {k: v for k, v in p.items() if k in pr.FIELDS}
    prof = pr.update_salary(user, emp, **data)
    return "salary_profiles", s.SalaryProfileSerializer(prof).data


def op_payroll_run(user, p):
    n = pr.run_payroll(user, int(p["year"]), int(p["month"]))
    return "", {"created": n}


def op_payroll_approve(user, p):
    n = pr.approve_payroll(user, int(p["year"]), int(p["month"]))
    return "", {"approved": n}


def op_payslip_pay(user, p):
    slip = _get(s.Payslip, p["payslip"])
    bank = _get(s.BankAccount, p["bank_account"]) if p.get("bank_account") else None
    pr.pay_payslip(user, slip, amount=p["amount"], method=p.get("method", "EFT"), reference=p.get("reference", ""), bank_account=bank)
    slip.refresh_from_db()
    return "payslips", s.PayslipSerializer(slip).data


STAFF_OPS = {
    "salary.update": op_salary_update,
    "payroll.run": op_payroll_run,
    "payroll.approve": op_payroll_approve,
    "payslip.pay": op_payslip_pay,
    "voucher.prepare": op_voucher_prepare,
    "voucher.pay": op_voucher_pay,
    "cashup.submit": op_cashup_submit,
    "cashup.verify": op_cashup_verify,
    "po.create": op_po_create,
    "po.receive": op_po_receive,
    "correspondence.create": op_correspondence_create,
    "correspondence.update": op_correspondence_update,
    "funds.create": op_funds_create,
    "funds.action": op_funds_action,
    "memo.create": op_memo_create,
    "memo.reply": op_memo_reply,
    "requisition.create": op_requisition_create,
    "task.create": op_task_create,
    "stand.action": op_stand_action,
    "project.update": op_project_update,
    "finding.respond": op_finding_respond,
    "incident.create": op_incident_create,
    "incident.update": op_incident_update,
    "activity.create": op_activity_create,
    "activity.report": op_activity_report,
    "activity.verify": op_activity_verify,
    "plan.action": op_plan_action,
    "plan.create": op_plan_create,
    "asset.condition": op_asset_condition,
    "ict.create": op_ict_create,
    "ict.action": op_ict_action,
    "resolution.update": op_resolution_update,
    "claim.decide": op_claim_decide,
    "reminders.send": op_reminders_send,
    "receipt.create": op_receipt_create,
    "receipt.void_request": op_receipt_void_request,
    "receipt.void_decide": op_receipt_void_decide,
    "leave.decide": op_leave_decide,
    "complaint.create": op_complaint_create,
    "complaint.action": op_complaint_action,
    "service_request.create": op_service_request_create,
    "service_request.action": op_service_request_action,
    "task.update": op_task_update,
    "requisition.decide": op_requisition_decide,
    "voucher.decide": op_voucher_decide,
    "licence.inspect": op_licence_inspect,
    "licence.decide": op_licence_decide,
    "leave.apply": op_leave_apply,
    "stand.create": op_stand_create,
    "notification.read": op_notification_read,
}

CLIENT_OPS = {
    "claim.create": op_claim_create,
    "plan.create": op_plan_create,
    "complaint.create": op_complaint_create,
    "service_request.create": op_service_request_create,
    "licence.apply": op_licence_apply,
    "stand.create": op_stand_create,
    "notification.read": op_notification_read,
}


def push(user, operations, device_id=""):
    handlers = CLIENT_OPS if user.is_client else STAFF_OPS
    results = []
    for op in operations:
        op_id = op.get("op_id")
        op_type = op.get("type", "")
        existing = SyncOperation.objects.filter(op_id=op_id).first() if op_id else None
        if existing:
            if existing.user_id != user.pk:
                results.append({"op_id": op_id, "status": "rejected", "error": "Operation id belongs to another user."})
                continue
            results.append({"op_id": op_id, "status": existing.status, "duplicate": True, "error": existing.error, **existing.result})
            continue
        handler = handlers.get(op_type)
        status, error, result = "applied", "", {}
        if handler is None:
            status, error = "rejected", f"Operation '{op_type}' is not allowed for this app/user."
        else:
            try:
                with transaction.atomic():
                    entity, record = handler(user, op.get("payload") or {})
                result = {"entity": entity, "record": record} if entity else {"info": record}
            except PermissionDenied as exc:
                status, error = "rejected", str(exc) or "Permission denied."
            except ValidationError as exc:
                status, error = "rejected", " ".join(exc.messages)
            except (KeyError, TypeError, ValueError) as exc:
                status, error = "rejected", f"Invalid data: {exc}"
        if op_id:
            SyncOperation.objects.create(op_id=op_id, user=user, device_id=device_id, op_type=op_type, payload=op.get("payload") or {},
                                         status=status, error=error, result=_json(result), client_created_at=_dt(op.get("created_at")))
        results.append({"op_id": op_id, "status": status, "error": error, **_json(result)})
    return results


def _json(data):
    import json

    from rest_framework.utils.encoders import JSONEncoder

    return json.loads(json.dumps(data, cls=JSONEncoder))
