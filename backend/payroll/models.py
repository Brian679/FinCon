"""Payroll: each employee's salary, the monthly payslips and the payments made against them.

Finance keeps the salary details up to date (no one can change their own), runs the payroll
each month, the Treasurer approves it, and payments are recorded – in full or in part – so
the council always knows how much has been paid to whom and how much is still owed.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import SequenceCounter, SyncModel

ZERO = Decimal("0.00")
MONEY = {"max_digits": 14, "decimal_places": 2}


class SalaryProfile(SyncModel):
    class Method(models.TextChoices):
        EFT = "EFT", "Bank transfer"
        CASH = "CASH", "Cash"
        MOBILE = "MOBILE", "Mobile money"

    employee = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="salary")
    grade = models.CharField("Grade / notch", max_length=30, blank=True)
    currency = models.CharField(max_length=3, default="USD", choices=[("USD", "USD"), ("ZWG", "ZWG")])
    basic_salary = models.DecimalField(**MONEY, default=ZERO)
    housing_allowance = models.DecimalField(**MONEY, default=ZERO)
    transport_allowance = models.DecimalField(**MONEY, default=ZERO)
    other_allowances = models.DecimalField(**MONEY, default=ZERO)
    paye = models.DecimalField("PAYE (tax)", **MONEY, default=ZERO, help_text="Monthly amount from the ZIMRA tax tables")
    nssa = models.DecimalField("NSSA", **MONEY, default=ZERO)
    pension = models.DecimalField("Pension (LAPF)", **MONEY, default=ZERO)
    medical_aid = models.DecimalField(**MONEY, default=ZERO)
    other_deductions = models.DecimalField(**MONEY, default=ZERO, help_text="Loans, union dues …")
    payment_method = models.CharField(max_length=6, choices=Method.choices, default=Method.EFT)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account = models.CharField("Account / mobile number", max_length=60, blank=True)
    is_active = models.BooleanField("On the payroll", default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["employee__first_name", "employee__last_name"]

    def __str__(self):
        return f"Salary – {self.employee.get_full_name() or self.employee.username}"

    @property
    def allowances(self):
        return self.housing_allowance + self.transport_allowance + self.other_allowances

    @property
    def gross(self):
        return self.basic_salary + self.allowances

    @property
    def deductions(self):
        return self.paye + self.nssa + self.pension + self.medical_aid + self.other_deductions

    @property
    def net(self):
        return self.gross - self.deductions


class Payslip(SyncModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft – awaiting approval"
        APPROVED = "APPROVED", "Approved – not yet paid"
        PART = "PART", "Part paid"
        PAID = "PAID", "Paid in full"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payslips")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    currency = models.CharField(max_length=3, default="USD")
    grade = models.CharField(max_length=30, blank=True)
    basic_salary = models.DecimalField(**MONEY, default=ZERO)
    allowances = models.DecimalField(**MONEY, default=ZERO)
    gross = models.DecimalField(**MONEY, default=ZERO)
    paye = models.DecimalField(**MONEY, default=ZERO)
    nssa = models.DecimalField(**MONEY, default=ZERO)
    pension = models.DecimalField(**MONEY, default=ZERO)
    other_deductions = models.DecimalField(**MONEY, default=ZERO, help_text="Medical aid, loans, union dues …")
    net = models.DecimalField(**MONEY, default=ZERO)
    amount_paid = models.DecimalField(**MONEY, default=ZERO)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-year", "-month", "employee__first_name"]
        constraints = [models.UniqueConstraint(fields=["employee", "year", "month"], name="one_payslip_per_month")]

    def __str__(self):
        return f"{self.reference} {self.employee.get_full_name()} {self.period}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("PAY", 5)
        super().save(*args, **kwargs)

    @property
    def period(self):
        import calendar

        return f"{calendar.month_name[self.month]} {self.year}"

    @property
    def deductions(self):
        return self.paye + self.nssa + self.pension + self.other_deductions

    @property
    def balance(self):
        """Still owed to the employee."""
        if self.status in (self.Status.DRAFT, self.Status.CANCELLED):
            return ZERO
        return self.net - self.amount_paid


class SalaryPayment(SyncModel):
    payslip = models.ForeignKey(Payslip, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(**MONEY)
    method = models.CharField(max_length=6, choices=SalaryProfile.Method.choices, default=SalaryProfile.Method.EFT)
    reference = models.CharField("Bank / transaction reference", max_length=100, blank=True)
    bank_account = models.ForeignKey("finance.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="salary_payments")
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    paid_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-paid_on", "-created_at"]

    def __str__(self):
        return f"{self.payslip.reference}: {self.amount}"
