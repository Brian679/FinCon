"""Finance department: revenue (incoming money), expenditure (outgoing money),
procurement, budgets, licences and online payments.

All monetary ledgers are kept in the council's base currency (USD). Every
transaction also records the currency actually tendered, the amount in that
currency and the exchange rate used.
"""
import builtins
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import Currency, Department, SequenceCounter, SyncModel

MONEY = dict(max_digits=14, decimal_places=2)
POSITIVE = [MinValueValidator(Decimal("0.01"))]
ZERO = Decimal("0.00")


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def current_year():
    return timezone.localdate().year


class ExchangeRate(models.Model):
    """Units of ``currency`` per 1 USD, set by the Treasurer."""

    currency = models.CharField(max_length=3, choices=Currency.choices)
    rate = models.DecimalField(max_digits=14, decimal_places=4, validators=POSITIVE)
    effective_date = models.DateField(default=timezone.localdate)
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-id"]

    def __str__(self):
        return f"1 USD = {self.rate} {self.currency} ({self.effective_date})"

    @classmethod
    def rate_for(cls, currency, on_date=None):
        if currency == settings.COUNCIL["BASE_CURRENCY"]:
            return Decimal("1")
        on_date = on_date or timezone.localdate()
        rate = cls.objects.filter(currency=currency, effective_date__lte=on_date).first()
        if rate is None:
            raise ValueError(f"No exchange rate has been set for {currency}. Ask the Treasurer to capture one.")
        return rate.rate


class BudgetLine(SyncModel):
    class Kind(models.TextChoices):
        INCOME = "INCOME", "Income"
        EXPENDITURE = "EXPENDITURE", "Expenditure"
        CAPITAL = "CAPITAL", "Capital expenditure"

    financial_year = models.PositiveSmallIntegerField(default=current_year, db_index=True)
    vote_code = models.CharField(max_length=20)
    description = models.CharField(max_length=200)
    department = models.CharField(max_length=10, choices=Department.choices)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    approved_amount = models.DecimalField(**MONEY, default=ZERO)
    revised_amount = models.DecimalField(**MONEY, null=True, blank=True)

    class Meta:
        ordering = ["financial_year", "vote_code"]
        unique_together = [("financial_year", "vote_code")]

    def __str__(self):
        return f"{self.vote_code} {self.description} ({self.financial_year})"

    @property
    def budget(self):
        return self.revised_amount if self.revised_amount is not None else self.approved_amount

    def actual(self):
        if self.kind == self.Kind.INCOME:
            total = Receipt.objects.alive().filter(
                revenue_head__budget_line=self, status__in=Receipt.COUNTABLE, created_at__year=self.financial_year
            ).aggregate(t=Sum("base_amount"))["t"]
        else:
            total = PaymentVoucher.objects.alive().filter(budget_line=self, status=PaymentVoucher.Status.PAID).aggregate(
                t=Sum("base_amount")
            )["t"]
        return q2(total)

    def committed(self):
        if self.kind == self.Kind.INCOME:
            return ZERO
        vouchers = PaymentVoucher.objects.alive().filter(
            budget_line=self,
            status__in=[PaymentVoucher.Status.PREPARED, PaymentVoucher.Status.CHECKED, PaymentVoucher.Status.APPROVED,
                        PaymentVoucher.Status.AUTHORISED],
        ).aggregate(t=Sum("base_amount"))["t"]
        reqs = Requisition.objects.alive().filter(
            budget_line=self,
            status__in=[Requisition.Status.FINANCE_CHECKED, Requisition.Status.APPROVED, Requisition.Status.AUTHORISED],
        ).aggregate(t=Sum("total"))["t"]
        return q2(vouchers) + q2(reqs)

    def available(self):
        return q2(self.budget) - self.actual() - self.committed()

    def utilisation_pct(self):
        if not self.budget:
            return 0
        return round(float((self.actual() + self.committed()) / self.budget * 100), 1)


