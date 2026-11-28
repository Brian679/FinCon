"""Finance business rules and workflows.

Views, the REST API and the mobile sync engine all call these functions so
the rules (permissions, segregation of duties, audit trail, notifications)
are enforced identically everywhere.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from core import audit, sla
from core.models import AuditLog, Notification, SequenceCounter

ZERO_D = Decimal("0.00")

from .models import (  # noqa: E402
    ApprovalRecord,
    Bill,
    CashUp,
    ClientAccount,
    Licence,
    OnlinePayment,
    PaymentVoucher,
    Property,
    PurchaseOrder,
    Receipt,
    Requisition,
    RevenueHead,
    q2,
)

User = get_user_model()


def _require(user, *caps):
    if not (user and user.is_authenticated and user.has_cap(*caps)):
        audit.log(AuditLog.Action.ACCESS_DENIED, message=f"Needs {', '.join(caps)}", user=user)
        raise PermissionDenied(f"You need one of these permissions: {', '.join(caps)}")


def _record(obj, stage, decision, user, comment=""):
    ApprovalRecord.objects.create(
        content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk),
        stage=stage, decision=decision, user=user, comment=comment,
    )
    action = AuditLog.Action.REJECT if decision.upper().startswith("REJECT") else AuditLog.Action.APPROVE
    audit.log(action, obj, user=user, message=f"{stage}: {decision}. {comment}".strip())


def notify(users, title, body="", link=""):
    for u in {u for u in users if u is not None}:
        Notification.objects.create(recipient=u, title=title, body=body, link=link)


def users_with_cap(cap, department=None):
    qs = User.objects.filter(is_active=True, user_type=User.UserType.STAFF)
    if department:
        qs = qs.filter(department=department)
    return [u for u in qs if u.has_cap(cap)]


# --------------------------------------------------------------------- revenue
@transaction.atomic
def issue_receipt(user, *, revenue_head, amount, payer_name="", account=None, bill=None, currency="USD",
                  method=Receipt.Method.CASH, reference="", bank_account=None, description="",
                  channel=Receipt.Channel.COUNTER, offline_created_at=None, device_id="", receipt_id=None):
    if channel in (Receipt.Channel.COUNTER, Receipt.Channel.FIELD):
        _require(user, "receipt.create")
    amount = q2(amount)
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if bill is not None:
        account = account or bill.account
        if bill.account_id != account.pk:
            raise ValidationError("The bill does not belong to this account.")
        if revenue_head is None or revenue_head.pk != bill.revenue_head_id:
            # Income is always booked to the head of the bill being paid, so reports by revenue head stay correct.
            revenue_head = bill.revenue_head
        if bill.status == Bill.Status.CANCELLED:
            raise ValidationError("This bill has been cancelled.")
    if account is not None and account.status == ClientAccount.Status.CLOSED:
        raise ValidationError("This account is closed.")
    if method != Receipt.Method.CASH and not reference and channel == Receipt.Channel.COUNTER:
        raise ValidationError("A transaction reference is required for non-cash payments.")
    kwargs = {}
    if receipt_id:
        kwargs["id"] = receipt_id
    receipt = Receipt(
        account=account, bill=bill, payer_name=payer_name or (account.name if account else ""),
        revenue_head=revenue_head, description=description or revenue_head.name, currency=currency,
        amount=amount, method=method, reference=reference, bank_account=bank_account, channel=channel,
        received_by=user if user and user.is_authenticated and user.is_staff_member else None,
        offline_created_at=offline_created_at, device_id=device_id, created_by=user, **kwargs,
    )
    if not receipt.payer_name:
        raise ValidationError("Payer name is required for walk-in receipts.")
    receipt.full_clean(exclude=["number", "exchange_rate", "base_amount"])
    receipt.save()
    audit.log(AuditLog.Action.PAYMENT, receipt, user=user,
              message=f"Receipt {receipt.number}: {currency} {amount} via {receipt.get_method_display()} ({receipt.get_channel_display()})")
    if account is not None:
        account.recalculate()
        _maybe_issue_licences(account)
        settle_paid_items(account)
        notify_payment(receipt)
    return receipt


def client_people(account, *extra):
    """Everyone who follows this account on the client app / portal."""
    people = list(account.portal_users.filter(is_active=True)) if account is not None else []
    return [u for u in {*people, *extra} if u is not None]


def notify_payment(receipt, extra_users=()):
    """Tell the shop / stand owner on their phone (app notification + SMS) that the council
    received their payment and what is still owing - wherever the payment was taken."""
    from core.messaging import notify_client

    account = receipt.account
    if account is None:
        return 0
    account.refresh_from_db(fields=["balance"])
    prop = receipt.bill.property if receipt.bill_id and receipt.bill.property_id else None
    what = (f" for farm {prop.stand_number}" if prop.hectares else f" for stand {prop.stand_number}") + (f" ({prop.business_name})" if prop and prop.business_name else "") if prop else ""
    where = {Receipt.Channel.COUNTER: "at the council offices", Receipt.Channel.FIELD: "by a council revenue collector"}.get(receipt.channel, "online")
    left = "Your account is fully paid – nothing owing." if account.balance <= 0 else f"Balance remaining: USD {account.balance:,.2f}."
    body = (f"Receipt {receipt.number}: {receipt.currency} {receipt.amount:,.2f}{what} paid {where} on "
            f"{timezone.localtime(receipt.created_at).strftime('%d %b %Y %H:%M')}. {left}")
    issued = [lic for lic in account.licences.alive().filter(status=Licence.Status.ISSUED, issue_date=timezone.localdate())]
    if issued:
        body += " Licence " + ", ".join(f"{lic.number} ({lic.business_name})" for lic in issued) + " is now issued."
    sms_to = account.phone if receipt.channel in (Receipt.Channel.COUNTER, Receipt.Channel.FIELD) else ""
    return notify_client(users=client_people(account, *extra_users), phone=sms_to, subject=f"Payment received – {account.account_number}",
                         body=body, account_number=account.account_number, sent_by=receipt.received_by, campaign="Payment confirmation",
                         link=f"/portal/receipts/{receipt.pk}/")


@transaction.atomic
def request_void(user, receipt, reason):
    _require(user, "receipt.void_request", "receipt.void_approve")
    if receipt.status != Receipt.Status.VALID:
        raise ValidationError("Only valid receipts can be voided.")
    if not reason:
        raise ValidationError("A reason is required.")
    receipt.status = Receipt.Status.VOID_REQUESTED
    receipt.void_reason = reason
    receipt.void_requested_by = user
    receipt.save()
    _record(receipt, "Void request", "REQUESTED", user, reason)
    notify(users_with_cap("receipt.void_approve", "FINANCE"), f"Void requested: {receipt.number}", reason)
    return receipt


@transaction.atomic
def decide_void(user, receipt, approve: bool, comment=""):
    _require(user, "receipt.void_approve")
    if receipt.status != Receipt.Status.VOID_REQUESTED:
        raise ValidationError("There is no pending void request on this receipt.")
    if receipt.void_requested_by_id == user.pk or receipt.received_by_id == user.pk:
        raise PermissionDenied("Segregation of duties: you cannot approve a void on a receipt you issued or requested.")
    if approve:
        receipt.status = Receipt.Status.VOIDED
        receipt.voided_by = user
        receipt.voided_at = timezone.now()
        audit.log(AuditLog.Action.VOID, receipt, user=user, message=f"Receipt voided: {receipt.void_reason}. {comment}")
    else:
        receipt.status = Receipt.Status.VALID
    receipt.save()
    _record(receipt, "Void approval", "APPROVED" if approve else "REJECTED", user, comment)
    if receipt.account:
        receipt.account.recalculate()
        if approve:
            _withdraw_unpaid_licences(receipt.account, user, receipt)
            settle_paid_items(receipt.account)
    notify([receipt.void_requested_by], f"Void {'approved' if approve else 'rejected'}: {receipt.number}", comment)
    return receipt


@transaction.atomic
def create_bill(user, *, account, revenue_head, amount, description="", due_date=None, period="", property=None):
    _require(user, "billing.run", "licence.manage")
    bill = Bill.objects.create(
        account=account, revenue_head=revenue_head, amount=q2(amount), property=property, period=period,
        description=description or revenue_head.name, due_date=due_date or timezone.localdate() + timezone.timedelta(days=30),
        created_by=user,
    )
    account.recalculate()
    return bill


@transaction.atomic
def cancel_bill(user, bill, reason):
    _require(user, "billing.run")
    if bill.amount_paid > 0:
        raise ValidationError("A bill with payments allocated cannot be cancelled. Void the receipts or raise a credit.")
    bill.status = Bill.Status.CANCELLED
    bill.cancel_reason = reason
    bill.save()
    audit.log(AuditLog.Action.VOID, bill, user=user, message=f"Bill cancelled: {reason}")
    bill.account.recalculate()
    return bill


def run_rates_billing(user, year: int, month: int, revenue_head=None):
    """Raise the monthly rates bill for every active property. Idempotent per period."""
    _require(user, "billing.run")
    revenue_head = revenue_head or RevenueHead.objects.get(code="RATES")
    period = f"{year:04d}-{month:02d}"
    due = date(year, month, monthrange(year, month)[1])
    created = skipped = 0
    for prop in Property.objects.alive().filter(is_active=True, monthly_rates__gt=0, account__status=ClientAccount.Status.ACTIVE).select_related("account"):
        exists = Bill.objects.alive().filter(account=prop.account, property=prop, revenue_head=revenue_head, period=period).exclude(
            status=Bill.Status.CANCELLED).exists()
        if exists:
            skipped += 1
            continue
        Bill.objects.create(account=prop.account, property=prop, revenue_head=revenue_head, period=period,
                            amount=prop.monthly_rates, description=f"Rates {period} - {prop}", due_date=due, created_by=user)
        prop.account.recalculate()
        created += 1
    audit.log(AuditLog.Action.OTHER, user=user, model_label="finance.Bill",
              message=f"Rates billing run for {period}: {created} bills raised, {skipped} already billed")
    return created, skipped


@transaction.atomic
def submit_cashup(user, *, currency, declared_cash, notes=""):
    _require(user, "cashup.submit", "receipt.create")
    receipts = Receipt.objects.alive().filter(received_by=user, cashup__isnull=True, currency=currency, status__in=Receipt.COUNTABLE)
    expected_cash = q2(sum((r.amount for r in receipts if r.method == Receipt.Method.CASH), Decimal(0)))
    expected_other = q2(sum((r.amount for r in receipts if r.method != Receipt.Method.CASH), Decimal(0)))
    cashup = CashUp.objects.create(cashier=user, currency=currency, declared_cash=q2(declared_cash), expected_cash=expected_cash,
                                   expected_other=expected_other, variance=q2(declared_cash) - expected_cash, notes=notes, created_by=user)
    receipts.update(cashup=cashup, updated_at=timezone.now())
    if cashup.variance != 0:
        notify(users_with_cap("cashup.verify", "FINANCE"), f"Cash-up variance {currency} {cashup.variance}",
               f"{user} declared {declared_cash}, expected {expected_cash}")
    return cashup


@transaction.atomic
def verify_cashup(user, cashup, ok: bool, notes=""):
    _require(user, "cashup.verify")
    if cashup.cashier_id == user.pk:
        raise PermissionDenied("You cannot verify your own cash-up.")
    cashup.status = CashUp.Status.VERIFIED if ok else CashUp.Status.QUERIED
    cashup.verified_by = user
    cashup.verified_at = timezone.now()
    if notes:
        cashup.notes = (cashup.notes + "\n" + notes).strip()
    cashup.save()
    _record(cashup, "Cash-up verification", "VERIFIED" if ok else "QUERIED", user, notes)
    return cashup


# -------------------------------------------------------------------- licences
@transaction.atomic
def apply_licence(user, *, account, licence_type, business_name, premises, business_activity="", ward=None, renewal_of=None, licence_id=None,
                  property=None):
    if user.is_client:
        if not user.client_accounts.filter(pk=account.pk).exists():
            raise PermissionDenied("This account is not linked to your profile.")
    else:
        _require(user, "licence.manage")
    head = RevenueHead.objects.filter(code=f"LIC-{licence_type}").first() or RevenueHead.objects.filter(category=RevenueHead.Category.LICENCE).first()
    if property is None and licence_type == Licence.LicenceType.SHOP:
        # a shop licence belongs to the shop's stand: link it when the account has exactly one business stand
        stands = account.properties.alive().exclude(business_name="")
        property = stands.first() if stands.count() == 1 else None
    automatic = licence_type in AUTO_ISSUE_LICENCES
    needs_inspection = not automatic and licence_type in (Licence.LicenceType.HEALTH, Licence.LicenceType.LIQUOR)
    kwargs = {"id": licence_id} if licence_id else {}
    lic = Licence.objects.create(
        licence_type=licence_type, account=account, business_name=business_name, premises=premises,
        business_activity=business_activity, ward=ward or account.ward, applicant=user, revenue_head=head, property=property,
        fee=head.default_amount if head else 0, renewal_of=renewal_of, created_by=user,
        status=Licence.Status.APPROVED if automatic else Licence.Status.INSPECTION if needs_inspection else Licence.Status.APPLIED,
        due_at=sla.due_from_standard("process-applications"), **kwargs,
    )
    if automatic:
        # No approvals: the fee is billed straight away and the licence is issued by itself once everything is paid.
        if lic.fee and lic.fee > 0:
            lic.bill = Bill.objects.create(account=account, property=property, revenue_head=head, amount=lic.fee,
                                           description=f"{lic.get_licence_type_display()} {lic.number} - {lic.business_name}",
                                           due_date=timezone.localdate() + timezone.timedelta(days=30), created_by=user)
            lic.save(update_fields=["bill", "updated_at"])
        audit.log(AuditLog.Action.CREATE, lic, user=user, message="Licence fee billed – issued automatically when fully paid")
        account.recalculate()
        _maybe_issue_licences(account)
        lic.refresh_from_db()
        if lic.status == Licence.Status.APPROVED:
            notify(client_people(account, user if user.is_client else None), f"Licence {lic.number}: pay to receive it",
                   licence_dues_message(lic))
    elif needs_inspection:
        notify(users_with_cap("licence.inspect"), f"Inspection required: {lic.business_name}", lic.premises)
    else:
        notify(users_with_cap("licence.approve", "FINANCE"), f"Licence application: {lic.business_name}")
    return lic


# Licences issued automatically as soon as everything is paid – no inspection or Treasurer approval.
# Health certificates and liquor recommendations still need an inspection / council decision.
AUTO_ISSUE_LICENCES = (Licence.LicenceType.SHOP, Licence.LicenceType.HAWKER, Licence.LicenceType.BUSINESS,
                       Licence.LicenceType.TRANSPORT, Licence.LicenceType.ADVERT)


def licence_outstanding(lic):
    """What must still be paid before this licence is issued: [(label, amount)].

    The licence fee always; for a shop also every unpaid lease (rent) and levy bill on the shop."""
    out = []
    if lic.bill_id and lic.bill.status not in (Bill.Status.PAID, Bill.Status.CANCELLED):
        out.append(("Licence fee", lic.bill.outstanding))
    if lic.licence_type == Licence.LicenceType.SHOP:
        dues = Bill.objects.alive().filter(status__in=[Bill.Status.UNPAID, Bill.Status.PART_PAID],
                                           revenue_head__category__in=[RevenueHead.Category.RENT, RevenueHead.Category.LEVY])
        dues = dues.filter(property=lic.property) if lic.property_id else dues.filter(account=lic.account)
        for cat, label in ((RevenueHead.Category.RENT, "Lease / rent"), (RevenueHead.Category.LEVY, "Levy")):
            amt = sum((b.outstanding for b in dues if b.revenue_head.category == cat), Decimal(0))
            if amt > 0:
                out.append((label, q2(amt)))
    return out


def licence_dues_message(lic):
    owing = licence_outstanding(lic)
    if not owing:
        return "Fully paid."
    parts = ", ".join(f"{label} USD {amt:,.2f}" for label, amt in owing)
    return f"{lic.business_name}: still to pay {parts}. The licence is issued automatically as soon as everything is paid."


@transaction.atomic
def inspect_licence(user, lic, passed: bool, notes):
    _require(user, "licence.inspect")
    if lic.status != Licence.Status.INSPECTION:
        raise ValidationError("This application is not awaiting inspection.")
    lic.status = Licence.Status.INSPECTED if passed else Licence.Status.FAILED
    lic.inspected_by = user
    lic.inspection_notes = notes
    lic.save()
    _record(lic, "Inspection", "PASSED" if passed else "FAILED", user, notes)
    notify([lic.applicant], f"Inspection {'passed' if passed else 'failed'}: {lic.business_name}", notes)
    if passed:
        notify(users_with_cap("licence.approve", "FINANCE"), f"Licence ready for approval: {lic.business_name}")
    return lic


@transaction.atomic
def decide_licence(user, lic, approve: bool, reason="", fee=None):
    _require(user, "licence.approve")
    if lic.status not in (Licence.Status.APPLIED, Licence.Status.INSPECTED):
        raise ValidationError("This application is not ready for a decision.")
    if not approve:
        lic.status = Licence.Status.REJECTED
        lic.rejection_reason = reason
        lic.save()
        _record(lic, "Licence decision", "REJECTED", user, reason)
        notify(client_people(lic.account, lic.applicant), f"Licence application rejected: {lic.business_name}", reason)
        return lic
    if fee is not None:
        lic.fee = q2(fee)
    lic.approved_by = user
    lic.status = Licence.Status.APPROVED
    if lic.fee and lic.fee > 0:
        lic.bill = Bill.objects.create(account=lic.account, revenue_head=lic.revenue_head, amount=lic.fee,
                                       description=f"{lic.get_licence_type_display()} {lic.number} - {lic.business_name}",
                                       due_date=timezone.localdate() + timezone.timedelta(days=30), created_by=user)
    lic.save()
    _record(lic, "Licence decision", "APPROVED", user, reason)
    lic.account.recalculate()
    _maybe_issue_licences(lic.account)
    lic.refresh_from_db()
    if lic.status == Licence.Status.APPROVED:
        notify(client_people(lic.account, lic.applicant), f"Licence approved - please pay ${lic.fee}",
               f"{lic.business_name}. Pay bill {lic.bill.number if lic.bill else ''} in the app or at the council offices to receive your licence.")
    return lic


def _maybe_issue_licences(account):
    """Issue approved licences as soon as everything is paid: the fee, and for a shop its lease and levy too."""
    lics = Licence.objects.alive().filter(status=Licence.Status.APPROVED).filter(
        models.Q(account=account) | models.Q(property__account=account) | models.Q(property__bills__account=account)).distinct()
    for lic in lics.select_related("bill", "property"):
        account = lic.account
        Licence.objects.filter(pk=lic.pk).update(updated_at=timezone.now())   # apps re-sync "still to pay"
        if not licence_outstanding(lic):
            today = timezone.localdate()
            lic.status = Licence.Status.ISSUED
            lic.issue_date = today
            lic.expiry_date = date(today.year, 12, 31)
            lic.save()
            audit.log(AuditLog.Action.APPROVE, lic, message="Licence issued on payment of fee")
            notify(client_people(account, lic.applicant), f"Licence issued: {lic.number}", f"{lic.business_name} - valid until {lic.expiry_date}")


def expire_licences():
    today = timezone.localdate()
    qs = Licence.objects.alive().filter(status=Licence.Status.ISSUED, expiry_date__lt=today)
    n = 0
    for lic in qs:
        lic.status = Licence.Status.EXPIRED
        lic.save()
        n += 1
    return n


# ------------------------------------------------------------------ procurement
def _hod_of(department):
    return [u for u in User.objects.filter(is_active=True, department=department) if u.is_head]


@transaction.atomic
def submit_requisition(user, req):
    if req.requested_by_id != user.pk:
        raise PermissionDenied("Only the requester can submit this requisition.")
    if req.status != Requisition.Status.DRAFT:
        raise ValidationError("Only draft requisitions can be submitted.")
    req.recalc_total()
    if req.total <= 0:
        raise ValidationError("Add at least one item before submitting.")
    if user.is_head:
        # A head of department's own requisition goes straight to Finance.
        req.status = Requisition.Status.HOD_APPROVED
        _record(req, "Submission (HOD)", "SUBMITTED", user)
        notify(users_with_cap("requisition.finance_check", "FINANCE"), f"Requisition {req.number} needs funds check")
    else:
        req.status = Requisition.Status.SUBMITTED
        _record(req, "Submission", "SUBMITTED", user)
        notify(_hod_of(req.department), f"Requisition {req.number} awaiting your approval", req.purpose[:120])
    req.save()
    return req


STAGES = {
    # current status: (capability, next status, stage label)
    Requisition.Status.SUBMITTED: ("requisition.hod_approve", Requisition.Status.HOD_APPROVED, "Head of Department"),
    Requisition.Status.HOD_APPROVED: ("requisition.finance_check", Requisition.Status.FINANCE_CHECKED, "Funds check (Accountant)"),
    Requisition.Status.FINANCE_CHECKED: ("requisition.approve", Requisition.Status.APPROVED, "Treasurer approval"),
    Requisition.Status.APPROVED: ("requisition.authorise", Requisition.Status.AUTHORISED, "CEO authorisation"),
}


def requisition_next_action(user, req):
    stage = STAGES.get(req.status)
    if not stage:
        return None
    cap, _next, label = stage
    if req.status == Requisition.Status.APPROVED and not req.needs_ceo:
        return None
    if not user.has_cap(cap):
        return None
    if req.status == Requisition.Status.SUBMITTED and not (user.department == req.department or user.is_ceo):
        return None
    return label


@transaction.atomic
def decide_requisition(user, req, approve: bool, comment=""):
    stage = STAGES.get(req.status)
    if not stage or (req.status == Requisition.Status.APPROVED and not req.needs_ceo):
        raise ValidationError("This requisition is not awaiting a decision.")
    cap, next_status, label = stage
    _require(user, cap)
    if req.status == Requisition.Status.SUBMITTED and user.department != req.department and not user.is_ceo:
        raise PermissionDenied("Only the head of the requesting department can approve at this stage.")
    if req.requested_by_id == user.pk:
        raise PermissionDenied("Segregation of duties: you cannot approve your own requisition.")
    if ApprovalRecord.for_object(req).filter(user=user, decision="APPROVED").exists():
        raise PermissionDenied("Segregation of duties: you have already approved this requisition at another stage.")
    if not approve:
        req.status = Requisition.Status.REJECTED
        req.rejection_reason = comment
        req.save()
        _record(req, label, "REJECTED", user, comment)
        notify([req.requested_by], f"Requisition {req.number} rejected", comment)
        return req
    if req.status == Requisition.Status.HOD_APPROVED and req.budget_line_id:
        available = req.budget_line.available()
        if req.total > available:
            raise ValidationError(f"Insufficient budget on {req.budget_line.vote_code}: available ${available}, requested ${req.total}.")
    req.status = next_status
    req.save()
    _record(req, label, "APPROVED", user, comment)
    if req.status == Requisition.Status.FINANCE_CHECKED:
        notify(users_with_cap("requisition.approve", "FINANCE"), f"Requisition {req.number} awaiting Treasurer approval")
    elif req.status == Requisition.Status.APPROVED and req.needs_ceo:
        notify(users_with_cap("requisition.authorise"), f"Requisition {req.number} (${req.total}) needs CEO authorisation")
    elif req.status == Requisition.Status.HOD_APPROVED:
        notify(users_with_cap("requisition.finance_check", "FINANCE"), f"Requisition {req.number} needs funds check")
    if req.is_ready_for_order:
        notify([req.requested_by] + users_with_cap("procurement.order"), f"Requisition {req.number} approved - ready for purchase order")
    return req


@transaction.atomic
def raise_purchase_order(user, req, supplier, amount=None, expected_delivery=None, notes=""):
    _require(user, "procurement.order")
    if not req.is_ready_for_order:
        raise ValidationError("The requisition has not been fully approved.")
    if supplier.status != supplier.Status.ACTIVE:
        raise ValidationError("The supplier is not active.")
    amount = q2(amount or req.total)
    if amount > req.total:
        raise ValidationError("The order amount cannot exceed the approved requisition total.")
    po = PurchaseOrder.objects.create(requisition=req, supplier=supplier, amount=amount, expected_delivery=expected_delivery,
                                      notes=notes, created_by=user)
    req.status = Requisition.Status.ORDERED
    req.save()
    return po


@transaction.atomic
def receive_goods(user, po, notes=""):
    _require(user, "procurement.order", "voucher.prepare")
    if po.status != PurchaseOrder.Status.ISSUED:
        raise ValidationError("Only issued orders can be received.")
    po.status = PurchaseOrder.Status.DELIVERED
    po.delivered_at = timezone.now()
    po.received_by = user
    if notes:
        po.notes = (po.notes + "\n" + notes).strip()
    po.save()
    _record(po, "Goods received", "RECEIVED", user, notes)
    return po


# --------------------------------------------------------------- expenditure
@transaction.atomic
def prepare_voucher(user, **data):
    _require(user, "voucher.prepare")
    po = data.get("purchase_order")
    if po is not None:
        if po.status != PurchaseOrder.Status.DELIVERED:
            raise ValidationError("Goods/services must be received before payment.")
        data.setdefault("supplier", po.supplier)
        data.setdefault("budget_line", po.requisition.budget_line)
        data.setdefault("department", po.requisition.department)
    supplier = data.get("supplier")
    if supplier is not None:
        if supplier.status != supplier.Status.ACTIVE:
            raise ValidationError("Payments cannot be made to a suspended or blacklisted supplier.")
        data.setdefault("payee_name", supplier.name)
    voucher = PaymentVoucher(prepared_by=user, created_by=user, **data)
    voucher.full_clean(exclude=["number", "exchange_rate", "base_amount", "prepared_by"])
    voucher.save()
    _record(voucher, "Preparation", "PREPARED", user)
    notify(users_with_cap("voucher.check", "FINANCE"), f"Payment voucher {voucher.number} to check", f"{voucher.payee_name} {voucher.currency} {voucher.amount}")
    return voucher


VOUCHER_STAGES = {
    PaymentVoucher.Status.PREPARED: ("voucher.check", PaymentVoucher.Status.CHECKED, "Checking (Accountant)"),
    PaymentVoucher.Status.CHECKED: ("voucher.approve", PaymentVoucher.Status.APPROVED, "Approval (Treasurer)"),
    PaymentVoucher.Status.APPROVED: ("voucher.authorise", PaymentVoucher.Status.AUTHORISED, "Authorisation (CEO)"),
}


def voucher_next_action(user, voucher):
    stage = VOUCHER_STAGES.get(voucher.status)
    if not stage or (voucher.status == PaymentVoucher.Status.APPROVED and not voucher.needs_ceo):
        return None
    return stage[2] if user.has_cap(stage[0]) else None


@transaction.atomic
def decide_voucher(user, voucher, approve: bool, comment=""):
    stage = VOUCHER_STAGES.get(voucher.status)
    if not stage or (voucher.status == PaymentVoucher.Status.APPROVED and not voucher.needs_ceo):
        raise ValidationError("This voucher is not awaiting a decision.")
    cap, next_status, label = stage
    _require(user, cap)
    if voucher.prepared_by_id == user.pk:
        raise PermissionDenied("Segregation of duties: you cannot approve a voucher you prepared.")
    if ApprovalRecord.for_object(voucher).filter(user=user, decision="APPROVED").exists():
        raise PermissionDenied("Segregation of duties: you have already approved this voucher at another stage.")
    if not approve:
        voucher.status = PaymentVoucher.Status.REJECTED
        voucher.rejection_reason = comment
        voucher.save()
        _record(voucher, label, "REJECTED", user, comment)
        notify([voucher.prepared_by], f"Voucher {voucher.number} rejected", comment)
        _funds_follow(voucher, user)
        return voucher
    if voucher.status == PaymentVoucher.Status.PREPARED and voucher.budget_line_id:
        # Funds check excludes this voucher's own commitment.
        available = voucher.budget_line.available() + voucher.base_amount
        if voucher.base_amount > available:
            raise ValidationError(f"Insufficient budget on {voucher.budget_line.vote_code}: available ${available}.")
    voucher.status = next_status
    voucher.save()
    _record(voucher, label, "APPROVED", user, comment)
    if voucher.status == PaymentVoucher.Status.CHECKED:
        notify(users_with_cap("voucher.approve", "FINANCE"), f"Voucher {voucher.number} awaiting Treasurer approval")
    elif voucher.status == PaymentVoucher.Status.APPROVED and voucher.needs_ceo:
        notify(users_with_cap("voucher.authorise"), f"Voucher {voucher.number} (${voucher.base_amount}) needs CEO authorisation")
    if voucher.is_ready_for_payment:
        notify([voucher.prepared_by] + users_with_cap("voucher.pay", "FINANCE"), f"Voucher {voucher.number} ready for payment")
    _funds_follow(voucher, user)
    return voucher


def _funds_follow(voucher, user):
    from workflow.funds import voucher_changed

    voucher_changed(voucher, user)


@transaction.atomic
def pay_voucher(user, voucher, *, bank_account, payment_reference):
    _require(user, "voucher.pay")
    if voucher.funds_requests.filter(requested_by=user).exists():
        raise PermissionDenied("Segregation of duties: you cannot release a payment for your own request.")
    if not voucher.is_ready_for_payment:
        raise ValidationError("This voucher has not been fully approved.")
    if not payment_reference:
        raise ValidationError("Enter the cheque / RTGS / transaction reference.")
    if bank_account.currency != voucher.currency:
        raise ValidationError("Bank account currency does not match the voucher currency.")
    if voucher.method != PaymentVoucher.Method.CASH and bank_account.balance() < voucher.amount:
        raise ValidationError(f"Insufficient funds in {bank_account.name}: balance {bank_account.balance()}.")
    voucher.status = PaymentVoucher.Status.PAID
    voucher.bank_account = bank_account
    voucher.payment_reference = payment_reference
    voucher.paid_at = timezone.now()
    voucher.save()
    _record(voucher, "Payment", "PAID", user, payment_reference)
    audit.log(AuditLog.Action.PAYMENT, voucher, user=user, message=f"Paid {voucher.currency} {voucher.amount} to {voucher.payee_name} ref {payment_reference}")
    if voucher.purchase_order_id:
        po = voucher.purchase_order
        po.status = PurchaseOrder.Status.PAID
        po.save()
    _funds_follow(voucher, user)
    return voucher


# ------------------------------------------------------------ online payments
def start_online_payment(user, *, account, amount, revenue_head=None, bill=None, method="ECOCASH", phone="", channel=Receipt.Channel.PORTAL):
    from .gateway import get_gateway

    if not user.client_accounts.filter(pk=account.pk).exists() and not user.is_staff_member:
        raise PermissionDenied("This account is not linked to your profile.")
    if bill is not None and bill.account_id != account.pk:
        raise PermissionDenied("This bill does not belong to the selected account.")
    revenue_head = revenue_head or (bill.revenue_head if bill else RevenueHead.objects.get(code="RATES"))
    if not revenue_head.payable_online:
        raise ValidationError("This charge cannot be paid online.")
    payment = OnlinePayment.objects.create(account=account, user=user, bill=bill, revenue_head=revenue_head, amount=q2(amount),
                                           method=method, phone=phone, channel=channel, provider=settings.PAYMENT_GATEWAY, created_by=user)
    get_gateway().initiate(payment)
    return payment


@transaction.atomic
def confirm_online_payment(payment, provider_reference=""):
    """Called by the gateway callback / poll when the provider confirms payment.

    The receipt is issued immediately (charter: payment confirmation - immediate).
    """
    payment = OnlinePayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == OnlinePayment.Status.PAID:
        return payment.receipt
    receipt = _confirm_bulk(payment, provider_reference) if payment.bills.exists() else issue_receipt(
        payment.user, revenue_head=payment.revenue_head, amount=payment.amount, account=payment.account, bill=payment.bill,
        currency=payment.currency, method=Receipt.Method.ONLINE, reference=provider_reference or payment.reference,
        channel=payment.channel, payer_name=payment.account.name, description=f"Online payment {payment.reference}",
    )
    payment.status = OnlinePayment.Status.PAID
    payment.provider_reference = provider_reference
    payment.receipt = receipt
    payment.paid_at = timezone.now()
    payment.save()
    if payment.user_id and not payment.account.portal_users.filter(pk=payment.user_id).exists():
        notify([payment.user], f"Payment received - receipt {receipt.number}", f"{payment.currency} {payment.amount} for {payment.account.account_number}")
    # Revenue staff see online money arrive straight away (it is already in the cashbook and on the area board).
    notify(users_with_cap("cashup.verify", "FINANCE"), f"Online payment {payment.currency} {payment.amount:,.2f} – {payment.account.name}",
           f"Receipt {receipt.number}, account {payment.account.account_number}", f"/staff/finance/receipts/{receipt.pk}/")
    return receipt


# ------------------------------------------------------- levies & leases
def run_levy_billing(user, revenue_head, year: int, *, area=None, land_use=None, amount=None):
    """Raise an annual levy on every matching property. Idempotent per year.

    Stands, households and shops pay a flat levy (development levy, unit tax ...); farms pay the farm levy,
    which is charged per hectare (e.g. $5 x 40 ha = $200), and are left out of the flat levies."""
    _require(user, "billing.run")
    amount = q2(amount or revenue_head.default_amount)
    if amount <= 0:
        raise ValidationError("Set an amount for the levy.")
    period = f"{year:04d}"
    props = Property.objects.alive().filter(is_active=True, account__status=ClientAccount.Status.ACTIVE).select_related("account")
    if revenue_head.per_hectare:
        props = props.filter(hectares__gt=0)
    else:
        props = props.filter(models.Q(hectares__isnull=True) | models.Q(hectares=0))
    if area is not None:
        props = props.filter(area=area)
    if land_use:
        props = props.filter(land_use=land_use)
    created = skipped = 0
    for prop in props:
        if Bill.objects.alive().filter(account=prop.account, property=prop, revenue_head=revenue_head, period=period).exclude(status=Bill.Status.CANCELLED).exists():
            skipped += 1
            continue
        charge, what = amount, f"{revenue_head.name} {year} – {prop}"
        if revenue_head.per_hectare:
            charge = q2(amount * prop.hectares)
            what = f"{revenue_head.name} {year} – {prop} ({prop.hectares.normalize():f} ha × ${amount:,.2f})"
        Bill.objects.create(account=prop.account, property=prop, revenue_head=revenue_head, period=period, amount=charge,
                            description=what, due_date=date(year, 3, 31) if date(year, 3, 31) > timezone.localdate() else timezone.localdate() + timezone.timedelta(days=30),
                            created_by=user)
        prop.account.recalculate()
        created += 1
    audit.log(AuditLog.Action.OTHER, user=user, model_label="finance.Bill",
              message=f"{revenue_head.name} {year} levy run{f' for {area}' if area else ''}: {created} raised, {skipped} already billed")
    return created, skipped


def run_lease_billing(user, year: int, month: int):
    """Raise the monthly rent bill for every current lease. Idempotent per month."""
    from .models import Lease

    _require(user, "billing.run")
    period = f"{year:04d}-{month:02d}"
    first, last = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    created = skipped = 0
    for lease in Lease.objects.alive().filter(status=Lease.Status.ACTIVE, start_date__lte=last, end_date__gte=first).select_related("lessee", "premises"):
        head = RevenueHead.objects.get(code="RENT")
        if Bill.objects.alive().filter(account=lease.lessee, property=lease.premises, revenue_head=head, period=period).exclude(status=Bill.Status.CANCELLED).exists():
            skipped += 1
            continue
        Bill.objects.create(account=lease.lessee, property=lease.premises, revenue_head=head, period=period, amount=lease.monthly_rent,
                            description=f"Rent {period} – {lease.premises} ({lease.number})", due_date=first + timezone.timedelta(days=6), created_by=user)
        lease.lessee.recalculate()
        created += 1
    audit.log(AuditLog.Action.OTHER, user=user, model_label="finance.Lease", message=f"Lease billing {period}: {created} raised, {skipped} already billed")
    return created, skipped


@transaction.atomic
def create_lease(user, **data):
    from .models import Lease

    _require(user, "leases.manage")
    premises = data["premises"]
    if Lease.objects.alive().filter(premises=premises, status=Lease.Status.ACTIVE, end_date__gte=data.get("start_date") or timezone.localdate()).exists():
        raise ValidationError("These premises already have an active lease.")
    lease = Lease(created_by=user, **data)
    lease.full_clean(exclude=["number"])
    lease.save()
    if not premises.is_council_owned:
        premises.is_council_owned = True
        premises.save(update_fields=["is_council_owned", "updated_at"])
    if lease.deposit and lease.deposit > 0:
        Bill.objects.create(account=lease.lessee, property=premises, revenue_head=RevenueHead.objects.get(code="RENT"), amount=lease.deposit,
                            description=f"Lease deposit {lease.number}", due_date=lease.start_date, created_by=user)
        lease.lessee.recalculate()
    return lease


# ------------------------------------------------- shop / stand compliance
def property_compliance(prop, year=None):
    """Paid / unpaid position of one stand or shop for the dashboard and reminders."""
    from .models import Lease

    year = year or timezone.localdate().year
    today = timezone.localdate()
    bills = Bill.objects.alive().filter(property=prop).exclude(status__in=[Bill.Status.CANCELLED, Bill.Status.PAID])
    owing = {"rates": ZERO_D, "levies": ZERO_D, "rent": ZERO_D, "other": ZERO_D}
    for b in bills.select_related("revenue_head"):
        cat = b.revenue_head.category
        key = "rates" if cat == RevenueHead.Category.RATES else "levies" if cat == RevenueHead.Category.LEVY else "rent" if cat == RevenueHead.Category.RENT else "other"
        owing[key] += b.outstanding
    total = sum(owing.values(), ZERO_D)
    lic = prop.licences.alive().order_by("-created_at").first() if hasattr(prop, "licences") else None
    needs_licence = prop.land_use in (Property.LandUse.COMMERCIAL, Property.LandUse.INDUSTRIAL) or bool(prop.business_name)
    if lic is None:
        licence = "NONE" if needs_licence else "N/A"
    elif lic.status == Licence.Status.ISSUED and lic.expiry_date and lic.expiry_date >= today:
        licence = "VALID"
    elif lic.status == Licence.Status.APPROVED:
        licence = "UNPAID"
    elif lic.status in (Licence.Status.APPLIED, Licence.Status.INSPECTION, Licence.Status.INSPECTED):
        licence = "PROCESSING"
    else:
        licence = "EXPIRED" if lic.status in (Licence.Status.EXPIRED, Licence.Status.ISSUED) else "NONE"
    lease = Lease.objects.alive().filter(premises=prop, status=Lease.Status.ACTIVE).first()
    ok = total <= 0 and licence in ("VALID", "N/A")
    return {
        "property": prop, "account": prop.account, "owing": owing, "total": total, "licence": licence, "licence_obj": lic,
        "lease": lease, "registered": prop.account.portal_users.exists(), "ok": ok,
    }


LICENCE_TEXT = {"NONE": "no shop licence on record", "UNPAID": "licence approved but fee not paid", "EXPIRED": "licence expired",
                "PROCESSING": "licence application in progress", "VALID": "licence valid", "N/A": ""}


def send_compliance_reminders(user, properties, *, campaign="", extra=""):
    """Send each owner / shop owner their position by app notification and SMS,
    and invite those not yet registered to create an online account."""
    from django.conf import settings as dj

    from core.messaging import notify_client

    _require(user, "reminders.send")
    site = dj.PUBLIC_SITE_URL or "the Chipinge RDC app"
    sent = 0
    for prop in properties:
        c = property_compliance(prop)
        acc = prop.account
        if c["ok"]:
            continue
        parts = []
        if c["total"] > 0:
            parts.append(f"you owe USD {c['total']:.2f}")
        if c["licence"] in ("NONE", "UNPAID", "EXPIRED"):
            parts.append(LICENCE_TEXT[c["licence"]])
        body = (f"Dear {acc.name}, account {acc.account_number}, {prop.business_name or 'stand ' + prop.stand_number} "
                f"({prop.area.name if prop.area else prop.location}): " + "; ".join(parts) +
                ". Pay with EcoCash/OneMoney in the Chipinge RDC app or at council offices.")
        if not c["registered"]:
            body += f" Register free on {site} with account number {acc.account_number} to receive bills and pay online."
        if extra:
            body += " " + extra
        sent += notify_client(users=list(acc.portal_users.all()), phone=acc.phone, email=acc.email, subject="Chipinge RDC payment reminder",
                              body=body, account_number=acc.account_number, sent_by=user, campaign=campaign or "Compliance reminder")
    audit.log(AuditLog.Action.OTHER, user=user, model_label="core.MessageLog", message=f"Reminders sent ({campaign}): {sent} message(s)")
    return sent


def broadcast(user, accounts, subject, body, campaign=""):
    from core.messaging import notify_client

    _require(user, "reminders.send")
    sent = 0
    for acc in accounts:
        sent += notify_client(users=list(acc.portal_users.all()), phone=acc.phone, subject=subject, body=body,
                              account_number=acc.account_number, sent_by=user, campaign=campaign or subject)
    audit.log(AuditLog.Action.OTHER, user=user, model_label="core.MessageLog", message=f"Broadcast '{subject}': {sent} message(s)")
    return sent


# --------------------------------------------------------- register import
IMPORT_COLUMNS = ["area", "ward", "stand_number", "owner_name", "account_type", "phone", "id_number", "email", "land_use",
                  "business_name", "monthly_rates", "valuation", "council_owned", "hectares"]


@transaction.atomic
def import_register(user, rows):
    """Bulk-load stands / shops and their owners (e.g. every stand in the district).

    ``rows`` are dicts with IMPORT_COLUMNS. Existing stands are updated, new
    ones created; owners are matched by ID number, then phone + name."""
    from .models import TradingArea

    _require(user, "accounts.manage")
    stats = {"areas": 0, "accounts": 0, "properties_new": 0, "properties_updated": 0, "errors": []}
    for i, row in enumerate(rows, start=2):
        row = {k: (str(v).strip() if v is not None else "") for k, v in row.items()}
        try:
            if not row.get("stand_number") or not row.get("area") or not row.get("owner_name"):
                raise ValidationError("area, stand_number and owner_name are required")
            ward = int(row["ward"]) if row.get("ward") else None
            area, created = TradingArea.objects.get_or_create(name=row["area"], defaults={"ward": ward, "created_by": user})
            stats["areas"] += int(created)
            acc = None
            if row.get("id_number"):
                acc = ClientAccount.objects.alive().filter(id_number__iexact=row["id_number"]).first()
            if acc is None and row.get("phone"):
                acc = ClientAccount.objects.alive().filter(phone=row["phone"], name__iexact=row["owner_name"]).first()
            if acc is None:
                acc = ClientAccount.objects.create(name=row["owner_name"], account_type=(row.get("account_type") or "IND").upper()[:5],
                                                   phone=row.get("phone", ""), id_number=row.get("id_number", ""), email=row.get("email", ""),
                                                   ward=ward or area.ward, created_by=user)
                stats["accounts"] += 1
            land_use = (row.get("land_use") or "COM").upper()[:4]
            if land_use not in Property.LandUse.values:
                raise ValidationError(f"land_use must be one of {', '.join(Property.LandUse.values)}")
            defaults = dict(account=acc, area=area, ward=ward or area.ward, land_use=land_use, business_name=row.get("business_name", ""),
                            monthly_rates=q2(row.get("monthly_rates") or 0), valuation=q2(row.get("valuation") or 0),
                            is_council_owned=row.get("council_owned", "").lower() in ("1", "yes", "y", "true"),
                            hectares=q2(row["hectares"]) if row.get("hectares") else None)
            if defaults["hectares"]:
                defaults["land_use"] = Property.LandUse.AGRICULTURAL
            prop = Property.objects.filter(location=area.name, stand_number=row["stand_number"]).first()
            if prop is None:
                Property.objects.create(location=area.name, stand_number=row["stand_number"], created_by=user, **defaults)
                stats["properties_new"] += 1
            else:
                for k, v in defaults.items():
                    setattr(prop, k, v)
                prop.save()
                stats["properties_updated"] += 1
        except (ValidationError, ValueError, ArithmeticError) as exc:
            msg = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            stats["errors"].append(f"Row {i}: {msg}")
    if stats["errors"] and not (stats["properties_new"] or stats["properties_updated"]):
        transaction.set_rollback(True)
    audit.log(AuditLog.Action.OTHER, user=user, model_label="finance.Property",
              message=f"Register import: {stats['properties_new']} new stands, {stats['properties_updated']} updated, {stats['accounts']} new accounts, {len(stats['errors'])} errors")
    return stats


# ------------------------------------------------------- account claims
def _digits(s):
    import re

    return re.sub(r"\D", "", s or "")[-9:]


@transaction.atomic
def submit_claim(user, *, stand_number, area=None, location="", business_name="", id_number="", phone="", claim_type="OWNER", notes="", claim_id=None):
    from .models import AccountClaim

    if not user.is_client:
        raise PermissionDenied("Only client accounts can claim a stand.")
    stand_number = stand_number.strip()
    if not stand_number:
        raise ValidationError("Enter the stand number.")
    qs = Property.objects.alive().filter(stand_number__iexact=stand_number).select_related("account")
    if area is not None:
        qs = qs.filter(area=area)
    elif location:
        qs = qs.filter(location__icontains=location.strip())
    prop = qs.first() if qs.count() == 1 else None
    if claim_type not in AccountClaim.ClaimType.values:
        raise ValidationError("Choose how you are connected to this stand.")
    kwargs = {"id": claim_id} if claim_id else {}
    claim = AccountClaim.objects.create(user=user, stand_number=stand_number, area=area, location=location, business_name=business_name,
                                        id_number=id_number or user.national_id, phone=phone or user.phone, claim_type=claim_type, notes=notes,
                                        matched_property=prop, created_by=user, **kwargs)
    if prop is not None and claim_type != AccountClaim.ClaimType.RENT:   # renting is always checked by the council
        acc = prop.account
        phone_ok = acc.phone and len(_digits(claim.phone)) >= 9 and _digits(acc.phone) == _digits(claim.phone)
        id_ok = acc.id_number and claim.id_number and acc.id_number.replace("-", "").replace(" ", "").upper() == claim.id_number.replace("-", "").replace(" ", "").upper()
        if phone_ok or id_ok:
            acc.portal_users.add(user)
            claim.status, claim.account, claim.decided_at = AccountClaim.Status.APPROVED, acc, timezone.now()
            claim.decision_note = "Verified automatically (details match the council register)."
            claim.save()
            notify([user], f"Stand {prop.stand_number} linked to your account", f"Account {acc.account_number}. Your bills and licences now appear in the app.")
            audit.log(AuditLog.Action.APPROVE, claim, user=user, message="Claim auto-approved: details matched register")
            return claim
    notify(users_with_cap("claims.review", "FINANCE"), f"Stand claim to verify: {claim.reference}",
           f"{user.get_full_name()} – stand {stand_number} {area or location}")
    return claim


@transaction.atomic
def decide_claim(user, claim, approve: bool, *, account=None, note="", create_account=False, monthly_rates=None, land_use="COM"):
    """Approve by linking to an existing account (or the matched stand's owner),
    or by registering a new account and stand from the claim's details."""
    from .models import AccountClaim

    _require(user, "claims.review")
    if claim.status != AccountClaim.Status.PENDING:
        raise ValidationError("This claim has already been decided.")
    claim.decided_by, claim.decided_at, claim.decision_note = user, timezone.now(), note
    if not approve:
        claim.status = AccountClaim.Status.REJECTED
        claim.save()
        _record(claim, "Stand claim", "REJECTED", user, note)
        notify([claim.user], f"Stand claim {claim.reference} not approved", note or "Please visit the council offices with proof of ownership.")
        return claim
    if claim.claim_type == AccountClaim.ClaimType.RENT:
        return _approve_tenancy(user, claim, note)
    if account is None and claim.matched_property is not None:
        account = claim.matched_property.account
    if account is None:
        if not create_account:
            raise ValidationError("Choose the account to link, or register a new account for this stand.")
        u = claim.user
        account = ClientAccount.objects.create(name=claim.business_name if claim.claim_type == "SHOP" and claim.business_name else u.get_full_name(),
                                               account_type="BUS" if claim.claim_type == "SHOP" else "IND", phone=claim.phone, id_number=claim.id_number,
                                               email=u.email, ward=(claim.area.ward if claim.area else u.ward), created_by=user)
        Property.objects.create(account=account, area=claim.area, location=claim.area.name if claim.area else claim.location, stand_number=claim.stand_number,
                                business_name=claim.business_name, ward=account.ward, land_use=land_use, monthly_rates=q2(monthly_rates or 0), created_by=user)
    account.portal_users.add(claim.user)
    claim.account = account
    claim.status = AccountClaim.Status.APPROVED
    claim.save()
    _record(claim, "Stand claim", "APPROVED", user, note)
    notify([claim.user], f"Stand {claim.stand_number} approved and linked", f"Account {account.account_number}. Your bills, payments and licences are now in the app.")
    return claim


def client_own_account(user, *, created_by=None):
    """The resident's own council account (opened from their profile if they have none)."""
    acc = user.client_accounts.alive().filter(Q(id_number__iexact=user.national_id) if user.national_id else Q(pk__isnull=False)).first() \
        or user.client_accounts.alive().first()
    if acc is None and user.national_id:
        acc = ClientAccount.objects.alive().filter(id_number__iexact=user.national_id).first()
    if acc is None:
        acc = ClientAccount.objects.create(name=user.get_full_name() or user.username, phone=user.phone, id_number=user.national_id or "",
                                           email=user.email, ward=user.ward, created_by=created_by or user)
    acc.portal_users.add(user)
    return acc


def _approve_tenancy(user, claim, note):
    """A renter: linked to the stand as a tenant with their OWN account – never to the owner's account."""
    from .models import AccountClaim, Tenancy

    prop = claim.matched_property
    if prop is None:
        raise ValidationError("The stand is not in the council register yet – register it under its owner first, then approve the tenancy.")
    tenant = client_own_account(claim.user, created_by=user)
    Tenancy.objects.filter(property=prop, tenant=tenant, is_active=True).update(is_active=False, end_date=timezone.localdate())
    Tenancy.objects.create(property=prop, tenant=tenant, user=claim.user, business_name=claim.business_name, claim=claim, created_by=user)
    claim.account, claim.status = tenant, AccountClaim.Status.APPROVED
    claim.save()
    _record(claim, "Tenancy", "APPROVED", user, note)
    notify([claim.user], f"You are registered as the tenant at stand {prop.stand_number}",
           f"Your own account {tenant.account_number} is used for your licence and payments. The owner's bills stay with the owner.")
    return claim


def end_tenancy(user, tenancy):
    if not (user.has_cap("claims.review") or tenancy.user_id == user.pk):
        raise PermissionDenied("Only the tenant or the council can end a tenancy.")
    tenancy.is_active, tenancy.end_date = False, timezone.localdate()
    tenancy.save()
    return tenancy


def area_overview(year=None):
    """One row per trading area (growth point, business centre, market …): how many
    shops / stands are paid up, how many still owe, how much, licences and app take-up.
    Uses the same rule as the shop board: paid up = nothing owing and a valid licence."""
    from django.db.models import F, Sum

    from .models import TradingArea

    year = year or timezone.localdate().year
    today = timezone.localdate()
    props = list(Property.objects.alive().filter(is_active=True, area__isnull=False).values(
        "id", "area_id", "account_id", "land_use", "business_name"))
    owed = dict(Bill.objects.alive().filter(property__isnull=False).exclude(status__in=[Bill.Status.CANCELLED, Bill.Status.PAID])
                .values("property").annotate(t=Sum(F("amount") - F("amount_paid"))).values_list("property", "t"))
    paid_year = dict(Bill.objects.alive().filter(property__isnull=False, created_at__year=year).exclude(status=Bill.Status.CANCELLED)
                     .values("property").annotate(t=Sum("amount_paid")).values_list("property", "t"))
    latest = {}
    for lic in Licence.objects.alive().filter(property__isnull=False).order_by("created_at").values("property", "status", "expiry_date"):
        latest[lic["property"]] = lic
    on_app = set(ClientAccount.portal_users.through.objects.values_list("clientaccount_id", flat=True))
    rows = {a.pk: {"area": a, "shops": 0, "paid": 0, "owing": 0, "owed": ZERO_D, "no_licence": 0, "not_on_app": 0, "collected": ZERO_D}
            for a in TradingArea.objects.alive().filter(is_active=True)}
    for p in props:
        r = rows.get(p["area_id"])
        if r is None:
            continue
        debt = owed.get(p["id"]) or ZERO_D
        needs = p["land_use"] in (Property.LandUse.COMMERCIAL, Property.LandUse.INDUSTRIAL) or bool(p["business_name"])
        lic = latest.get(p["id"])
        valid = bool(lic and lic["status"] == Licence.Status.ISSUED and lic["expiry_date"] and lic["expiry_date"] >= today)
        licence_ok = valid or not needs
        r["shops"] += 1
        r["owed"] += debt
        r["collected"] += paid_year.get(p["id"]) or ZERO_D
        if debt <= 0 and licence_ok:
            r["paid"] += 1
        else:
            r["owing"] += 1
        if needs and not valid:
            r["no_licence"] += 1
        if p["account_id"] not in on_app:
            r["not_on_app"] += 1
    out = list(rows.values())
    for r in out:
        r["pct"] = round(r["paid"] * 100 / r["shops"]) if r["shops"] else 0
    keys = ("shops", "paid", "owing", "owed", "no_licence", "not_on_app", "collected")
    total = {k: sum((r[k] for r in out), ZERO_D if k in ("owed", "collected") else 0) for k in keys}
    total["pct"] = round(total["paid"] * 100 / total["shops"]) if total["shops"] else 0
    return out, total



def _withdraw_unpaid_licences(account, user, receipt):
    """A licence issued because its fee was paid goes back to "approved – awaiting payment"
    if the payment is voided, so a voided receipt can never leave a valid licence behind."""
    for lic in account.licences.alive().filter(status=Licence.Status.ISSUED, bill__isnull=False).select_related("bill"):
        lic.bill.refresh_from_db()
        if lic.bill.status != Bill.Status.PAID:
            lic.status = Licence.Status.APPROVED
            lic.issue_date = None
            lic.expiry_date = None
            lic.save()
            audit.log(AuditLog.Action.VOID, lic, user=user, message=f"Licence withdrawn: fee receipt {receipt.number} was voided")
            notify(client_people(account, lic.applicant) + users_with_cap("licence.approve", "FINANCE"),
                   f"Licence {lic.number} suspended – fee not paid", f"Receipt {receipt.number} was cancelled. Pay the fee to restore the licence.")


# ------------------------------------------------------------ fines & penalties
def _offender_account(user, *, name, national_id="", phone="", ward=None):
    """Find the offender's council account (ID number, then phone + name) or open one, so the fine is a bill like any other."""
    acc = None
    if national_id:
        acc = ClientAccount.objects.alive().filter(id_number__iexact=national_id).first()
    if acc is None and phone:
        acc = ClientAccount.objects.alive().filter(phone=phone, name__iexact=name).first()
    if acc is None:
        acc = ClientAccount.objects.create(name=name, account_type=ClientAccount.AccountType.INDIVIDUAL, id_number=national_id, phone=phone,
                                           ward=ward, created_by=user)
    return acc


@transaction.atomic
def issue_fine(user, *, offence, offender_name, location, amount=None, account=None, national_id="", phone="", vehicle_reg="", ward=None,
               date=None, notes="", fine_id=None):
    from .models import Fine

    _require(user, "fines.issue")
    amount = q2(amount or offence.default_fine)
    if amount <= 0:
        raise ValidationError("The fine must be more than zero.")
    account = account or _offender_account(user, name=offender_name, national_id=national_id, phone=phone, ward=ward)
    head = RevenueHead.objects.filter(code="FINES").first() or RevenueHead.objects.filter(category=RevenueHead.Category.FINES).first()
    kwargs = {"id": fine_id} if fine_id else {}
    fine = Fine(offence=offence, account=account, offender_name=offender_name, national_id=national_id, phone=phone, vehicle_reg=vehicle_reg,
                ward=ward, location=location, date=date or timezone.localdate(), amount=amount, notes=notes, issued_by=user, created_by=user, **kwargs)
    fine.save()
    fine.bill = Bill.objects.create(account=account, revenue_head=head, amount=amount, created_by=user,
                                    description=f"Fine {fine.reference}: {offence.name} ({location})",
                                    due_date=fine.date + timezone.timedelta(days=14))
    fine.save(update_fields=["bill", "updated_at"])
    account.recalculate()
    from core.messaging import notify_client

    notify_client(users=client_people(account), phone=phone or account.phone, subject=f"Fine {fine.reference}",
                  body=f"{offence.name} at {location} on {fine.date:%d %b %Y}: fine USD {amount:,.2f}, due by {fine.bill.due_date:%d %b %Y}. "
                       f"Pay at the council offices, to a council collector or in the Chipinge RDC app.",
                  account_number=account.account_number, sent_by=user, campaign="Fines")
    return fine


@transaction.atomic
def decide_fine(user, fine, action, reason=""):
    """Waive a fine (Treasurer / CEO, never the officer who issued it) or refer an unpaid fine to court."""
    from .models import Fine

    if action == "waive":
        _require(user, "fines.waive")
        if fine.issued_by_id == user.pk:
            raise PermissionDenied("Segregation of duties: you cannot waive a fine you issued.")
        if not reason:
            raise ValidationError("Give the reason for waiving the fine.")
        if fine.status != Fine.Status.ISSUED:
            raise ValidationError("Only unpaid fines can be waived.")
        if fine.bill_id:
            bill = fine.bill
            if bill.amount_paid > 0:
                raise ValidationError("Part of this fine has been paid – void the receipt first.")
            bill.status, bill.cancel_reason = Bill.Status.CANCELLED, f"Fine {fine.reference} waived: {reason}"
            bill.save()
            bill.account.recalculate()
        fine.status = Fine.Status.WAIVED
    elif action == "court":
        _require(user, "fines.issue", "fines.waive")
        if fine.status != Fine.Status.ISSUED:
            raise ValidationError("Only unpaid fines can be referred to court.")
        fine.status = Fine.Status.COURT
    else:
        raise ValidationError("Unknown action.")
    fine.decided_by = user
    fine.decision_reason = reason
    fine.save()
    _record(fine, "Fine decision", action.upper(), user, reason)
    return fine


@transaction.atomic
def run_late_penalties(user, *, rate_pct, days_overdue=30, today=None):
    """Charge a late-payment penalty (% of what is still owed) on every bill overdue by more than
    ``days_overdue`` days. Once per bill per month, so running it twice in a month changes nothing.
    Fines and penalties themselves are not penalised again."""
    _require(user, "billing.run")
    rate = Decimal(str(rate_pct))
    if rate <= 0 or rate > 50:
        raise ValidationError("The penalty rate must be between 0 and 50 %.")
    today = today or timezone.localdate()
    period = f"{today.year:04d}-{today.month:02d}"
    head = RevenueHead.objects.get(code="PENALTY")
    cutoff = today - timezone.timedelta(days=int(days_overdue))
    overdue = Bill.objects.alive().filter(status__in=[Bill.Status.UNPAID, Bill.Status.PART_PAID], due_date__lt=cutoff).exclude(
        revenue_head__category=RevenueHead.Category.FINES).select_related("account")
    created = skipped = 0
    for bill in overdue:
        tag = f"Late payment penalty on {bill.number}"
        if Bill.objects.alive().filter(revenue_head=head, period=period, description__startswith=tag).exists():
            skipped += 1
            continue
        amount = q2(bill.outstanding * rate / 100)
        if amount <= 0:
            continue
        Bill.objects.create(account=bill.account, property=bill.property, revenue_head=head, period=period, amount=amount, created_by=user,
                            description=f"{tag} ({rate:g}% of USD {bill.outstanding:,.2f})", due_date=today + timezone.timedelta(days=30))
        bill.account.recalculate()
        created += 1
    audit.log(AuditLog.Action.OTHER, user=user, model_label="finance.Bill",
              message=f"Late payment penalties {period} at {rate:g}%: {created} raised, {skipped} already charged")
    return created, skipped


def settle_paid_items(account):
    """Keep fines, trophy hunts and resource permits in step with their bills (after a receipt or a void)."""
    from .models import Fine

    for fine in Fine.objects.alive().filter(account=account, status__in=[Fine.Status.ISSUED, Fine.Status.PAID, Fine.Status.COURT]).select_related("bill"):
        paid = fine.bill_id and fine.bill.status == Bill.Status.PAID
        if paid and fine.status != Fine.Status.PAID:
            fine.status = Fine.Status.PAID
            fine.save(update_fields=["status", "updated_at"])
        elif not paid and fine.status == Fine.Status.PAID:
            fine.status = Fine.Status.ISSUED
            fine.save(update_fields=["status", "updated_at"])
    from departments.services import settle_stand_fees
    from social.services import settle_paid_items as social_settle

    social_settle(account)
    settle_stand_fees(account)
    settle_certificate_fees(account)


# ------------------------------------------------------------ pay everything
def start_bulk_payment(user, *, bills, method="ECOCASH", phone="", channel=Receipt.Channel.PORTAL):
    """One mobile-money prompt for several unpaid bills – on one or more of the resident's accounts (stands, shops, farms,
    rented places, fines …). When it is confirmed a receipt is issued for every bill."""
    from .gateway import get_gateway

    bills = [b for b in bills if b.status in (Bill.Status.UNPAID, Bill.Status.PART_PAID) and b.outstanding > 0]
    if not bills:
        raise ValidationError("There is nothing to pay.")
    mine = set(user.client_accounts.values_list("pk", flat=True))
    if any(b.account_id not in mine for b in bills) and not user.is_staff_member:
        raise PermissionDenied("One of these bills is not on an account linked to your profile.")
    if any(not b.revenue_head.payable_online for b in bills):
        raise ValidationError("One of these charges cannot be paid online.")
    first = bills[0]
    payment = OnlinePayment.objects.create(account=first.account, user=user, revenue_head=first.revenue_head,
                                           amount=q2(sum(b.outstanding for b in bills)), method=method, phone=phone, channel=channel,
                                           provider=settings.PAYMENT_GATEWAY, created_by=user)
    payment.bills.set(bills)
    get_gateway().initiate(payment)
    return payment


def _confirm_bulk(payment, provider_reference):
    remaining = payment.amount
    receipts = []
    for bill in payment.bills.select_related("account", "revenue_head").order_by("due_date", "created_at"):
        bill.refresh_from_db()
        part = min(remaining, bill.outstanding)
        if part <= 0:
            continue
        receipts.append(issue_receipt(payment.user, revenue_head=bill.revenue_head, amount=part, account=bill.account, bill=bill, currency=payment.currency,
                                      method=Receipt.Method.ONLINE, reference=provider_reference or payment.reference, channel=payment.channel,
                                      payer_name=bill.account.name, description=f"Online payment {payment.reference}"))
        remaining -= part
    if remaining > 0:   # a bill was paid at the office meanwhile: the rest stays as credit on the first account
        receipts.append(issue_receipt(payment.user, revenue_head=payment.revenue_head, amount=remaining, account=payment.account,
                                      currency=payment.currency, method=Receipt.Method.ONLINE, reference=provider_reference or payment.reference,
                                      channel=payment.channel, payer_name=payment.account.name, description=f"Online payment {payment.reference} (credit)"))
    payment.receipts.set(receipts)
    return receipts[0]


# ------------------------------------------------------ letters & certificates
# kind: (revenue head, offices that issue it, needs one of the resident's stands, days valid, letter number prefix)
CERTIFICATES = {
    "RESIDENCE": ("CERT-RES", ("ADMIN",), False, 90, "POR"),
    "CLEARANCE": ("CERT-CLR", ("FINANCE",), True, 90, "RCC"),
    "OWNERSHIP": ("CERT-OWN", ("ADMIN", "GROWTH"), True, 180, "SOL"),
    "CESSION": ("CESSION", ("ADMIN", "GROWTH"), True, None, "CES"),
    "BURIAL": ("BURIAL", ("SOCIAL",), False, 30, "BUR"),
}


def certificate_offices(kind):
    return CERTIFICATES[kind][1]


def can_issue_certificate(user, cert):
    return user.has_cap("certificates.issue") and (user.department in CERTIFICATES[cert.kind][1] or user.department == "EXEC")


def request_certificate(user, *, kind, property=None, purpose="", address="", ward=None, other_party_name="", other_party_id="", event_date=None,
                        place="", req_id=None):
    from .models import CertificateRequest, RevenueHead, Tenancy

    if not user.is_client:
        raise PermissionDenied("Only residents can request letters and certificates here.")
    if kind not in CERTIFICATES:
        raise ValidationError("Choose the letter or certificate you need.")
    head_code, _offices, needs_property, _days, _prefix = CERTIFICATES[kind]
    owned = Property.objects.alive().filter(account__portal_users=user)
    if property is not None and not owned.filter(pk=property.pk).exists():
        rented = Tenancy.objects.filter(user=user, property=property, is_active=True).exists()
        if not (kind == "RESIDENCE" and rented):
            raise PermissionDenied("That stand is not linked to your profile.")
    if needs_property and property is None:
        raise ValidationError("Choose the stand.")
    if kind == "CLEARANCE" and property.account.balance > 0:
        raise ValidationError(f"Account {property.account.account_number} owes USD {property.account.balance:,.2f}. Pay it first, then ask for the clearance.")
    if kind == "CESSION" and not (other_party_name and other_party_id):
        raise ValidationError("Enter the new owner's name and National ID.")
    if kind == "BURIAL" and not (other_party_name and event_date and place):
        raise ValidationError("Enter the name of the deceased, the date of death and the cemetery.")
    if kind == "RESIDENCE" and not (address or property):
        raise ValidationError("Enter where you live.")
    account = property.account if property is not None and owned.filter(pk=property.pk).exists() else client_own_account(user)
    kwargs = {"id": req_id} if req_id else {}
    c = CertificateRequest.objects.create(kind=kind, user=user, account=account, property=property, applicant_name=user.get_full_name() or user.username,
                                          national_id=user.national_id, phone=user.phone, address=address or (str(property) if property else ""),
                                          ward=ward or user.ward, purpose=purpose, other_party_name=other_party_name, other_party_id=other_party_id,
                                          event_date=event_date or None, place=place, created_by=user, **kwargs)
    head = RevenueHead.objects.filter(code=head_code, is_active=True).first()
    if head and head.default_amount > 0:
        c.fee_bill = Bill.objects.create(account=account, revenue_head=head, amount=head.default_amount, created_by=user,
                                         description=f"{c.get_kind_display()} {c.reference}", due_date=timezone.localdate() + timezone.timedelta(days=30))
        c.save(update_fields=["fee_bill", "updated_at"])
        account.recalculate()
    else:
        _certificate_to_office(c)
    audit.log(AuditLog.Action.CREATE, c, user=user, message=f"Requested {c.get_kind_display()}")
    return c


def _certificate_to_office(c):
    from .models import CertificateRequest

    c.status = CertificateRequest.Status.PROCESSING
    c.save(update_fields=["status", "updated_at"])
    officers = [u for u in User.objects.filter(is_active=True, user_type=User.UserType.STAFF, department__in=CERTIFICATES[c.kind][1])
                if u.has_cap("certificates.issue")]
    notify(officers, f"{c.get_kind_display()} to issue: {c.reference}", f"{c.applicant_name} – {c.purpose or c.address}",
           f"/staff/finance/certificates/{c.pk}/")


def settle_certificate_fees(account):
    from .models import CertificateRequest

    for c in CertificateRequest.objects.alive().filter(account=account, status=CertificateRequest.Status.FEE_DUE, fee_bill__status=Bill.Status.PAID):
        _certificate_to_office(c)


@transaction.atomic
def certificate_action(user, c, action, note=""):
    from core.messaging import notify_client

    from .models import CertificateRequest

    if not can_issue_certificate(user, c):
        raise PermissionDenied("Your office does not issue this letter / certificate.")
    if c.status != CertificateRequest.Status.PROCESSING:
        raise ValidationError("Only a request whose fee is paid can be issued or rejected.")
    _head, _offices, _needs, days, prefix = CERTIFICATES[c.kind]
    if action == "issue":
        if c.kind == "CLEARANCE" and c.property.account.balance > 0:
            raise ValidationError(f"Account {c.property.account.account_number} owes USD {c.property.account.balance:,.2f} – no clearance until it is paid.")
        c.status, c.number = CertificateRequest.Status.ISSUED, SequenceCounter.next(prefix)
        c.valid_until = timezone.localdate() + timezone.timedelta(days=days) if days else None
        subject = f"{c.get_kind_display()} {c.number} is ready"
        body = "Open it in the app, or collect the signed copy at the council offices."
    elif action == "reject":
        if not note:
            raise ValidationError("Give the reason.")
        c.status = CertificateRequest.Status.REJECTED
        subject, body = f"{c.get_kind_display()} {c.reference} not issued", note
    else:
        raise ValidationError("Unknown action.")
    c.decided_by, c.decided_at, c.decision_note = user, timezone.now(), note
    c.save()
    notify_client(users=[c.user] if c.user_id else [], phone=c.phone, subject=subject, body=body, account_number=c.account.account_number, sent_by=user)
    audit.log(AuditLog.Action.APPROVE if action == "issue" else AuditLog.Action.REJECT, c, user=user, message=f"{action}: {note}")
    return c
