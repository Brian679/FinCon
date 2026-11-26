"""Payroll rules (used by the website, the API and the apps)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from core import audit
from core.models import AuditLog
from finance.services import _require, notify, users_with_cap

from .models import Payslip, SalaryPayment, SalaryProfile

User = get_user_model()
FIELDS = ["grade", "currency", "basic_salary", "housing_allowance", "transport_allowance", "other_allowances", "paye", "nssa", "pension",
          "medical_aid", "other_deductions", "payment_method", "bank_name", "bank_account", "is_active", "notes"]
MONEY_FIELDS = {"basic_salary", "housing_allowance", "transport_allowance", "other_allowances", "paye", "nssa", "pension", "medical_aid",
                "other_deductions"}


def can_view_payroll(user):
    return user.has_cap("payroll.view", "payroll.manage")


def payslip_scope(user, qs):
    return qs if can_view_payroll(user) else qs.filter(employee=user)


def salary_scope(user, qs):
    return qs if can_view_payroll(user) else qs.filter(employee=user)


@transaction.atomic
def update_salary(user, employee, **data):
    _require(user, "payroll.manage")
    if employee.pk == user.pk:
        raise PermissionDenied("Segregation of duties: someone else in Finance must change your own salary.")
    if not employee.is_staff_member:
        raise ValidationError("Only council staff are on the payroll.")
    profile, _ = SalaryProfile.objects.get_or_create(employee=employee, defaults={"created_by": user})
    for k, v in data.items():
        if k not in FIELDS:
            continue
        if k in MONEY_FIELDS:
            v = Decimal(str(v or 0)).quantize(Decimal("0.01"))
            if v < 0:
                raise ValidationError(f"{k.replace('_', ' ').capitalize()} cannot be negative.")
        setattr(profile, k, v)
    if profile.net < 0:
        raise ValidationError("Deductions are larger than the gross salary.")
    profile.save()
    return profile


@transaction.atomic
def run_payroll(user, year: int, month: int):
    """Create this month's payslips (drafts) for everyone on the payroll who does not have one yet."""
    _require(user, "payroll.manage")
    if not (1 <= int(month) <= 12):
        raise ValidationError("Choose a month.")
    made = 0
    for p in SalaryProfile.objects.alive().filter(is_active=True, employee__is_active=True).select_related("employee"):
        if Payslip.objects.filter(employee=p.employee, year=year, month=month).exists():
            continue
        Payslip.objects.create(employee=p.employee, year=year, month=month, currency=p.currency, grade=p.grade, basic_salary=p.basic_salary,
                               allowances=p.allowances, gross=p.gross, paye=p.paye, nssa=p.nssa, pension=p.pension,
                               other_deductions=p.medical_aid + p.other_deductions, net=p.net, created_by=user)
        made += 1
    if made:
        notify(users_with_cap("payroll.approve", "FINANCE"), f"Payroll {month:02d}/{year} ready for approval", f"{made} payslip(s) prepared.",
               f"/staff/finance/payroll/?period={year}-{month:02d}")
    return made


@transaction.atomic
def approve_payroll(user, year: int, month: int):
    _require(user, "payroll.approve")
    drafts = Payslip.objects.alive().filter(year=year, month=month, status=Payslip.Status.DRAFT)
    if not drafts.exists():
        raise ValidationError("There are no draft payslips for this month.")
    if drafts.filter(created_by=user).exists():
        raise PermissionDenied("Segregation of duties: the person who prepared the payroll cannot approve it.")
    own = drafts.filter(employee=user).first()
    now = timezone.now()
    slips = list(drafts.exclude(employee=user).select_related("employee"))
    if own is not None:
        # nobody approves their own pay: it waits for another approver (e.g. the CEO for the Treasurer)
        notify([u for u in users_with_cap("payroll.approve") if u.pk != user.pk], f"Payslip of {user.get_full_name()} to approve – {own.period}",
               "The approver's own payslip needs a second approver.", f"/staff/finance/payroll/?period={year}-{month:02d}")
        if not slips:
            raise PermissionDenied("Only your own payslip is left – another approver must approve it.")
    for s in slips:
        s.status, s.approved_by, s.approved_at = Payslip.Status.APPROVED, user, now
        s.save()
        notify([s.employee], f"Payslip for {s.period}", f"Net pay {s.currency} {s.net:,.2f}.", "/staff/profile/")
    audit.log(AuditLog.Action.APPROVE, message=f"Payroll {month:02d}/{year} approved – {len(slips)} payslips", user=user)
    return len(slips)


