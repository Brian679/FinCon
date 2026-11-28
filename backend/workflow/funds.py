"""Requests for funds / purchases raised by any department.

Route: requester (with the quotation / supporting documents attached) -> Head of Department -> Administration Officer
-> CEO -> Accountant -> Treasurer -> for purchases, fuel and repairs: the purchase is confirmed (invoice / delivery note
attached) -> payment voucher: Finance prepares it, the Accountant checks it, the Treasurer approves the payment again (and
the CEO authorises it when it is above the threshold), the cashier pays -> the requester is told it is done.

Every move is written to the approval history and the audit trail, the next
approvers are notified, and the requester is told where the request is. The
requester can send a reminder to whoever is holding it.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core import audit
from core.models import AuditLog, Department, Notification

from .models import FundsRequest

User = get_user_model()
S = FundsRequest.Status

# status -> (stage label, who decides)
STAGES = [
    (S.PENDING_HOD, "Head of Department"),
    (S.PENDING_ADMIN, "Administration Officer"),
    (S.PENDING_CEO, "Chief Executive Officer"),
    (S.PENDING_ACCOUNTANT, "Accountant"),
    (S.PENDING_TREASURER, "Treasurer"),
]
STAGE_LABEL = dict(STAGES)
STAGE_CAP = {S.PENDING_ADMIN: "funds.admin_approve", S.PENDING_ACCOUNTANT: "funds.accountant_approve", S.PENDING_TREASURER: "funds.treasurer_approve",
             S.PENDING_CEO: "funds.ceo_approve"}
# Requests that buy something: evidence (quotation) at submission, and the purchase is confirmed (invoice / delivery note) before payment.
PURCHASE_TYPES = ("PURCHASE", "FUEL", "REPAIRS", "TRAINING")
CONFIRM_TYPES = ("PURCHASE", "FUEL", "REPAIRS")
REMINDER_COOLDOWN = timedelta(hours=getattr(settings, "FUNDS_REMINDER_COOLDOWN_HOURS", 24))


def _link(req):
    return f"/staff/funds/{req.pk}/"


def _staff():
    return User.objects.filter(is_active=True, user_type=User.UserType.STAFF)


def eligible(req, status=None):
    """Officers who may decide the request at a stage."""
    status = status or req.status
    if status == S.PENDING_HOD:
        return [u for u in _staff().filter(department=req.department) if u.is_head]
    cap = STAGE_CAP.get(status)
    return [u for u in _staff() if u.has_cap(cap)] if cap else []


def _voucher_holders(v):
    from finance.models import PaymentVoucher as PV
    from finance.services import users_with_cap

    if v.status == PV.Status.PREPARED:
        return "Accountant – checking the payment voucher", users_with_cap("voucher.check", Department.FINANCE)
    if v.status == PV.Status.CHECKED:
        return "Treasurer – approving the payment", users_with_cap("voucher.approve", Department.FINANCE)
    if v.status == PV.Status.APPROVED and v.needs_ceo:
        return "CEO – authorising the payment", users_with_cap("voucher.authorise")
    if v.is_ready_for_payment:
        return "Cashier – paying out", users_with_cap("voucher.pay", Department.FINANCE)
    return v.get_status_display(), []


def current_holder(req):
    """(where the request is now, [officers holding it])."""
    if req.status in STAGE_LABEL:
        return STAGE_LABEL[req.status], [u for u in eligible(req) if u.pk != req.requested_by_id]
    if req.status == S.PENDING_CONFIRMATION:
        return "Confirm the purchase – attach the invoice / delivery note", [req.requested_by] + [
            u for u in _staff() if u.has_cap("procurement.order")]
    if req.status == S.PENDING_PAYMENT:
        from finance.services import users_with_cap

        return "Finance – preparing the payment voucher", users_with_cap("voucher.prepare", Department.FINANCE)
    if req.status == S.PAYMENT_PROCESSING and req.voucher_id:
        return _voucher_holders(req.voucher)
    if req.status == S.RETURNED:
        return "Requester – make the changes asked for and resubmit", [req.requested_by]
    return req.get_status_display(), []


def where_now(req):
    label, people = current_holder(req)
    names = ", ".join(sorted({p.get_full_name() or p.username for p in people}))
    return f"{label} ({names})" if names and req.is_open else label


# ------------------------------------------------------------------ helpers
def _record(req, stage, decision, user, comment="", action=AuditLog.Action.OTHER):
    from finance.models import ApprovalRecord

    ApprovalRecord.objects.create(content_type=ContentType.objects.get_for_model(req), object_id=str(req.pk), stage=stage,
                                  decision=decision, user=user, comment=comment)
    audit.log(action, req, user=user, message=f"{stage}: {decision}. {comment}".strip())


def history(req):
    from finance.models import ApprovalRecord

    return ApprovalRecord.for_object(req)


def _tell(users, title, body, req):
    """In-app notification (shows on the phone after sync) + e-mail."""
    seen = set()
    for u in users:
        if u is None or u.pk in seen:
            continue
        seen.add(u.pk)
        Notification.objects.create(recipient=u, title=title, body=body, link=_link(req))
        if u.email:
            send_mail(title, f"{body}\n\n{settings.STAFF_SITE_URL.rstrip('/')}{_link(req)}", None, [u.email], fail_silently=True)


def _approved_this_round(req):
    qs = history(req).filter(decision="APPROVED")
    if req.submitted_at:
        qs = qs.filter(timestamp__gte=req.submitted_at)
    return {r.user_id for r in qs}


def _move_to(req, status, actor):
    req.status = status
    req.stage_since = timezone.now()
    req.save()


def _advance(req, actor):
    """Move to the next stage that still needs a decision."""
    order = [st for st, _l in STAGES]
    idx = order.index(req.status) + 1 if req.status in order else 0
    approved = _approved_this_round(req)
    while idx < len(order):
        status = order[idx]
        label = STAGE_LABEL[status]
        people = eligible(req, status)
        others = [u for u in people if u.pk != req.requested_by_id]
        already = [u for u in people if u.pk in approved]
        if already:
            _record(req, label, "SKIPPED", actor, f"Already approved by {already[0].get_full_name() or already[0].username} at an earlier stage.")
        elif not others:
            reason = "This is the requester's own office." if people else "No officer holds this post."
            _record(req, label, "SKIPPED", actor, reason)
        else:
            _move_to(req, status, actor)
            _tell(others, f"Request {req.reference} awaits your approval",
                  f"{req.get_request_type_display()}: {req.title} – {req.currency} {req.total:,.2f} from {req.requested_by.get_full_name()} "
                  f"({req.get_department_display()}).", req)
            if actor.pk != req.requested_by_id:
                _tell([req.requested_by], f"Your request {req.reference} moved to the {label}",
                      f"Approved by {actor.get_full_name() or actor.username}. It is now with the {label}.", req)
            return req
        idx += 1
    # all approvals done
    if req.requires_payment and req.total > 0 and req.request_type in CONFIRM_TYPES and not req.purchase_confirmed_at:
        _move_to(req, S.PENDING_CONFIRMATION, actor)
        _tell([req.requested_by] + [u for u in _staff() if u.has_cap("procurement.order")], f"Request {req.reference} approved – confirm the purchase",
              "Attach the invoice or delivery note and confirm the purchase; Finance then prepares the payment.", req)
    elif req.requires_payment and req.total > 0:
        from finance.services import users_with_cap

        _move_to(req, S.PENDING_PAYMENT, actor)
        _tell(users_with_cap("voucher.prepare", Department.FINANCE), f"Request {req.reference} approved – prepare payment",
              f"Pay {req.payee_name or req.requested_by.get_full_name()} {req.currency} {req.total:,.2f} for: {req.title}.", req)
        _tell([req.requested_by], f"Your request {req.reference} has been fully approved",
              "All approvals are done. Finance is now preparing the payment – you will be told when it is paid.", req)
    else:
        req.completed_at = timezone.now()
        _move_to(req, S.COMPLETED, actor)
        _tell([req.requested_by], f"Your request {req.reference} has been approved", "All approvals are done – the request is complete.", req)
    return req


# ---------------------------------------------------------------- actions
def can_decide(user, req):
    return (req.status in STAGE_LABEL and user.pk != req.requested_by_id and user in eligible(req)
            and user.pk not in _approved_this_round(req))


def can_view(user, req):
    return funds_scope(user, FundsRequest.objects.filter(pk=req.pk)).exists()


def funds_scope(user, qs):
    if user.is_client:
        return qs.none()
    mine = Q(requested_by=user)
    if user.has_cap("funds.view_all", "funds.admin_approve", "funds.accountant_approve", "procurement.order") or user.sees_all_departments():
        return qs.filter(mine | ~Q(status=S.DRAFT))
    if user.is_head:
        return qs.filter(mine | (Q(department=user.department) & ~Q(status=S.DRAFT)))
    return qs.filter(mine)


def awaiting(user):
    """Requests waiting for this user's decision (approvals list)."""
    qs = FundsRequest.objects.alive().filter(status__in=FundsRequest.PENDING).select_related("requested_by")
    return [r for r in qs if can_decide(user, r)]