class RevenueHead(SyncModel):
    class Category(models.TextChoices):
        RATES = "RATES", "Property / land rates"
        LEVY = "LEVY", "Levies (development, unit tax ...)"
        LICENCE = "LICENCE", "Licences"
        RENT = "RENT", "Rentals & leases"
        FEES = "FEES", "Fees & charges"
        FINES = "FINES", "Fines & penalties"
        WATER = "WATER", "Water & sanitation"
        LAND = "LAND", "Stand sales / land"
        OTHER = "OTHER", "Other income"

    class Frequency(models.TextChoices):
        ONCE = "ONCE", "Once-off"
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        ANNUAL = "ANNUAL", "Annual"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=10, choices=Category.choices)
    default_amount = models.DecimalField(**MONEY, default=ZERO)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.ONCE)
    budget_line = models.ForeignKey(BudgetLine, null=True, blank=True, on_delete=models.SET_NULL, related_name="revenue_heads")
    payable_online = models.BooleanField(default=True, help_text="Clients may pay this from the client app / portal")
    per_hectare = models.BooleanField(default=False, help_text="Levy charged per hectare (farms): amount × hectares")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class BankAccount(SyncModel):
    name = models.CharField(max_length=120)
    bank = models.CharField(max_length=120)
    account_number = models.CharField(max_length=40)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    opening_balance = models.DecimalField(**MONEY, default=ZERO)
    opening_date = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.bank} {self.account_number}, {self.currency})"

    def receipts_total(self):
        return q2(self.receipts.alive().filter(status__in=Receipt.COUNTABLE).aggregate(t=Sum("amount"))["t"])

    def payments_total(self):
        return q2(self.vouchers.alive().filter(status=PaymentVoucher.Status.PAID).aggregate(t=Sum("amount"))["t"])

    def balance(self):
        return q2(self.opening_balance) + self.receipts_total() - self.payments_total()


class TradingArea(SyncModel):
    """A shopping / business centre, growth point, township or market where
    council stands, shops and stalls are located."""

    class Kind(models.TextChoices):
        SHOPPING_CENTRE = "SC", "Shopping / business centre"
        GROWTH_POINT = "GP", "Growth point"
        TOWNSHIP = "TS", "Township / residential area"
        MARKET = "MKT", "Market / vending site"
        SERVICE_CENTRE = "RSC", "Rural service centre"
        FARMING = "FARM", "Farming / plantation area"

    name = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=4, choices=Kind.choices, default=Kind.SHOPPING_CENTRE)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()}, Ward {self.ward or '-'})"


class ClientAccount(SyncModel):
    """A ratepayer / customer account (individual, business or institution)."""

    class AccountType(models.TextChoices):
        INDIVIDUAL = "IND", "Individual / household"
        BUSINESS = "BUS", "Business"
        INSTITUTION = "INST", "Institution / school / church"
        FARM = "FARM", "Farm / plantation"
        GOVERNMENT = "GOV", "Government"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        CLOSED = "CLOSED", "Closed"

    account_number = models.CharField(max_length=20, unique=True, editable=False)
    account_type = models.CharField(max_length=5, choices=AccountType.choices, default=AccountType.INDIVIDUAL)
    name = models.CharField(max_length=200)
    id_number = models.CharField("National ID / company reg. no.", max_length=40, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    postal_address = models.CharField(max_length=255, blank=True)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    balance = models.DecimalField(**MONEY, default=ZERO, editable=False, help_text="Amount owed (USD). Negative = credit.")
    portal_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="client_accounts")

    class Meta:
        ordering = ["account_number"]

    def __str__(self):
        return f"{self.account_number} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.account_number:
            self.account_number = SequenceCounter.next("ACC", 5).replace("ACC-", "CR")
        super().save(*args, **kwargs)

    def recalculate(self):
        """Recompute the balance and allocate payments to bills (oldest first)."""
        bills = list(self.bills.alive().exclude(status=Bill.Status.CANCELLED).order_by("due_date", "created_at"))
        countable = self.receipts.alive().filter(status__in=Receipt.COUNTABLE)
        paid = q2(countable.aggregate(t=Sum("base_amount"))["t"])
        # 1) a payment made against a particular bill (e.g. the licence fee) goes to that bill first …
        earmarked = {row["bill"]: q2(row["t"]) for row in countable.filter(bill__isnull=False).values("bill").annotate(t=Sum("base_amount"))}
        allocation = {}
        live = {b.pk for b in bills}
        pool = paid - sum((v for k, v in earmarked.items() if k in live), ZERO)   # money on cancelled bills stays in the pool
        for bill in bills:
            own = earmarked.get(bill.pk, ZERO)
            allocation[bill.pk] = min(own, bill.amount)
            pool += own - allocation[bill.pk]          # overpayment of a bill joins the general pool
        # 2) … and everything else pays the oldest bills first.
        for bill in bills:
            gap = bill.amount - allocation[bill.pk]
            take = min(max(pool, ZERO), gap)
            allocation[bill.pk] += take
            pool -= take
        for bill in bills:
            alloc = allocation[bill.pk]
            status = Bill.Status.PAID if alloc >= bill.amount else (Bill.Status.PART_PAID if alloc > 0 else Bill.Status.UNPAID)
            if bill.amount_paid != alloc or bill.status != status:
                bill.amount_paid = alloc
                bill.status = status
                bill.save(update_fields=["amount_paid", "status", "updated_at"])
        billed = sum((b.amount for b in bills), ZERO)
        new_balance = q2(billed - paid)
        if new_balance != self.balance:
            self.balance = new_balance
            self.save(update_fields=["balance", "updated_at"])
        return self.balance


