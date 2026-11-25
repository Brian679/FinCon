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
from workflow import services as wf
from workflow.models import Complaint, ServiceRequest, Task, TaskComment

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
        "licences": (Licence.objects.select_related("account"), s.LicenceSerializer) if c("licence.view") else None,
        "requisitions": (_requisition_scope(user), s.RequisitionSerializer),
        "vouchers": (PaymentVoucher.objects.select_related("prepared_by", "budget_line"), s.VoucherSerializer)
        if c("voucher.prepare", "voucher.check", "voucher.approve", "voucher.authorise", "finance.view_all") else None,
        "budget_lines": (BudgetLine.objects.filter(financial_year=timezone.localdate().year), s.BudgetLineSerializer) if c("budget.view") else None,
        "tasks": (_task_scope(user), s.TaskSerializer),
        "task_comments": (TaskComment.objects.filter(task__in=_task_scope(user)).select_related("author"), s.TaskCommentSerializer),
        "complaints": (wf.complaint_scope(user, Complaint.objects.all()), s.ComplaintSerializer),
        "service_requests": (wf.request_scope(user, ServiceRequest.objects.all()), s.ServiceRequestSerializer),
        "stands": (StandApplication.objects.all(), s.StandApplicationSerializer) if c("stands.view") else None,
        "projects": (Project.objects.all(), s.ProjectSerializer) if c("projects.view") else None,
        "audit_findings": (_finding_scope(user), s.AuditFindingSerializer) if _finding_scope(user) is not None else None,
        "leave": (_leave_scope(user).select_related("employee"), s.LeaveRequestSerializer),
        "notifications": (Notification.objects.filter(recipient=user), s.NotificationSerializer),
    }


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
        rows = list(q.order_by("updated_at", "pk")[: limit + 1]) if hasattr(qs.model, "updated_at") else list(q[: limit + 1])
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = serializer(rows, many=True).data
        new_cursor = rows[-1].updated_at.isoformat() if rows else (cursors or {}).get(name)
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
    lic = fin.apply_licence(user, account=account, licence_type=p["licence_type"], business_name=p["business_name"], premises=p["premises"],
                            business_activity=p.get("business_activity", ""), ward=p.get("ward"), licence_id=p.get("id"))
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


STAFF_OPS = {
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
                result = {"entity": entity, "record": record}
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
