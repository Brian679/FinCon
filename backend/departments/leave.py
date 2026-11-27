"""Leave approval: the employee applies (from their profile) → Head of Department → HR (HR Officer or
Administration Officer) → CEO → approved. Everyone concerned is notified at each step.

A step is skipped when nobody other than the employee (or someone who already approved) can take it –
e.g. a Head of Department's leave starts with HR, and HR staff's own leave goes to the other HR approver."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core import audit
from core.models import AuditLog
from finance.models import ApprovalRecord
from finance.services import _record, notify

from .models import LeaveRequest

STAGES = [("HOD", "Head of Department"), ("HR", "Human Resources / Administration Officer"), ("CEO", "Chief Executive Officer")]
LABELS = dict(STAGES)


def _eligible(stage, lv):
    User = get_user_model()
    emp = lv.employee
    staff = User.objects.filter(user_type=User.UserType.STAFF, is_active=True).exclude(pk=emp.pk)
    if stage == "HOD":
        return [u for u in staff.filter(department=emp.department) if u.is_head and not u.is_ceo]
    if stage == "HR":
        return [u for u in staff if u.has_cap("leave.hr_approve")]
    if stage == "CEO":
        return [u for u in staff if u.is_ceo]
    return []


def _already_approved(lv):
    return set(ApprovalRecord.for_object(lv).filter(decision="APPROVED").values_list("user_id", flat=True))


def approvers(lv):
    """People who may decide the leave at its current step."""
    if lv.status != LeaveRequest.Status.PENDING or not lv.stage:
        return []
    done = _already_approved(lv)
    return [u for u in _eligible(lv.stage, lv) if u.pk not in done]


def can_decide(user, lv):
    return any(u.pk == user.pk for u in approvers(lv))


def _advance(lv, after=None):
    """Move to the next step that somebody can take; if none is left the leave is approved."""
    order = [s for s, _ in STAGES]
    start = order.index(after) + 1 if after else 0
    done = _already_approved(lv)
    for stage in order[start:]:
        if [u for u in _eligible(stage, lv) if u.pk not in done]:
            lv.stage = stage
            lv.save(update_fields=["stage", "updated_at"])
            notify([u for u in _eligible(stage, lv) if u.pk not in done], f"Leave to approve: {lv.employee.get_full_name()}",
                   f"{lv.get_leave_type_display()} {lv.start_date:%d %b} – {lv.end_date:%d %b %Y} ({lv.days} working day(s)) – "
                   f"waiting for the {LABELS[stage]}", f"/staff/leave/{lv.pk}/")
            return lv
    lv.stage = ""
    lv.status = LeaveRequest.Status.APPROVED
    lv.decided_at = timezone.now()
    lv.save(update_fields=["stage", "status", "decided_at", "updated_at"])
    audit.log(AuditLog.Action.APPROVE, lv, message="Leave fully approved")
    notify([lv.employee], "Your leave is approved",
           f"{lv.get_leave_type_display()} {lv.start_date:%d %b} – {lv.end_date:%d %b %Y}. Enjoy your leave.", f"/staff/leave/{lv.pk}/")
    hr = _eligible("HR", lv)
    notify(hr, f"Leave approved: {lv.employee.get_full_name()}", f"{lv.start_date:%d %b} – {lv.end_date:%d %b %Y}", f"/staff/leave/{lv.pk}/")
    return lv


@transaction.atomic
def submit(lv):
    """Called once the application is saved: route it to the first approver."""
    return _advance(lv)


@transaction.atomic
def decide(user, lv, approve, comment=""):
    lv = LeaveRequest.objects.select_for_update().get(pk=lv.pk)
    if lv.status != LeaveRequest.Status.PENDING:
        raise ValidationError("This leave application has already been decided.")
    if lv.employee_id == user.pk:
        raise PermissionDenied("You cannot approve your own leave.")
    if not can_decide(user, lv):
        raise PermissionDenied(f"This leave is waiting for the {LABELS.get(lv.stage, 'next approver')}.")
    stage = lv.stage
    if not approve and not comment:
        raise ValidationError("Give the reason for not approving the leave.")
    _record(lv, LABELS[stage], "APPROVED" if approve else "REJECTED", user, comment)
    lv.decided_by = user
    lv.decision_comment = comment
    if not approve:
        lv.status = LeaveRequest.Status.REJECTED
        lv.stage = ""
        lv.decided_at = timezone.now()
        lv.save()
        audit.log(AuditLog.Action.REJECT, lv, user=user, message=comment)
        notify([lv.employee], "Your leave was not approved", f"{LABELS[stage]}: {comment}", f"/staff/leave/{lv.pk}/")
        return lv
    lv.save()
    _advance(lv, after=stage)
    lv.refresh_from_db()
    if lv.status == LeaveRequest.Status.PENDING:
        notify([lv.employee], f"Leave approved by the {LABELS[stage]}", f"Now with the {LABELS[lv.stage]}.", f"/staff/leave/{lv.pk}/")
    return lv


@transaction.atomic
def cancel(user, lv):
    if lv.employee_id != user.pk:
        raise PermissionDenied("Only the applicant can cancel the application.")
    if lv.status not in (LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED) or lv.start_date <= timezone.localdate():
        raise ValidationError("Only leave that has not started can be cancelled.")
    lv.status, lv.stage = LeaveRequest.Status.CANCELLED, ""
    lv.save()
    _record(lv, "Applicant", "CANCELLED", user, "")
    return lv


def route(lv):
    """The tracker: every step with who did it, or who it is waiting for."""
    recs = list(ApprovalRecord.for_object(lv).order_by("timestamp"))
    rows = [{"stage": "Applied", "who": lv.employee.get_full_name(), "when": lv.created_at, "state": "done", "comment": lv.reason}]
    for r in recs:
        rows.append({"stage": r.stage, "who": r.user.get_full_name() if r.user else "", "when": r.timestamp,
                     "state": "done" if r.decision == "APPROVED" else "rejected", "comment": r.comment})
    if lv.status == LeaveRequest.Status.PENDING and lv.stage:
        rows.append({"stage": LABELS[lv.stage], "who": ", ".join(u.get_full_name() for u in approvers(lv)), "when": None, "state": "waiting",
                     "comment": ""})
    elif lv.status == LeaveRequest.Status.APPROVED:
        rows.append({"stage": "Approved – leave can be taken", "who": "", "when": lv.decided_at, "state": "done", "comment": ""})
    return rows


def awaiting(user, qs=None):
    """Leave applications waiting for this user's decision."""
    qs = qs if qs is not None else LeaveRequest.objects.alive()
    return [lv for lv in qs.filter(status=LeaveRequest.Status.PENDING).exclude(employee=user).select_related("employee") if can_decide(user, lv)]