class Property(SyncModel):
    class LandUse(models.TextChoices):
        RESIDENTIAL = "RES", "Residential"
        COMMERCIAL = "COM", "Commercial"
        INDUSTRIAL = "IND", "Industrial"
        INSTITUTIONAL = "INST", "Institutional"
        AGRICULTURAL = "AGR", "Agricultural / farm"

    account = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="properties")
    area = models.ForeignKey(TradingArea, null=True, blank=True, on_delete=models.PROTECT, related_name="properties")
    stand_number = models.CharField(max_length=40)
    business_name = models.CharField(max_length=200, blank=True, help_text="Shop / business trading at this stand")
    location = models.CharField(max_length=200, help_text="Township / business centre / village")
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    land_use = models.CharField(max_length=4, choices=LandUse.choices, default=LandUse.RESIDENTIAL)
    size_sqm = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hectares = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                   help_text="Farms: size in hectares – the farm levy is charged per hectare")
    valuation = models.DecimalField(**MONEY, default=ZERO)
    monthly_rates = models.DecimalField(**MONEY, default=ZERO, help_text="Monthly rates charge (USD)")
    is_council_owned = models.BooleanField(default=False, help_text="Council-owned premises let out on lease")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["location", "stand_number"]
        verbose_name_plural = "properties"
        unique_together = [("location", "stand_number")]

    def __str__(self):
        kind = "Farm" if self.hectares else "Stand"
        return f"{kind} {self.stand_number}, {self.location}"


class Bill(SyncModel):
    """A charge raised against a client account (rates, levies, licence fees...)."""

    class Status(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PART_PAID = "PART", "Partly paid"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=30, unique=True, editable=False)
    account = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="bills")
    property = models.ForeignKey(Property, null=True, blank=True, on_delete=models.PROTECT, related_name="bills")
    revenue_head = models.ForeignKey(RevenueHead, on_delete=models.PROTECT, related_name="bills")
    description = models.CharField(max_length=255)
    period = models.CharField(max_length=7, blank=True, help_text="YYYY-MM for periodic charges")
    amount = models.DecimalField(**MONEY, validators=POSITIVE)
    amount_paid = models.DecimalField(**MONEY, default=ZERO, editable=False)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID, db_index=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "property", "revenue_head", "period"],
                condition=~Q(period="") & Q(is_deleted=False) & ~Q(status="CANCELLED"),
                name="unique_periodic_bill",
            )
        ]

    def __str__(self):
        return f"{self.number} {self.description} ${self.amount}"

    @builtins.property
    def outstanding(self):
        return q2(self.amount - self.amount_paid) if self.status != self.Status.CANCELLED else ZERO

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("INV")
        super().save(*args, **kwargs)