@transaction.atomic
def submit(user, req):
    if req.requested_by_id != user.pk:
        raise PermissionDenied("Only the person who wrote the request can submit it.")
    if req.status not in (S.DRAFT, S.RETURNED):
        raise ValidationError("This request has already been submitted.")
    req.recalc_total()
    if not req.lines.exists():
        raise ValidationError("Add at least one line (what you need and how much) before submitting.")
    from . import attachments as att

    if req.request_type in PURCHASE_TYPES and not att.for_object("funds", req).exists():
        raise ValidationError("Attach the quotation or other supporting document before submitting.")
    if req.request_type == FundsRequest.RequestType.TRAVEL and not (req.destination and req.depart_date):
        raise ValidationError("Travel & subsistence requests need the destination and departure date.")
    resubmitted = req.status == S.RETURNED
    req.submitted_at = timezone.now()
    req.status = S.DRAFT
    req.decision_note = ""
    _record(req, "Requester", "RESUBMITTED" if resubmitted else "SUBMITTED", user)
    return _advance(req, user)


@transaction.atomic
def decide(user, req, decision, comment=""):
    """decision: approve | reject | return"""
    if req.status not in STAGE_LABEL:
        raise ValidationError("This request is not waiting for an approval.")
    label = STAGE_LABEL[req.status]
    if req.requested_by_id == user.pk:
        raise PermissionDenied("Segregation of duties: you cannot approve your own request.")
    if user not in eligible(req):
        audit.log(AuditLog.Action.ACCESS_DENIED, req, user=user, message=f"Not the {label}")
        raise PermissionDenied(f"This request is waiting for the {label}.")
    if user.pk in _approved_this_round(req):
        raise PermissionDenied("Segregation of duties: you have already approved this request.")
    if decision == "approve":
        if req.status == S.PENDING_TREASURER and req.budget_line_id and req.requires_payment:
            available = req.budget_line.available()
            if req.total > available:
                raise ValidationError(f"Insufficient budget on vote {req.budget_line.vote_code}: available ${available:,.2f}.")
        _record(req, label, "APPROVED", user, comment, AuditLog.Action.APPROVE)
        return _advance(req, user)
    if not comment.strip():
        raise ValidationError("Give a reason so the requester knows what to do.")
    if decision == "reject":
        req.status = S.REJECTED
        req.decision_note = comment[:255]
        req.save()
        _record(req, label, "REJECTED", user, comment, AuditLog.Action.REJECT)
        _tell([req.requested_by], f"Your request {req.reference} was rejected by the {label}", comment, req)
        return req
    if decision == "return":
        req.status = S.RETURNED
        req.decision_note = comment[:255]
        req.stage_since = timezone.now()
        req.save()
        _record(req, label, "RETURNED", user, comment, AuditLog.Action.REJECT)
        _tell([req.requested_by], f"Your request {req.reference} was returned for changes", f"{label}: {comment}", req)
        return req
    raise ValidationError("Unknown decision.")


