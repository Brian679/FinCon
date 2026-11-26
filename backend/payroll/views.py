from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import cap_required, staff_required
from core.crud import run_action
from departments.models import LeaveRequest

from . import forms, services
from .models import Payslip, SalaryProfile, TaxTable

User = get_user_model()


@staff_required
def my_profile(request):
    """Everything about me: details, leave balance, salary and payslips (what I was paid, what is still owed)."""
    u = request.user
    slips = list(Payslip.objects.alive().filter(employee=u).exclude(status=Payslip.Status.DRAFT).prefetch_related("payments")[:12])
    return render(request, "payroll/profile.html", {
        "title": "My profile", "u": u, "leave": services.leave_balance(u),
        "leave_list": LeaveRequest.objects.alive().filter(employee=u).order_by("-start_date")[:8],
        "salary": getattr(u, "salary", None), "slips": slips, "owed": sum((s.balance for s in slips), Decimal("0.00")),
        "paid_year": sum((s.amount_paid for s in slips if s.year == timezone.localdate().year), Decimal("0.00")),
    })


def _period(request):
    raw = request.GET.get("period") or request.POST.get("period") or timezone.localdate().strftime("%Y-%m")
    try:
        y, m = (int(x) for x in raw.split("-"))
        date(y, m, 1)
    except ValueError:
        y, m = timezone.localdate().year, timezone.localdate().month
    return y, m


@cap_required("payroll.view", "payroll.manage")
def payroll_home(request):
    y, m = _period(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "run":
            n = run_action(request, services.run_payroll, y, m, success="Payroll prepared.")
            if n is not None:
                messages.info(request, f"{n} new payslip(s) created as drafts.")
        elif action == "approve":
            run_action(request, services.approve_payroll, y, m, success="Payroll approved – staff can see their payslips.")
        return redirect(f"{request.path}?period={y}-{m:02d}")
    slips = Payslip.objects.alive().filter(year=y, month=m).select_related("employee").order_by("employee__department", "employee__first_name")
    return render(request, "payroll/payroll.html", {
        "title": "Payroll", "slips": slips, "sum": services.period_summary(y, m), "period": f"{y}-{m:02d}",
        "period_label": date(y, m, 1).strftime("%B %Y"),
        "can_run": request.user.has_cap("payroll.manage"), "can_approve": request.user.has_cap("payroll.approve"),
        "tax_unconfirmed": TaxTable.objects.alive().filter(confirmed=False).exists(),
    })


@staff_required
def payslip_detail(request, pk):
    slip = get_object_or_404(services.payslip_scope(request.user, Payslip.objects.alive()).select_related("employee"), pk=pk)
    if request.method == "POST":
        from finance.models import BankAccount

        bank = BankAccount.objects.filter(pk=request.POST.get("bank_account") or None).first()
        run_action(request, services.pay_payslip, slip, amount=request.POST.get("amount") or "0", method=request.POST.get("method", "EFT"),
                   reference=request.POST.get("reference", "").strip(), bank_account=bank, success="Payment recorded – the employee is notified.")
        return redirect("payroll:payslip", pk=pk)
    from finance.models import BankAccount

    return render(request, "payroll/payslip.html", {
        "title": str(slip), "s": slip, "payments": slip.payments.alive().select_related("paid_by"),
        "can_pay": request.user.has_cap("payroll.pay") and slip.status in ("APPROVED", "PART") and slip.employee_id != request.user.pk,
        "banks": BankAccount.objects.alive().filter(is_active=True, currency=slip.currency), "methods": SalaryProfile.Method.choices,
    })


@cap_required("payroll.view", "payroll.manage")
def salaries(request):
    staff = User.objects.filter(user_type=User.UserType.STAFF, is_active=True).select_related("salary").order_by("department", "first_name")
    return render(request, "payroll/salaries.html", {"title": "Salaries", "staff": staff, "can_edit": request.user.has_cap("payroll.manage")})


@cap_required("payroll.manage")
def salary_edit(request, user_id):
    emp = get_object_or_404(User, pk=user_id, user_type=User.UserType.STAFF)
    if emp.pk == request.user.pk:
        raise PermissionDenied("Someone else in Finance must change your own salary.")
    profile = getattr(emp, "salary", None)
    form = forms.SalaryForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        if run_action(request, services.update_salary, emp, success="Salary saved (recorded in the audit trail).", **form.cleaned_data):
            return redirect("payroll:salaries")
    return render(request, "generic/form.html", {"form": form, "title": f"Salary – {emp.get_full_name()} ({emp.role_label})"})


@cap_required("payroll.view", "payroll.manage")
def tax_tables(request):
    """The ZIMRA PAYE tables in use (the Treasurer keeps them up to date) and a PAYE calculator."""
    from django.forms import inlineformset_factory

    from core.crud import BaseModelForm

    from . import tax
    from .models import TaxBand, TaxTable

    class TableForm(BaseModelForm):
        class Meta:
            model = TaxTable
            fields = ["name", "currency", "effective_from", "aids_levy_rate", "nssa_rate", "nssa_ceiling", "pension_cap", "confirmed", "source"]

    Bands = inlineformset_factory(TaxTable, TaxBand, fields=["lower", "upper", "rate"], extra=2, can_delete=True)
    can_edit = request.user.has_cap("payroll.approve")
    table = TaxTable.objects.alive().filter(pk=request.GET.get("table")).first() if request.GET.get("table") else tax.table_for("USD")
    if request.GET.get("new") and can_edit:
        table = None
    form = TableForm(request.POST or None, instance=table, prefix="t")
    bands = Bands(request.POST or None, instance=table or TaxTable(), prefix="b")
    if request.method == "POST" and request.POST.get("action") == "save":
        if not can_edit:
            raise PermissionDenied("Only the Treasurer can change the tax tables.")
        if form.is_valid() and bands.is_valid():
            t = form.save(commit=False)
            t.created_by = t.created_by or request.user
            t.save()
            bands.instance = t
            bands.save()
            from core import audit
            from core.models import AuditLog

            audit.log(AuditLog.Action.UPDATE, t, user=request.user, message="PAYE tax table saved: " + "; ".join(str(b) for b in t.bands.all()))
            messages.success(request, "Tax table saved. New payrolls use it from its effective date.")
            return redirect(f"{request.path}?table={t.pk}")
    result = None
    calc = {"gross": request.GET.get("gross", ""), "pension": request.GET.get("pension", ""), "credits": request.GET.get("credits", "")}
    if calc["gross"] and table:
        try:
            result = tax.calculate(Decimal(calc["gross"]), pension=Decimal(calc["pension"] or 0), credits=Decimal(calc["credits"] or 0), table=table)
        except (ArithmeticError, ValueError):
            messages.error(request, "Enter amounts as numbers.")
    return render(request, "payroll/tax.html", {"title": "PAYE tax tables", "form": form, "bands": bands, "table": table, "can_edit": can_edit,
                                                "tables": TaxTable.objects.alive(), "result": result, "calc": calc})


@cap_required("payroll.view", "payroll.manage")
def arrears(request):
    return render(request, "payroll/arrears.html", {"title": "Salaries owed to staff", "rows": services.owed_by_employee()})