class CashUp(SyncModel):
    """End-of-day cash declaration by a cashier, verified by the Accountant."""

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        VERIFIED = "VERIFIED", "Verified"
        QUERIED = "QUERIED", "Queried"

    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cashups")
    date = models.DateField(default=timezone.localdate)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    expected_cash = models.DecimalField(**MONEY, default=ZERO, editable=False)
    declared_cash = models.DecimalField(**MONEY, default=ZERO)
    expected_other = models.DecimalField(**MONEY, default=ZERO, editable=False, help_text="Non-cash receipts")
    variance = models.DecimalField(**MONEY, default=ZERO, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)
    notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"Cash-up {self.date} {self.cashier} {self.currency}"


class Receipt(SyncModel):
    """Incoming money. Receipts are never edited or deleted - only voided
    through a two-person request / approve process."""

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        ECOCASH = "ECOCASH", "EcoCash"
        ONEMONEY = "ONEMONEY", "OneMoney"
        INNBUCKS = "INNBUCKS", "InnBucks"
        SWIPE = "SWIPE", "Card / swipe (POS)"
        BANK = "BANK", "Bank transfer / deposit"
        ONLINE = "ONLINE", "Online (Paynow)"

    class Channel(models.TextChoices):
        COUNTER = "COUNTER", "Council counter"
        FIELD = "FIELD", "Field officer (mobile)"
        PORTAL = "PORTAL", "Client web portal"
        CLIENT_APP = "CLIENT_APP", "Client mobile app"

    class Status(models.TextChoices):
        VALID = "VALID", "Valid"
        VOID_REQUESTED = "VOID_REQ", "Void requested"
        VOIDED = "VOIDED", "Voided"

    COUNTABLE = [Status.VALID, Status.VOID_REQUESTED]

    number = models.CharField(max_length=30, unique=True, editable=False)
    account = models.ForeignKey(ClientAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="receipts")
    payer_name = models.CharField(max_length=200)
    revenue_head = models.ForeignKey(RevenueHead, on_delete=models.PROTECT, related_name="receipts")
    bill = models.ForeignKey(Bill, null=True, blank=True, on_delete=models.PROTECT, related_name="receipts")
    description = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    amount = models.DecimalField(**MONEY, validators=POSITIVE, help_text="Amount in the currency tendered")
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1"), editable=False)
    base_amount = models.DecimalField(**MONEY, default=ZERO, editable=False, help_text="Equivalent in USD")
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.CASH)
    reference = models.CharField(max_length=100, blank=True, help_text="Mobile money / bank / POS reference")
    bank_account = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="receipts")
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.COUNTER)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="receipts_issued")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.VALID, db_index=True)
    void_reason = models.CharField(max_length=255, blank=True)
    void_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    voided_at = models.DateTimeField(null=True, blank=True)
    cashup = models.ForeignKey(CashUp, null=True, blank=True, on_delete=models.SET_NULL, related_name="receipts")
    offline_created_at = models.DateTimeField(null=True, blank=True, help_text="When captured on a device that was offline")
    device_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.currency} {self.amount} - {self.payer_name}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("RCT")
        if self._state.adding:
            self.exchange_rate = ExchangeRate.rate_for(self.currency)
            self.base_amount = q2(Decimal(self.amount) / self.exchange_rate)
        super().save(*args, **kwargs)