@transaction.atomic
def cancel(user, req, reason=""):
    if req.requested_by_id != user.pk:
        raise PermissionDenied("Only the requester can cancel the request.")
    if req.status not in (S.DRAFT, S.RETURNED) + tuple(FundsRequest.PENDING):
        raise ValidationError("A request that is being paid cannot be cancelled – contact Finance.")
    req.status = S.CANCELLED
    req.save()
    _record(req, "Requester", "CANCELLED", user, reason, AuditLog.Action.VOID)
    return req


@transaction.atomic
def remind(user, req, message=""):
    """The requester (or their head) nudges whoever is holding the request."""
    if not (req.requested_by_id == user.pk or (user.is_head and user.department == req.department)):
        raise PermissionDenied("Only the requester or their head of department can send a reminder.")
    if not req.is_open:
        raise ValidationError("This request is not waiting for anyone.")
    if req.last_reminder_at and timezone.now() - req.last_reminder_at < REMINDER_COOLDOWN:
        nxt = timezone.localtime(req.last_reminder_at + REMINDER_COOLDOWN).strftime("%d %b %H:%M")
        raise ValidationError(f"A reminder was already sent. You can send another after {nxt}.")
    label, people = current_holder(req)
    if not people:
        raise ValidationError("Nobody is holding this request right now.")
    days = req.days_waiting
    body = (f"{user.get_full_name() or user.username} is asking about {req.reference} ({req.title}, {req.currency} {req.total:,.2f}). "
            f"It has been with you for {days} day(s)." + (f" Message: {message}" if message else ""))
    _tell(people, f"Reminder: request {req.reference} is waiting for you", body, req)
    req.last_reminder_at = timezone.now()
    req.save(update_fields=["last_reminder_at", "updated_at"])
    _record(req, label, "REMINDER", user, message or f"Reminder sent after {days} day(s).")
    return req