@transaction.atomic
def pay_payslip(user, payslip, *, amount, method="EFT", reference="", bank_account=None):
    _require(user, "payroll.pay")
    if payslip.employee_id == user.pk:
        raise PermissionDenied("Segregation of duties: you cannot pay your own salary.")
    if payslip.status not in (Payslip.Status.APPROVED, Payslip.Status.PART):
        raise ValidationError("Only approved payslips can be paid.")
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0 or amount > payslip.balance:
        raise ValidationError(f"Enter an amount between 0.01 and the balance owed ({payslip.balance:,.2f}).")
    if method != "CASH" and not reference:
        raise ValidationError("Enter the bank / transaction reference.")
    pay = SalaryPayment.objects.create(payslip=payslip, amount=amount, method=method, reference=reference, bank_account=bank_account, paid_by=user,
                                       created_by=user)
    payslip.amount_paid = (payslip.amount_paid + amount).quantize(Decimal("0.01"))
    payslip.status = Payslip.Status.PAID if payslip.amount_paid >= payslip.net else Payslip.Status.PART
    payslip.save()
    audit.log(AuditLog.Action.PAYMENT, payslip, user=user, message=f"Salary {payslip.period}: paid {payslip.currency} {amount} ref {reference}")
    left = payslip.balance
    notify([payslip.employee], f"Salary paid – {payslip.period}",
           f"{payslip.currency} {amount:,.2f} paid" + (f". Still owed to you: {payslip.currency} {left:,.2f}." if left > 0 else ". Paid in full."),
           "/staff/profile/")
    return pay


def owed_by_employee():
    """Arrears: what the council still owes each employee (approved, not fully paid)."""
    rows = (Payslip.objects.alive().filter(status__in=[Payslip.Status.APPROVED, Payslip.Status.PART])
            .values("employee", "employee__first_name", "employee__last_name", "employee__department", "currency")
            .annotate(owed=Sum(F("net") - F("amount_paid")), months=Sum(1)).order_by("-owed"))
    return list(rows)


def period_summary(year, month):
    qs = Payslip.objects.alive().filter(year=year, month=month).exclude(status=Payslip.Status.CANCELLED)
    agg = qs.aggregate(gross=Sum("gross"), net=Sum("net"), paid=Sum("amount_paid"), paye=Sum("paye"), nssa=Sum("nssa"), pension=Sum("pension"))
    owed = sum((s.balance for s in qs), Decimal("0.00"))
    return {"count": qs.count(), "drafts": qs.filter(status=Payslip.Status.DRAFT).count(), "owed": owed,
            **{k: (v or Decimal("0.00")) for k, v in agg.items()}}


# ------------------------------------------------------------------ leave
def leave_balance(user, year=None):
    """Annual leave: days a year, taken (approved), waiting for approval and left."""
    from departments.models import LeaveRequest

    year = year or timezone.localdate().year
    annual = LeaveRequest.objects.alive().filter(employee=user, leave_type=LeaveRequest.LeaveType.ANNUAL, start_date__year=year)
    taken = sum(lv.days for lv in annual.filter(status=LeaveRequest.Status.APPROVED))
    pending = sum(lv.days for lv in annual.filter(status=LeaveRequest.Status.PENDING))
    entitled = user.annual_leave_days
    return {"year": year, "entitled": entitled, "taken": taken, "pending": pending, "left": entitled - taken - pending}