class Licence(SyncModel):
    """Shop, hawker, business and other licences issued by council."""

    class LicenceType(models.TextChoices):
        SHOP = "SHOP", "Shop licence"
        HAWKER = "HAWKER", "Hawker / vendor licence"
        BUSINESS = "BUSINESS", "General business licence"
        LIQUOR = "LIQUOR", "Liquor (council recommendation)"
        HEALTH = "HEALTH", "Health / food handling certificate"
        TRANSPORT = "TRANSPORT", "Public transport rank permit"
        ADVERT = "ADVERT", "Advertising / billboard permit"

    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Application received"
        INSPECTION = "INSPECTION", "Awaiting inspection"
        INSPECTED = "INSPECTED", "Inspected - passed"
        FAILED = "FAILED", "Inspected - failed"
        APPROVED = "APPROVED", "Awaiting payment"
        ISSUED = "ISSUED", "Issued / active"
        REJECTED = "REJECTED", "Rejected"
        EXPIRED = "EXPIRED", "Expired"

    number = models.CharField(max_length=30, unique=True, editable=False)
    licence_type = models.CharField(max_length=10, choices=LicenceType.choices, default=LicenceType.SHOP)
    account = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="licences")
    property = models.ForeignKey("Property", null=True, blank=True, on_delete=models.SET_NULL, related_name="licences",
                                 help_text="The stand / shop the licence is for")
    business_name = models.CharField(max_length=200)
    business_activity = models.CharField(max_length=200, blank=True)
    premises = models.CharField(max_length=255, help_text="Premises / stand / trading site")
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="licence_applications")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPLIED, db_index=True)
    fee = models.DecimalField(**MONEY, default=ZERO)
    revenue_head = models.ForeignKey(RevenueHead, null=True, blank=True, on_delete=models.PROTECT, related_name="licences")
    bill = models.ForeignKey(Bill, null=True, blank=True, on_delete=models.PROTECT, related_name="licences")
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    inspection_notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    rejection_reason = models.CharField(max_length=255, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    renewal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals")
    due_at = models.DateTimeField(null=True, blank=True, help_text="Charter: process applications within 30 working days")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.get_licence_type_display()} - {self.business_name}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("LIC", 5)
        super().save(*args, **kwargs)

    @builtins.property
    def is_active(self):
        return self.status == self.Status.ISSUED and self.expiry_date and self.expiry_date >= timezone.localdate()