@transaction.atomic
def confirm_purchase(user, req, note=""):
    """After approval: the goods / service were bought – with the invoice or delivery note attached Finance may pay."""
    from . import attachments as att
    from .models import Attachment

    if req.status != S.PENDING_CONFIRMATION:
        raise ValidationError("This request is not waiting for the purchase to be confirmed.")
    if not (req.requested_by_id == user.pk or user.has_cap("procurement.order")):
        raise PermissionDenied("Only the requester or Procurement can confirm the purchase.")
    if not att.for_object("funds", req).filter(kind__in=[Attachment.Kind.INVOICE, Attachment.Kind.DELIVERY]).exists():
        raise ValidationError("Attach the invoice or delivery note first.")
    req.purchase_confirmed_by, req.purchase_confirmed_at, req.confirmation_note = user, timezone.now(), note[:255]
    req.save()
    _record(req, "Purchase confirmed", "CONFIRMED", user, note)
    from finance.services import users_with_cap

    _move_to(req, S.PENDING_PAYMENT, user)
    _tell(users_with_cap("voucher.prepare", Department.FINANCE), f"Request {req.reference} – purchase confirmed, prepare payment",
          f"Pay {req.payee_name or req.requested_by.get_full_name()} {req.currency} {req.total:,.2f} for: {req.title}. Invoice attached.", req)
    return req


@transaction.atomic
def prepare_payment(user, req, *, method=None, budget_line=None):
    """Finance turns the approved request into a payment voucher, which then
    goes through the voucher approvals (check, Treasurer, CEO if large, pay)."""
    from finance import services as fin
    from finance.models import PaymentVoucher

    fin._require(user, "voucher.prepare")
    if req.requested_by_id == user.pk:
        raise PermissionDenied("Segregation of duties: someone else in Finance must prepare the payment of your own request.")
    if req.status != S.PENDING_PAYMENT:
        raise ValidationError("The request is not waiting for payment.")
    category = PaymentVoucher.Category.ALLOWANCES if req.request_type in ("TRAVEL", "ADVANCE") else PaymentVoucher.Category.OTHER
    voucher = fin.prepare_voucher(
        user, category=category, payee_name=req.payee_name or req.requested_by.get_full_name() or req.requested_by.username,
        department=req.department, description=f"{req.reference}: {req.get_request_type_display()} – {req.title}",
        currency=req.currency, amount=req.total, method=method or req.payment_method, budget_line=budget_line or req.budget_line,
    )
    req.voucher = voucher
    _move_to(req, S.PAYMENT_PROCESSING, user)
    _record(req, "Payment voucher", "PREPARED", user, voucher.number)
    _tell([req.requested_by], f"Payment for {req.reference} is being processed",
          f"Payment voucher {voucher.number} has been prepared and is going through payment approval.", req)
    return voucher


def voucher_changed(voucher, user):
    """Called by the voucher workflow so the request follows its payment."""
    from finance.models import PaymentVoucher as PV

    for req in FundsRequest.objects.alive().filter(voucher=voucher, status=S.PAYMENT_PROCESSING):
        if voucher.status == PV.Status.PAID:
            req.status = S.PAID
            req.completed_at = timezone.now()
            req.stage_since = timezone.now()
            req.save()
            _record(req, "Payment", "PAID", user, voucher.payment_reference)
            _tell([req.requested_by], f"Your request {req.reference} has been paid",
                  f"{req.currency} {req.total:,.2f} paid to {voucher.payee_name} by {voucher.get_method_display()} "
                  f"(ref {voucher.payment_reference}). The request is complete.", req)
        elif voucher.status in (PV.Status.REJECTED, PV.Status.CANCELLED):
            req.voucher = None
            req.status = S.PENDING_PAYMENT
            req.stage_since = timezone.now()
            req.save()
            _record(req, "Payment voucher", "REJECTED", user, voucher.rejection_reason)
            _tell([req.requested_by], f"Payment voucher for {req.reference} was rejected",
                  f"{voucher.rejection_reason}. Finance will prepare it again.", req)
        else:
            label, people = _voucher_holders(voucher)
            req.stage_since = timezone.now()
            req.save(update_fields=["stage_since", "updated_at"])
            _tell([req.requested_by], f"Payment for {req.reference}: {voucher.get_status_display().lower()}",
                  f"Next: {label}.", req)


