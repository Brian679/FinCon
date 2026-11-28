"""Workflows for the departmental registers. Used by the website and the
mobile sync so the same stage-by-stage rules apply everywhere."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core import audit
from core.models import AuditLog, Department
from finance.services import _record, notify

from .models import (
    Asset, AssetMaintenance, AuditFinding, BuildingPlan, CommunityActivity, ICTTicket, Incident, Project, Resolution, StandApplication,
)

User = get_user_model()


def _need(user, *caps):
    if not user.has_cap(*caps):
        audit.log(AuditLog.Action.ACCESS_DENIED, user=user, message=f"Needs {', '.join(caps)}")
        raise PermissionDenied("You do not have permission for this action.")


def heads_of(department):
    return [u for u in User.objects.filter(department=department, is_active=True) if u.is_head]


def is_head_of(user, department):
    return user.is_ceo or (user.is_head and user.department == department)


# ----------------------------------------------------------- incidents
@transaction.atomic
def report_incident(user, **data):
    _need(user, "incidents.manage")
    inc = Incident.objects.create(reported_by=user, created_by=user, **data)
    notify(heads_of(Department.SOCIAL_SERVICES) + list(User.objects.filter(role="CEO")), f"Incident: {inc.title}",
           f"{inc.get_incident_type_display()} at {inc.location}, ward {inc.ward or '-'}. {inc.households_affected} household(s) affected.",
           f"/staff/social/incidents/{inc.pk}/")
    return inc


@transaction.atomic
def update_incident(user, inc, *, status=None, response="", **figures):
    _need(user, "incidents.manage")
    if status == Incident.Status.CLOSED and not is_head_of(user, Department.SOCIAL_SERVICES):
        raise PermissionDenied("Only the Director of Social Services can close an incident.")
    if status:
        inc.status = status
    if response:
        stamp = timezone.localtime().strftime("%d %b %H:%M")
        inc.response = (inc.response + f"\n[{stamp} {user.get_full_name()}] {response}").strip()
    for k in ("households_affected", "people_injured", "deaths", "livestock_lost", "crops_hectares"):
        if figures.get(k) not in (None, ""):
            setattr(inc, k, figures[k])
    inc.save()
    return inc


# ---------------------------------------------------------- activities
@transaction.atomic
def plan_activity(user, **data):
    _need(user, "activities.manage")
    data.setdefault("department", user.department)
    return CommunityActivity.objects.create(officer=user, created_by=user, **data)


@transaction.atomic
def report_activity(user, act, *, report, participants):
    _need(user, "activities.manage")
    if act.status not in (CommunityActivity.Status.PLANNED, CommunityActivity.Status.DONE):
        raise ValidationError("This activity can no longer be changed.")
    act.report, act.participants, act.status = report, int(participants or 0), CommunityActivity.Status.DONE
    act.save()
    notify(heads_of(act.department), f"Activity report to verify: {act.title}", f"{act.participants} participant(s)", f"/staff/activities/{act.pk}/")
    return act


@transaction.atomic
def verify_activity(user, act, approve=True, note=""):
    if not is_head_of(user, act.department):
        raise PermissionDenied("Only the head of the department can verify activity reports.")
    if act.status != CommunityActivity.Status.DONE:
        raise ValidationError("Only submitted reports can be verified.")
    if act.officer_id == user.pk:
        raise PermissionDenied("You cannot verify your own report.")
    if approve:
        act.status, act.verified_by = CommunityActivity.Status.VERIFIED, user
    else:
        act.status = CommunityActivity.Status.PLANNED
        act.report = (act.report + f"\n[Returned by {user.get_full_name()}: {note}]").strip()
    act.save()
    _record(act, "HOD verification", "APPROVED" if approve else "REJECTED", user, note)
    notify([act.officer], f"Activity report {'verified' if approve else 'returned'}: {act.title}", note)
    return act


# ------------------------------------------------------- building plans
@transaction.atomic
def submit_building_plan(user, **data):
    from finance.models import Bill, ClientAccount, RevenueHead

    if user.is_client:
        data.update(applicant=user, applicant_name=data.get("applicant_name") or user.get_full_name(), phone=data.get("phone") or user.phone)
    else:
        _need(user, "plans.review")
    plan = BuildingPlan(created_by=user, **data)
    head = RevenueHead.objects.filter(code="BUILD-PLAN").first()
    plan.fee = head.default_amount if head else 0
    plan.save()
    account = user.client_accounts.alive().first() if user.is_client else None
    if head and plan.fee and account is not None:
        plan.bill = Bill.objects.create(account=account, revenue_head=head, amount=plan.fee, description=f"Building plan fee {plan.reference}",
                                        due_date=timezone.localdate() + timezone.timedelta(days=14), created_by=user)
        plan.save(update_fields=["bill", "updated_at"])
        account.recalculate()
    notify([u for u in User.objects.filter(is_active=True) if u.has_cap("plans.review")], f"Building plan submitted: {plan.reference}",
           f"{plan.applicant_name}, stand {plan.stand_number} {plan.location}", f"/staff/technical/plans/{plan.pk}/")
    return plan


@transaction.atomic
def plan_action(user, plan, action, note=""):
    S = BuildingPlan.Status
    if action in ("start_review", "recommend", "return"):
        _need(user, "plans.review")
        if plan.status not in (S.SUBMITTED, S.UNDER_REVIEW):
            raise ValidationError("This plan is not awaiting technical review.")
        plan.reviewed_by = user
        plan.review_notes = (plan.review_notes + "\n" + note).strip() if note else plan.review_notes
        plan.status = {"start_review": S.UNDER_REVIEW, "recommend": S.RECOMMENDED, "return": S.REJECTED}[action]
        if action == "recommend":
            notify([u for u in heads_of(Department.TECHNICAL_SERVICES)], f"Plan {plan.reference} recommended for approval", note,
                   f"/staff/technical/plans/{plan.pk}/")
    elif action in ("approve", "reject"):
        _need(user, "plans.approve")
        if plan.status != S.RECOMMENDED:
            raise ValidationError("The plan must be recommended by a technical officer first.")
        if plan.reviewed_by_id == user.pk:
            raise PermissionDenied("Segregation of duties: the reviewer cannot also approve.")
        if action == "approve" and plan.bill_id and plan.bill.status != "PAID":
            raise ValidationError("The plan approval fee has not been paid.")
        plan.decided_by, plan.decision_notes = user, note
        plan.status = S.APPROVED if action == "approve" else S.REJECTED
        _record(plan, "Engineer decision", "APPROVED" if action == "approve" else "REJECTED", user, note)
    elif action in ("inspect", "complete"):
        _need(user, "plans.review")
        if plan.status not in (S.APPROVED, S.CONSTRUCTION):
            raise ValidationError("Inspections start after approval.")
        stamp = timezone.localdate().isoformat()
        plan.inspection_log = (plan.inspection_log + f"\n{stamp} {user.get_full_name()}: {note}").strip()
        plan.status = S.COMPLETED if action == "complete" else S.CONSTRUCTION
    else:
        raise ValidationError("Unknown action.")
    plan.save()
    notify([plan.applicant], f"Building plan {plan.reference}: {plan.get_status_display()}", note)
    return plan


# --------------------------------------------------------------- assets
@transaction.atomic
def report_asset_condition(user, asset, *, condition, note="", work_done="", cost=0, performed_by=""):
    _need(user, "assets.manage", "assets.condition")
    asset.condition = condition
    if condition == Asset.Condition.BROKEN:
        asset.status = Asset.Status.UNDER_REPAIR
    elif asset.status == Asset.Status.UNDER_REPAIR and condition in (Asset.Condition.GOOD, Asset.Condition.FAIR):
        asset.status = Asset.Status.IN_USE
    asset.save()
    m = AssetMaintenance.objects.create(asset=asset, work_done=work_done or f"Condition report: {note}", cost=cost or 0,
                                        performed_by=performed_by or user.get_full_name(), condition_after=condition, created_by=user)
    if condition == Asset.Condition.BROKEN:
        notify(heads_of(asset.department), f"Asset broken down: {asset}", note, f"/staff/assets/{asset.pk}/")
    return m


# ------------------------------------------------------------ ICT desk
@transaction.atomic
def raise_ticket(user, **data):
    _need(user, "ict.raise")
    t = ICTTicket.objects.create(raised_by=user, department=user.department or "ADMIN", created_by=user, **data)
    notify([u for u in User.objects.filter(is_active=True) if u.has_cap("ict.manage")], f"ICT ticket {t.reference}: {t.subject}",
           t.description[:150], f"/staff/ict/{t.pk}/")
    return t


@transaction.atomic
def ticket_action(user, t, action, note=""):
    if action == "close":
        if t.raised_by_id != user.pk and not user.has_cap("ict.manage"):
            raise PermissionDenied
        t.status = ICTTicket.Status.CLOSED
    else:
        _need(user, "ict.manage")
        if action == "take":
            t.assigned_to, t.status = user, ICTTicket.Status.IN_PROGRESS
        elif action == "resolve":
            t.status, t.resolution, t.resolved_at = ICTTicket.Status.RESOLVED, note, timezone.now()
            notify([t.raised_by], f"ICT ticket resolved: {t.subject}", note)
        else:
            raise ValidationError("Unknown action.")
    t.save()
    return t


# --------------------------------------------------------- resolutions
@transaction.atomic
def update_resolution(user, res, *, status, note=""):
    if not (res.responsible_id == user.pk or user.has_cap("meetings.manage") or is_head_of(user, res.department)):
        raise PermissionDenied("Only the responsible officer or head of department can update this resolution.")
    res.status = status
    if note:
        res.progress_note = (res.progress_note + f"\n{timezone.localdate()} {user.get_full_name()}: {note}").strip()
    res.save()
    return res


# --------------------------------------------------------- audit & misc
@transaction.atomic
def respond_finding(user, f, *, response, date=None):
    if not (user.has_cap("audit.respond") and (user.department == f.department or user.is_ceo)):
        raise PermissionDenied("Only the head of the audited department can respond.")
    f.management_response, f.responded_by, f.status = response, user, AuditFinding.Status.RESPONDED
    if date:
        f.implementation_date = date
    f.save()
    notify([f.auditor], f"Management responded: {f.reference}", response[:200])
    return f


@transaction.atomic
def apply_for_stand(user, *, stand_type, preferred_location, ward=None, notes="", applicant_name="", national_id="", phone="", app_id=None):
    """Stand application. From the residents' app the waiting-list fee is billed to the applicant's own account and the
    application joins the waiting list once it is paid; one captured at the council office joins at once (fee paid there)."""
    from finance.models import Bill, RevenueHead
    from finance.services import client_own_account

    kwargs = {"id": app_id} if app_id else {}
    if user.is_client:
        if StandApplication.objects.alive().filter(applicant=user, status__in=[StandApplication.Status.FEE_DUE, StandApplication.Status.RECEIVED,
                                                                              StandApplication.Status.SHORTLISTED], stand_type=stand_type).exists():
            raise ValidationError("You are already on the waiting list for this type of stand.")
        acc = client_own_account(user)
        st = StandApplication.objects.create(applicant=user, applicant_name=user.get_full_name() or user.username, national_id=user.national_id or national_id,
                                             phone=user.phone or phone, stand_type=stand_type, preferred_location=preferred_location, ward=ward,
                                             notes=notes, account=acc, status=StandApplication.Status.FEE_DUE, created_by=user, **kwargs)
        head = RevenueHead.objects.filter(code="STAND-APP").first()
        fee = head.default_amount if head else 0
        if head and fee > 0:
            st.fee_bill = Bill.objects.create(account=acc, revenue_head=head, amount=fee, created_by=user,
                                              description=f"Stand application {st.reference} – waiting-list fee",
                                              due_date=timezone.localdate() + timezone.timedelta(days=30))
            st.save(update_fields=["fee_bill", "updated_at"])
            acc.recalculate()
            notify([user], f"Stand application {st.reference} received",
                   f"Pay the waiting-list fee of USD {fee:,.2f} in the app to join the waiting list.")
        else:
            _join_waiting_list(st)
        return st
    _need(user, "stands.manage")
    st = StandApplication.objects.create(applicant_name=applicant_name, national_id=national_id, phone=phone, stand_type=stand_type,
                                         preferred_location=preferred_location, ward=ward, notes=notes, created_by=user, **kwargs)
    _join_waiting_list(st)
    return st


def _join_waiting_list(st):
    st.status, st.joined_waiting_list_at = StandApplication.Status.RECEIVED, timezone.now()
    st.save(update_fields=["status", "joined_waiting_list_at", "updated_at"])
    if st.applicant_id:
        notify([st.applicant], f"You are on the stand waiting list – number {st.waiting_position}",
               f"{st.get_stand_type_display()} stand, {st.preferred_location}. You will be notified when a stand is allocated to you.")
    managers = [u for u in get_user_model().objects.filter(is_active=True) if u.has_cap("stands.allocate")]
    notify(managers, f"New stand application on the waiting list: {st.reference}", f"{st.applicant_name} – {st.preferred_location}",
           f"/staff/growth-points/stands/{st.pk}/")


def settle_stand_fees(account):
    """After a receipt / void on the account: a paid waiting-list fee puts the application on the waiting list."""
    for st in StandApplication.objects.alive().filter(account=account, status=StandApplication.Status.FEE_DUE).select_related("fee_bill"):
        if st.fee_bill_id and st.fee_bill.status == "PAID":
            _join_waiting_list(st)


def stand_action(user, st, action, *, stand="", note="", deposit=None):
    _need(user, "stands.manage")
    if action in ("shortlist", "allocate") and st.status == StandApplication.Status.FEE_DUE:
        raise ValidationError("The application fee has not been paid yet – the applicant is not on the waiting list.")
    if action == "shortlist":
        st.status = StandApplication.Status.SHORTLISTED
    elif action == "allocate":
        if not user.has_cap("stands.allocate"):
            raise PermissionDenied("Only the Growth Point Manager can allocate stands.")
        if not stand:
            raise ValidationError("Enter the stand number.")
        st.status, st.allocated_stand, st.allocated_by, st.allocated_at = StandApplication.Status.ALLOCATED, stand, user, timezone.now()
        msg = "Visit the council offices to sign the agreement of sale."
        if deposit not in (None, "") and st.account_id:
            from decimal import Decimal

            from finance.models import Bill, RevenueHead

            amount = Decimal(str(deposit))
            if amount > 0:
                st.deposit_bill = Bill.objects.create(account=st.account, revenue_head=RevenueHead.objects.get(code="STAND"), amount=amount, created_by=user,
                                                      description=f"Deposit – stand {stand} ({st.reference})",
                                                      due_date=timezone.localdate() + timezone.timedelta(days=30))
                st.account.recalculate()
                msg = f"Pay the deposit of USD {amount:,.2f} in the app or at the council offices, then sign the agreement of sale."
        from core.messaging import notify_client

        notify_client(users=[st.applicant] if st.applicant_id else [], phone=st.phone, subject=f"Stand allocated to you: {stand}",
                      body=f"Good news – stand {stand} ({st.preferred_location}) has been allocated to you. {msg}", sent_by=user,
                      campaign="Stand allocation")
    elif action == "reject":
        st.status = StandApplication.Status.REJECTED
        notify([st.applicant], f"Stand application {st.reference}", note)
    else:
        raise ValidationError("Unknown action.")
    if note:
        st.notes = (st.notes + "\n" + note).strip()
    st.save()
    return st


@transaction.atomic
def project_update(user, p, *, progress=None, status=None, note=""):
    _need(user, "projects.manage")
    if progress is not None:
        p.progress = max(0, min(100, int(progress)))
    if status:
        p.status = status
    if note:
        p.description = (p.description + f"\n{timezone.localdate()} {user.get_full_name()}: {note}").strip()
    p.save()
    return p