class Supplier(SyncModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        BLACKLISTED = "BLACKLISTED", "Blacklisted"

    code = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True, help_text="e.g. Stationery, Fuel, Construction")
    contact_person = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    tax_number = models.CharField("BP / tax number", max_length=40, blank=True)
    prazcode = models.CharField("PRAZ registration no.", max_length=40, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} {self.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = SequenceCounter.next("SUP", 4)
        super().save(*args, **kwargs)


class Requisition(SyncModel):
    """Purchase requisition raised by any department.

    Workflow: DRAFT -> SUBMITTED -> HOD_APPROVED -> FINANCE_CHECKED (funds
    available, by Accountant) -> APPROVED (Treasurer) -> AUTHORISED (CEO, only
    at/above the CEO threshold) -> ORDERED.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted to Head of Department"
        HOD_APPROVED = "HOD_OK", "HOD approved - awaiting funds check"
        FINANCE_CHECKED = "FIN_OK", "Funds confirmed - awaiting Treasurer"
        APPROVED = "APPROVED", "Approved by Treasurer"
        AUTHORISED = "AUTHORISED", "Authorised by CEO"
        ORDERED = "ORDERED", "Purchase order issued"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=30, unique=True, editable=False)
    department = models.CharField(max_length=10, choices=Department.choices)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requisitions")
    purpose = models.TextField()
    budget_line = models.ForeignKey(BudgetLine, null=True, blank=True, on_delete=models.PROTECT, related_name="requisitions")
    total = models.DecimalField(**MONEY, default=ZERO, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.get_department_display()} ${self.total}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("REQ", 5)
        super().save(*args, **kwargs)

    def recalc_total(self):
        self.total = q2(sum((i.total for i in self.items.all()), ZERO))
        self.save(update_fields=["total", "updated_at"])

    @property
    def needs_ceo(self):
        return self.total >= Decimal(str(settings.CEO_APPROVAL_THRESHOLD))

    @property
    def is_ready_for_order(self):
        return self.status == self.Status.AUTHORISED or (self.status == self.Status.APPROVED and not self.needs_ceo)


class RequisitionItem(models.Model):
    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"), validators=POSITIVE)
    unit_cost = models.DecimalField(**MONEY, validators=POSITIVE)

    @property
    def total(self):
        return q2(self.quantity * self.unit_cost)

    def __str__(self):
        return f"{self.quantity} x {self.description}"


class PurchaseOrder(SyncModel):
    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued to supplier"
        DELIVERED = "DELIVERED", "Goods / services received"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=30, unique=True, editable=False)
    requisition = models.OneToOneField(Requisition, on_delete=models.PROTECT, related_name="purchase_order")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    amount = models.DecimalField(**MONEY, validators=POSITIVE)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    expected_delivery = models.DateField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.supplier.name} {self.currency} {self.amount}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("PO", 5)
        super().save(*args, **kwargs)


class PaymentVoucher(SyncModel):
    """Outgoing money.

    Workflow with segregation of duties: PREPARED (clerk) -> CHECKED
    (Accountant) -> APPROVED (Treasurer) -> AUTHORISED (CEO, at/above
    threshold) -> PAID. The same person may not perform two stages.
    """

    class Status(models.TextChoices):
        PREPARED = "PREPARED", "Prepared"
        CHECKED = "CHECKED", "Checked by Accountant"
        APPROVED = "APPROVED", "Approved by Treasurer"
        AUTHORISED = "AUTHORISED", "Authorised by CEO"
        PAID = "PAID", "Paid"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    class Method(models.TextChoices):
        EFT = "EFT", "Bank transfer (RTGS / EFT)"
        CHEQUE = "CHEQUE", "Cheque"
        CASH = "CASH", "Cash (petty cash)"
        MOBILE = "MOBILE", "Mobile money"

    class Category(models.TextChoices):
        SUPPLIER = "SUPPLIER", "Supplier / contractor"
        SALARIES = "SALARIES", "Salaries & wages"
        ALLOWANCES = "ALLOW", "Allowances & subsistence"
        STATUTORY = "STATUTORY", "Statutory (ZIMRA, NSSA, pension)"
        UTILITIES = "UTILITIES", "Utilities"
        REFUND = "REFUND", "Refund to client"
        OTHER = "OTHER", "Other"

    number = models.CharField(max_length=30, unique=True, editable=False)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.SUPPLIER)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT, related_name="vouchers")
    payee_name = models.CharField(max_length=200)
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="vouchers")
    budget_line = models.ForeignKey(BudgetLine, null=True, blank=True, on_delete=models.PROTECT, related_name="vouchers")
    department = models.CharField(max_length=10, choices=Department.choices, default=Department.FINANCE)
    description = models.TextField()
    invoice_number = models.CharField("Supplier invoice no.", max_length=60, blank=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    amount = models.DecimalField(**MONEY, validators=POSITIVE)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1"), editable=False)
    base_amount = models.DecimalField(**MONEY, default=ZERO, editable=False)
    method = models.CharField(max_length=7, choices=Method.choices, default=Method.EFT)
    bank_account = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="vouchers")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PREPARED, db_index=True)
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vouchers_prepared")
    payment_reference = models.CharField(max_length=100, blank=True, help_text="Cheque / RTGS / transaction number")
    paid_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} {self.payee_name} {self.currency} {self.amount}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("PV", 5)
        if self.status in (self.Status.PREPARED,) or self._state.adding:
            self.exchange_rate = ExchangeRate.rate_for(self.currency)
            self.base_amount = q2(Decimal(self.amount) / self.exchange_rate)
        super().save(*args, **kwargs)

    @property
    def needs_ceo(self):
        return self.base_amount >= Decimal(str(settings.CEO_APPROVAL_THRESHOLD))

    @property
    def is_ready_for_payment(self):
        return self.status == self.Status.AUTHORISED or (self.status == self.Status.APPROVED and not self.needs_ceo)


class ApprovalRecord(models.Model):
    """History of every workflow decision on requisitions, vouchers,
    licences and receipt voids (who, what, when, why)."""

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64, db_index=True)
    document = GenericForeignKey("content_type", "object_id")
    stage = models.CharField(max_length=40)
    decision = models.CharField(max_length=20)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    comment = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["timestamp", "id"]

    def __str__(self):
        return f"{self.stage}: {self.decision} by {self.user}"

    @classmethod
    def for_object(cls, obj):
        return cls.objects.filter(content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk)).select_related("user")


class OnlinePayment(SyncModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Awaiting confirmation"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    account = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="online_payments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="online_payments")
    bill = models.ForeignKey(Bill, null=True, blank=True, on_delete=models.PROTECT, related_name="online_payments")
    revenue_head = models.ForeignKey(RevenueHead, on_delete=models.PROTECT)
    amount = models.DecimalField(**MONEY, validators=POSITIVE)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    method = models.CharField(max_length=10, choices=Receipt.Method.choices, default=Receipt.Method.ECOCASH)
    phone = models.CharField(max_length=30, blank=True)
    provider = models.CharField(max_length=20, default="simulated")
    provider_reference = models.CharField(max_length=100, blank=True)
    poll_url = models.URLField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    receipt = models.OneToOneField(Receipt, null=True, blank=True, on_delete=models.PROTECT, related_name="online_payment")
    channel = models.CharField(max_length=10, choices=Receipt.Channel.choices, default=Receipt.Channel.PORTAL)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.reference} {self.currency} {self.amount} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("PAY")
        super().save(*args, **kwargs)


class Lease(SyncModel):
    """Lease of council-owned premises (shops, market stalls, land, offices)."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        TERMINATED = "TERMINATED", "Terminated"

    number = models.CharField(max_length=30, unique=True, editable=False)
    lessee = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="leases")
    premises = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="leases")
    purpose = models.CharField(max_length=200, help_text="e.g. Retail shop, market stall, office")
    monthly_rent = models.DecimalField(**MONEY, validators=POSITIVE)
    deposit = models.DecimalField(**MONEY, default=ZERO)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.number} {self.premises} – {self.lessee.name}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("LSE", 5)
        super().save(*args, **kwargs)

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.status == self.Status.ACTIVE and self.start_date <= today <= self.end_date