def _waiting(req):
    d = req.days_waiting
    return f"Waiting {d} day{'s' if d != 1 else ''}" if d else "Since today"


def route(req):
    """Rows for the "where is my request" tracker: label, state, who, when, note.
    state: done | current | skipped | waiting | rejected | returned"""
    recs = list(history(req).filter(timestamp__gte=req.submitted_at)) if req.submitted_at else []
    last = {}
    for r in recs:
        last[r.stage] = r
    rows = []
    sub = next((r for r in recs if r.stage == "Requester"), None)
    rows.append({"label": "Submitted by requester", "state": "done" if sub else "current", "who": req.requested_by,
                 "when": sub.timestamp if sub else None, "note": ""})
    for status, label in STAGES:
        r = last.get(label)
        if r and r.decision == "REMINDER":
            r = next((x for x in reversed(recs) if x.stage == label and x.decision != "REMINDER"), None)
        if req.status == status:
            _l, people = current_holder(req)
            rows.append({"label": label, "state": "current", "who": ", ".join(p.get_full_name() or p.username for p in people),
                         "when": req.stage_since, "note": _waiting(req)})
        elif r:
            state = {"APPROVED": "done", "SKIPPED": "skipped", "REJECTED": "rejected", "RETURNED": "returned"}.get(r.decision, "done")
            rows.append({"label": label, "state": state, "who": r.user if state != "skipped" else "—", "when": r.timestamp, "note": r.comment})
        else:
            rows.append({"label": label, "state": "waiting", "who": "", "when": None, "note": ""})
    if req.requires_payment and req.request_type in CONFIRM_TYPES:
        if req.status == S.PENDING_CONFIRMATION:
            _l, people = current_holder(req)
            rows.append({"label": "Purchase confirmed – invoice / delivery note", "state": "current",
                         "who": ", ".join(p.get_full_name() or p.username for p in people), "when": req.stage_since, "note": _waiting(req)})
        elif req.purchase_confirmed_at:
            rows.append({"label": "Purchase confirmed – invoice / delivery note", "state": "done", "who": req.purchase_confirmed_by,
                         "when": req.purchase_confirmed_at, "note": req.confirmation_note})
        else:
            rows.append({"label": "Purchase confirmed – invoice / delivery note", "state": "waiting", "who": "", "when": None, "note": ""})
    if req.requires_payment:
        v = req.voucher
        from finance.models import ApprovalRecord, PaymentVoucher as PV

        vrecs = {r.stage: r for r in ApprovalRecord.for_object(v)} if v else {}
        steps = [("Finance prepares payment voucher", "Preparation", PV.Status.PREPARED),
                 ("Accountant checks the voucher", "Checking (Accountant)", PV.Status.CHECKED),
                 ("Treasurer approves the payment", "Approval (Treasurer)", PV.Status.APPROVED)]
        if v is not None and v.needs_ceo:
            steps.append(("CEO authorises the payment", "Authorisation (CEO)", PV.Status.AUTHORISED))
        steps.append(("Cashier pays – requester notified", "Payment", PV.Status.PAID))
        current_found = False
        for label, stage, _st in steps:
            r = vrecs.get(stage)
            if r:
                rows.append({"label": label, "state": "done" if r.decision != "REJECTED" else "rejected", "who": r.user, "when": r.timestamp,
                             "note": (v.number if stage == "Preparation" else r.comment)})
            elif not current_found and req.status in (S.PENDING_PAYMENT, S.PAYMENT_PROCESSING):
                current_found = True
                _l, people = current_holder(req)
                rows.append({"label": label, "state": "current", "who": ", ".join(p.get_full_name() or p.username for p in people),
                             "when": req.stage_since, "note": _waiting(req)})
            else:
                rows.append({"label": label, "state": "waiting", "who": "", "when": None, "note": ""})
    else:
        rows.append({"label": "Requester notified – complete", "state": "done" if req.status == S.COMPLETED else "waiting", "who": req.requested_by,
                     "when": req.completed_at, "note": ""})
    return rows
