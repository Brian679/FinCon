"""Rules for the Social Services registers (CAMPFIRE, natural resources, farms, water, welfare)."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core import audit
from core.models import AuditLog
from finance.models import Bill, RevenueHead
from finance.models import q2
from finance.services import _record, _require, client_people, notify, users_with_cap

from .models import Assistance, Beneficiary, Extraction, HuntingQuota, ResourcePermit, TrophyHunt


def _head(code, fallback_category=RevenueHead.Category.FEES):
    return RevenueHead.objects.filter(code=code).first() or RevenueHead.objects.filter(category=fallback_category).first()


# ------------------------------------------------------------------ CAMPFIRE
@transaction.atomic
def book_hunt(user, *, quota, operator, client_name, trophy_fee=None, hunt_id=None, **extra):
    _require(user, "hunts.manage")
    quota = HuntingQuota.objects.select_for_update().get(pk=quota.pk)
    if quota.remaining <= 0:
        raise ValidationError(f"The {quota.year} quota for {quota.get_species_display()} ({quota.quota}) is fully used.")
    fee = q2(trophy_fee or quota.trophy_fee)
    if fee <= 0:
        raise ValidationError("Set the trophy fee.")
    kwargs = {"id": hunt_id} if hunt_id else {}
    allowed = {k: v for k, v in extra.items() if k in ("professional_hunter", "client_nationality", "hunt_date", "community_share_pct", "trophy_details")
               and v not in (None, "")}
    hunt = TrophyHunt.objects.create(quota=quota, operator=operator, client_name=client_name, trophy_fee=fee, recorded_by=user, created_by=user,
                                     **allowed, **kwargs)
    return hunt


@transaction.atomic
def hunt_action(user, hunt, action, *, hunt_date=None, trophy_details=""):
    """``hunted``: the animal was taken – the trophy fee is billed to the safari operator and the hunt is PAID
    by itself when the bill is paid. ``cancel``: frees the quota (only before the hunt)."""
    _require(user, "hunts.manage")
    if action == "hunted":
        if hunt.status != TrophyHunt.Status.BOOKED:
            raise ValidationError("Only a booked hunt can be recorded as hunted.")
        hunt.hunt_date = hunt_date or hunt.hunt_date or timezone.localdate()
        if trophy_details:
            hunt.trophy_details = trophy_details
        hunt.bill = Bill.objects.create(account=hunt.operator, revenue_head=_head("TROPHY"), amount=hunt.trophy_fee, created_by=user,
                                        description=f"Trophy fee {hunt.reference}: {hunt.species_label} – {hunt.client_name}",
                                        due_date=timezone.localdate() + timezone.timedelta(days=30))
        hunt.status = TrophyHunt.Status.HUNTED
        hunt.save()
        hunt.operator.recalculate()
        notify(client_people(hunt.operator), f"Trophy fee due: {hunt.reference}", f"USD {hunt.trophy_fee:,.2f} for {hunt.species_label}")
    elif action == "cancel":
        if hunt.status != TrophyHunt.Status.BOOKED:
            raise ValidationError("Only a booked hunt can be cancelled.")
        hunt.status = TrophyHunt.Status.CANCELLED
        hunt.save()
    else:
        raise ValidationError("Unknown action.")
    _record(hunt, "Trophy hunt", action.upper(), user, trophy_details)
    return hunt


def campfire_by_ward(year=None):
    """Trophy fees by producer ward with the CAMPFIRE community share and the council share."""
    year = year or timezone.localdate().year
    rows = {}
    for h in TrophyHunt.objects.alive().filter(quota__year=year).exclude(status=TrophyHunt.Status.CANCELLED).select_related("quota"):
        r = rows.setdefault(h.quota.ward, {"ward": h.quota.ward, "hunts": 0, "fees": Decimal(0), "paid": Decimal(0), "community": Decimal(0),
                                            "council": Decimal(0)})
        r["hunts"] += 1
        r["fees"] += h.trophy_fee
        if h.status == TrophyHunt.Status.PAID:
            r["paid"] += h.trophy_fee
            r["community"] += h.community_share
            r["council"] += h.council_share
    return sorted(rows.values(), key=lambda r: (r["ward"] is None, r["ward"] or 0))


# ----------------------------------------------------------- natural resources
@transaction.atomic
def decide_permit(user, permit, action, note="", unit_fee=None):
    """approve → the fee is billed and the permit becomes ACTIVE by itself when paid; reject; suspend; reinstate."""
    _require(user, "permits.approve")
    if action in ("approve", "reject"):
        if permit.status != ResourcePermit.Status.APPLIED:
            raise ValidationError("This application has already been decided.")
        if permit.applied_by_id == user.pk:
            raise PermissionDenied("Segregation of duties: someone else must decide a permit you captured.")
    if action == "approve":
        if unit_fee not in (None, ""):
            permit.unit_fee = Decimal(str(unit_fee))
            permit.save()     # recalculates the fee
        permit.bill = Bill.objects.create(account=permit.holder, revenue_head=_head("NAT-RES"), amount=permit.fee, created_by=user,
                                          description=f"{permit.get_permit_type_display()} permit {permit.reference}: "
                                                      f"{permit.quantity_allowed:g} {permit.get_unit_display()} × ${permit.unit_fee}",
                                          due_date=timezone.localdate() + timezone.timedelta(days=14))
        permit.status = ResourcePermit.Status.APPROVED
        permit.holder.recalculate()
        notify(client_people(permit.holder), f"Permit {permit.reference} approved – pay USD {permit.fee:,.2f}",
               "The permit becomes active as soon as the fee is paid.")
    elif action == "reject":
        if not note:
            raise ValidationError("Give the reason for rejecting.")
        permit.status = ResourcePermit.Status.REJECTED
    elif action == "suspend":
        if permit.status != ResourcePermit.Status.ACTIVE:
            raise ValidationError("Only an active permit can be suspended.")
        if not note:
            raise ValidationError("Give the reason for suspending.")
        permit.status = ResourcePermit.Status.SUSPENDED
    elif action == "reinstate":
        if permit.status != ResourcePermit.Status.SUSPENDED:
            raise ValidationError("Only a suspended permit can be reinstated.")
        permit.status = ResourcePermit.Status.ACTIVE
    else:
        raise ValidationError("Unknown action.")
    permit.decided_by = user
    permit.decision_note = note
    permit.save()
    _record(permit, "Permit decision", action.upper(), user, note)
    return permit


@transaction.atomic
def record_extraction(user, permit, *, quantity, date=None, vehicle_reg="", destination="", notes="", extraction_id=None):
    _require(user, "permits.manage")
    permit = ResourcePermit.objects.select_for_update().get(pk=permit.pk)
    date = date or timezone.localdate()
    if permit.status != ResourcePermit.Status.ACTIVE:
        raise ValidationError(f"Permit {permit.reference} is not active ({permit.get_status_display()}). Extraction without an active "
                              "permit is illegal – issue a fine.")
    if not (permit.valid_from <= date <= permit.valid_to):
        raise ValidationError(f"Permit {permit.reference} is valid {permit.valid_from} – {permit.valid_to}.")
    quantity = Decimal(str(quantity))
    if quantity > permit.quantity_left:
        raise ValidationError(f"Only {permit.quantity_left:g} {permit.get_unit_display()} left on this permit – this load is over the "
                              "permitted quantity. Issue a fine for over-extraction.")
    kwargs = {"id": extraction_id} if extraction_id else {}
    ex = Extraction.objects.create(permit=permit, quantity=quantity, date=date, vehicle_reg=vehicle_reg, destination=destination, notes=notes,
                                   recorded_by=user, created_by=user, **kwargs)
    ResourcePermit.objects.filter(pk=permit.pk).update(updated_at=timezone.now())
    if permit.quantity_left <= permit.quantity_allowed / 10:
        notify(users_with_cap("permits.approve"), f"Permit {permit.reference} almost used up",
               f"{permit.quantity_left:g} {permit.get_unit_display()} left")
    return ex


def expire_permits(today=None):
    today = today or timezone.localdate()
    return ResourcePermit.objects.alive().filter(status__in=[ResourcePermit.Status.ACTIVE, ResourcePermit.Status.APPROVED],
                                                 valid_to__lt=today).update(status=ResourcePermit.Status.EXPIRED, updated_at=timezone.now())


# ------------------------------------------------------------------- welfare
def apply_for_assistance(user, *, category, need, village, reason, ward=None, household_size=1, children=0, beneficiary_id=None):
    """A resident asks to be registered as a beneficiary (food aid, BEAM school fees, medical, shelter …)."""
    from django.contrib.auth import get_user_model

    if not user.is_client:
        raise PermissionDenied("Only residents apply here; staff register households in the welfare register.")
    if Beneficiary.objects.alive().filter(user=user, status__in=["APPLIED", "APPROVED"]).exists():
        raise ValidationError("You already have an application or are already a beneficiary.")
    if category not in Beneficiary.Category.values:
        raise ValidationError("Choose the category that describes your household.")
    if not (village and reason):
        raise ValidationError("Enter your village and why you need help.")
    kwargs = {"id": beneficiary_id} if beneficiary_id else {}
    b = Beneficiary.objects.create(name=user.get_full_name() or user.username, national_id=user.national_id, phone=user.phone, ward=ward or user.ward,
                                   village=village, household_size=max(1, int(household_size or 1)), children=int(children or 0), category=category,
                                   need=need or "", reason=reason, status="APPLIED", is_active=False, user=user, created_by=user, **kwargs)
    officers = [u for u in get_user_model().objects.filter(is_active=True, department="SOCIAL") if u.has_cap("welfare.manage")]
    notify(officers, f"Application for assistance: {b.name}", f"{b.get_category_display()} · {b.village}, ward {b.ward or '-'} · {b.get_need_display()}",
           f"/staff/social/welfare/{b.pk}/")
    audit.log(AuditLog.Action.CREATE, b, user=user, message="Applied for social assistance")
    return b


def assess_beneficiary(user, b, action, note=""):
    """After the home visit: approve (the household becomes a beneficiary) or not; close when support ends."""
    from core.messaging import notify_client

    _require(user, "welfare.manage")
    if action in ("approve", "reject") and b.status != "APPLIED":
        raise ValidationError("This application has already been assessed.")
    if action == "approve":
        b.status, b.is_active = "APPROVED", True
        subject, body = "You are registered for social assistance", f"Reference {b.reference}. The council will contact you when assistance is given."
    elif action == "reject":
        if not note:
            raise ValidationError("Give the reason.")
        b.status, b.is_active = "REJECTED", False
        subject, body = f"Application {b.reference} not approved", note
    elif action == "close":
        if b.status != "APPROVED":
            raise ValidationError("Only an active beneficiary can be closed.")
        b.status, b.is_active = "CLOSED", False
        subject, body = f"Support ended – {b.reference}", note or "Your household is no longer on the support list."
    else:
        raise ValidationError("Unknown action.")
    b.assessed_by, b.assessed_at, b.assessment_note = user, timezone.now(), note
    b.save()
    notify_client(users=[b.user] if b.user_id else [], phone=b.phone, subject=subject, body=body, sent_by=user, campaign="Social welfare")
    audit.log(AuditLog.Action.APPROVE if action == "approve" else AuditLog.Action.REJECT if action == "reject" else AuditLog.Action.OTHER, b,
              user=user, message=f"{action}: {note}")
    return b


def give_assistance(user, beneficiary, *, kind, description, value=0, programme="", date=None, assistance_id=None):
    _require(user, "welfare.manage")
    if not beneficiary.is_active or beneficiary.status != "APPROVED":
        raise ValidationError("This household is not an active beneficiary.")
    kwargs = {"id": assistance_id} if assistance_id else {}
    a = Assistance.objects.create(beneficiary=beneficiary, kind=kind, description=description, value=q2(value or 0), programme=programme,
                                  date=date or timezone.localdate(), given_by=user, created_by=user, **kwargs)
    type(beneficiary).objects.filter(pk=beneficiary.pk).update(updated_at=timezone.now())
    if beneficiary.user_id:
        notify([beneficiary.user], f"Assistance given: {a.get_kind_display()}", f"{description} · {a.date:%d %b %Y}")
    return a


# ------------------------------------------------------------- payments link
def settle_paid_items(account):
    """Called after every receipt / void on the account: hunts become PAID and permits ACTIVE when their bill
    is paid, and go back if the payment is voided."""
    for h in TrophyHunt.objects.alive().filter(operator=account, status__in=[TrophyHunt.Status.HUNTED, TrophyHunt.Status.PAID]).select_related("bill"):
        paid = h.bill_id and h.bill.status == Bill.Status.PAID
        new = TrophyHunt.Status.PAID if paid else TrophyHunt.Status.HUNTED
        if h.status != new:
            h.status = new
            h.save(update_fields=["status", "updated_at"])
            audit.log(AuditLog.Action.OTHER, h, message=f"Trophy fee {'paid' if paid else 'payment voided'}")
    for p in ResourcePermit.objects.alive().filter(holder=account, status__in=[ResourcePermit.Status.APPROVED, ResourcePermit.Status.ACTIVE]).select_related("bill"):
        if p.bill_id is None:
            continue
        paid = p.bill.status == Bill.Status.PAID
        new = ResourcePermit.Status.ACTIVE if paid else ResourcePermit.Status.APPROVED
        if p.status != new:
            p.status = new
            p.save(update_fields=["status", "updated_at"])
            if paid:
                notify(client_people(account), f"Permit {p.reference} is now active", f"Valid until {p.valid_to:%d %b %Y}.")


# Default council fee per unit for applications made in the residents' app (the deciding officer may change it on approval).
PERMIT_TARIFF = {"SAND": ("M3", "3"), "GRAVEL": ("M3", "4"), "CLAY": ("M3", "2"), "MINING": ("MONTH", "75"), "TIMBER": ("M3", "12"),
                 "FIREWOOD": ("CORD", "5"), "THATCH": ("BUNDLE", "0.50"), "OTHER": ("LOAD", "10")}


@transaction.atomic
def client_apply_permit(user, *, holder, permit_type, location, quantity, ward=None, days=30, permit_id=None, purpose=""):
    if permit_type not in PERMIT_TARIFF:
        raise ValidationError("Choose the type of permit.")
    unit, fee = PERMIT_TARIFF[permit_type]
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValidationError("Enter the quantity you want to extract.")
    days = max(1, min(int(days), 365))
    today = timezone.localdate()
    kwargs = {"id": permit_id} if permit_id else {}
    permit = ResourcePermit.objects.create(permit_type=permit_type, holder=holder, ward=ward, location=location, unit=unit, quantity_allowed=quantity,
                                           unit_fee=Decimal(fee), valid_from=today, valid_to=today + timezone.timedelta(days=days),
                                           conditions=purpose, applied_by=user, created_by=user, **kwargs)
    notify(users_with_cap("permits.approve"), f"Permit application from the app: {permit.reference}",
           f"{permit.get_permit_type_display()} – {holder.name}, {location} ({quantity:g} {permit.get_unit_display()})", f"/staff/social/permits/{permit.pk}/")
    return permit


def claim_fine(user, reference, id_or_phone):
    """A resident looks up a fine by its number and their ID or phone number; the offender's account is then linked to
    their profile so the fine appears in the app and can be paid."""
    from finance.models import Fine

    ref = (reference or "").strip().upper()
    key = "".join((id_or_phone or "").split()).upper()
    fine = Fine.objects.alive().filter(reference__iexact=ref).select_related("account").first()
    if fine is None or not key:
        raise ValidationError("No fine with that number – check the fine slip / SMS.")
    known = {"".join(v.split()).upper() for v in (fine.national_id, fine.phone, fine.account.id_number, fine.account.phone) if v}
    if key not in known:
        raise PermissionDenied("The ID or phone number does not match this fine.")
    fine.account.portal_users.add(user)
    type(fine.account).objects.filter(pk=fine.account_id).update(updated_at=timezone.now())
    return fine