class AccountClaim(SyncModel):
    """A client asks to have a stand / shop linked to their online account.

    If the stand is already in the register and the phone / ID matches, the
    link is approved automatically; otherwise a revenue officer checks it and
    approves (linking to an existing account, or registering a new one)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Waiting for council verification"
        APPROVED = "APPROVED", "Approved – linked to your account"
        REJECTED = "REJECTED", "Rejected"

    class ClaimType(models.TextChoices):
        OWNER = "OWNER", "I own / occupy this stand"
        SHOP = "SHOP", "I run a shop / business at this stand"
        TENANT = "TENANT", "I lease these council premises"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account_claims")
    claim_type = models.CharField(max_length=6, choices=ClaimType.choices, default=ClaimType.OWNER)
    stand_number = models.CharField(max_length=40)
    area = models.ForeignKey(TradingArea, null=True, blank=True, on_delete=models.SET_NULL, related_name="claims")
    location = models.CharField(max_length=200, blank=True, help_text="Township / business centre if not in the list")
    business_name = models.CharField(max_length=200, blank=True)
    id_number = models.CharField("National ID / company reg. no.", max_length=40, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True)
    matched_property = models.ForeignKey(Property, null=True, blank=True, on_delete=models.SET_NULL, related_name="claims")
    account = models.ForeignKey(ClientAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="claims")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} stand {self.stand_number} – {self.user}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("CLM", 5)
        super().save(*args, **kwargs)


# ------------------------------------------------------------ fines & penalties
class Offence(SyncModel):
    """Schedule of by-law offences and their standard fines (set by council)."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    by_law = models.CharField(max_length=200, blank=True, help_text="By-law / section")
    default_fine = models.DecimalField(**MONEY, validators=POSITIVE)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} – {self.name} (${self.default_fine})"


class Fine(SyncModel):
    """A fine issued for a by-law offence. It is billed to the offender's council account and
    becomes PAID by itself when the bill is paid. Waiving needs the Treasurer / CEO (not the issuer)."""

    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued – unpaid"
        PAID = "PAID", "Paid"
        WAIVED = "WAIVED", "Waived"
        COURT = "COURT", "Referred to court"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    offence = models.ForeignKey(Offence, on_delete=models.PROTECT, related_name="fines")
    account = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="fines")
    offender_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    vehicle_reg = models.CharField(max_length=20, blank=True)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200)
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(**MONEY, validators=POSITIVE)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ISSUED, db_index=True)
    bill = models.ForeignKey(Bill, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decision_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.reference} {self.offender_name} – {self.offence.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("FIN", 5)
        super().save(*args, **kwargs)
