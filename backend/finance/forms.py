from django import forms
from django.forms import inlineformset_factory

from core.crud import BaseModelForm, BootstrapFormMixin, date_widgets
from django.utils import timezone

from core.models import Currency

from .models import (
    BankAccount, Bill, BudgetLine, ClientAccount, ExchangeRate, Licence, Offence, PaymentVoucher, Property, PurchaseOrder,
    Receipt, Requisition, RequisitionItem, RevenueHead, Supplier,
)


class ReceiptForm(BootstrapFormMixin, forms.Form):
    account = forms.ModelChoiceField(queryset=ClientAccount.objects.alive().exclude(status="CLOSED"), required=False,
                                     help_text="Leave blank for a walk-in / once-off payment.")
    bill = forms.ModelChoiceField(queryset=Bill.objects.alive().filter(status__in=["UNPAID", "PART"]), required=False)
    payer_name = forms.CharField(max_length=200, required=False)
    revenue_head = forms.ModelChoiceField(queryset=RevenueHead.objects.alive().filter(is_active=True))
    currency = forms.ChoiceField(choices=Currency.choices)
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0.01)
    method = forms.ChoiceField(choices=[c for c in Receipt.Method.choices if c[0] != "ONLINE"])
    reference = forms.CharField(max_length=100, required=False, help_text="Required for EcoCash, swipe and bank payments")
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.alive().filter(is_active=True), required=False)
    description = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].widget.attrs["data-search"] = "1"


class ClientAccountForm(BaseModelForm):
    class Meta:
        model = ClientAccount
        fields = ["account_type", "name", "id_number", "phone", "email", "postal_address", "ward", "status"]


class PropertyForm(BaseModelForm):
    class Meta:
        model = Property
        fields = ["stand_number", "location", "ward", "land_use", "size_sqm", "hectares", "valuation", "monthly_rates", "is_active"]


class BillForm(BaseModelForm):
    class Meta:
        model = Bill
        fields = ["revenue_head", "property", "description", "amount", "due_date"]
        widgets = date_widgets("due_date")


class BillingRunForm(BootstrapFormMixin, forms.Form):
    year = forms.IntegerField(min_value=2020, max_value=2100)
    month = forms.IntegerField(min_value=1, max_value=12)


class LicenceForm(BaseModelForm):
    class Meta:
        model = Licence
        fields = ["account", "property", "licence_type", "business_name", "business_activity", "premises", "ward"]
        help_texts = {"property": "The stand / shop (links the licence to the area paid/unpaid board)"}


class SupplierForm(BaseModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "category", "contact_person", "phone", "email", "address", "tax_number", "prazcode", "bank_name", "bank_account", "status"]


class RequisitionForm(BaseModelForm):
    class Meta:
        model = Requisition
        fields = ["purpose", "budget_line"]

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = BudgetLine.objects.alive().exclude(kind=BudgetLine.Kind.INCOME)
        if department:
            qs = qs.filter(department=department)
        self.fields["budget_line"].queryset = qs


class ItemForm(BaseModelForm):
    class Meta:
        model = RequisitionItem
        fields = ["description", "quantity", "unit_cost"]

    def has_changed(self):
        # A blank spare row (only the default quantity filled in) is ignored.
        return bool(self.data.get(self.add_prefix("description"))) or (self.instance.pk is not None and super().has_changed())


ItemFormSet = inlineformset_factory(Requisition, RequisitionItem, form=ItemForm, extra=3, can_delete=True, min_num=1, validate_min=True)


class PurchaseOrderForm(BootstrapFormMixin, forms.Form):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.alive().filter(status=Supplier.Status.ACTIVE))
    amount = forms.DecimalField(max_digits=14, decimal_places=2, required=False, help_text="Defaults to the approved total")
    expected_delivery = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(required=False, widget=forms.Textarea)


class VoucherForm(BaseModelForm):
    class Meta:
        model = PaymentVoucher
        fields = ["category", "purchase_order", "supplier", "payee_name", "department", "budget_line", "description",
                  "invoice_number", "currency", "amount", "method"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["purchase_order"].queryset = PurchaseOrder.objects.alive().filter(status=PurchaseOrder.Status.DELIVERED)
        self.fields["supplier"].queryset = Supplier.objects.alive().filter(status=Supplier.Status.ACTIVE)
        self.fields["budget_line"].queryset = BudgetLine.objects.alive().exclude(kind=BudgetLine.Kind.INCOME)
        self.fields["payee_name"].required = False
        self.fields["payee_name"].help_text = "Filled from the supplier if left blank"


class PayVoucherForm(BootstrapFormMixin, forms.Form):
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.alive().filter(is_active=True))
    payment_reference = forms.CharField(max_length=100)


class BudgetLineForm(BaseModelForm):
    class Meta:
        model = BudgetLine
        fields = ["financial_year", "vote_code", "description", "department", "kind", "approved_amount", "revised_amount"]


class BankAccountForm(BaseModelForm):
    class Meta:
        model = BankAccount
        fields = ["name", "bank", "account_number", "currency", "opening_balance", "opening_date", "is_active"]
        widgets = date_widgets("opening_date")


class ExchangeRateForm(BaseModelForm):
    class Meta:
        model = ExchangeRate
        fields = ["currency", "rate", "effective_date"]
        widgets = date_widgets("effective_date")


class RevenueHeadForm(BaseModelForm):
    class Meta:
        model = RevenueHead
        fields = ["code", "name", "category", "default_amount", "per_hectare", "frequency", "budget_line", "payable_online", "is_active"]


class CashUpForm(BootstrapFormMixin, forms.Form):
    currency = forms.ChoiceField(choices=Currency.choices)
    declared_cash = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, label="Cash counted in drawer")
    notes = forms.CharField(required=False, widget=forms.Textarea)


class CommentForm(BootstrapFormMixin, forms.Form):
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


from .models import AccountClaim, Lease, TradingArea  # noqa: E402


class TradingAreaForm(BaseModelForm):
    class Meta:
        model = TradingArea
        fields = ["name", "kind", "ward", "description", "is_active"]


class LeaseForm(BaseModelForm):
    class Meta:
        model = Lease
        fields = ["lessee", "premises", "purpose", "monthly_rent", "deposit", "start_date", "end_date", "notes"]
        widgets = date_widgets("start_date", "end_date")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["premises"].queryset = Property.objects.alive().select_related("area").order_by("location", "stand_number")
        self.fields["premises"].help_text = "The council-owned shop, stall or premises being leased"


class LevyRunForm(BootstrapFormMixin, forms.Form):
    revenue_head = forms.ModelChoiceField(queryset=RevenueHead.objects.alive().filter(category__in=["LEVY", "LICENCE", "FEES"]),
                                          label="Levy / annual charge")
    year = forms.IntegerField(min_value=2020, max_value=2100)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, required=False, help_text="Leave blank to use the tariff amount")
    area = forms.ModelChoiceField(queryset=TradingArea.objects.alive(), required=False, help_text="Blank = whole district")
    land_use = forms.ChoiceField(choices=[("", "All land uses")] + list(Property.LandUse.choices), required=False)


class ImportForm(BootstrapFormMixin, forms.Form):
    file = forms.FileField(help_text="CSV with columns: area, ward, stand_number, owner_name, account_type, phone, id_number, email, "
                                     "land_use, business_name, monthly_rates, valuation, council_owned, hectares (farms)")


class ClaimDecisionForm(BootstrapFormMixin, forms.Form):
    account = forms.ModelChoiceField(queryset=ClientAccount.objects.alive(), required=False,
                                     help_text="Link to this existing account (leave blank to use the matched stand's owner)")
    create_account = forms.BooleanField(required=False, label="Stand not in the register – register a new account and stand from this claim")
    land_use = forms.ChoiceField(choices=Property.LandUse.choices, initial="COM", required=False)
    monthly_rates = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class BroadcastForm(BootstrapFormMixin, forms.Form):
    area = forms.ModelChoiceField(queryset=TradingArea.objects.alive(), required=False, help_text="Blank = every account in the district")
    only_owing = forms.BooleanField(required=False, initial=True, label="Only accounts that owe money")
    subject = forms.CharField(max_length=120)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), max_length=400)


class PenaltyRunForm(BootstrapFormMixin, forms.Form):
    rate_pct = forms.DecimalField(max_digits=5, decimal_places=2, initial=10, label="Penalty (% of amount overdue)")
    days_overdue = forms.IntegerField(min_value=1, max_value=365, initial=30, label="Charge bills overdue by more than (days)")


class OffenceForm(BaseModelForm):
    class Meta:
        model = Offence
        fields = ["code", "name", "by_law", "default_fine", "is_active"]


class FineForm(BootstrapFormMixin, forms.Form):
    offence = forms.ModelChoiceField(queryset=Offence.objects.alive().filter(is_active=True))
    offender_name = forms.CharField(max_length=200, label="Offender (person or business)")
    national_id = forms.CharField(max_length=30, required=False, label="National ID / company reg.")
    phone = forms.CharField(max_length=20, required=False, help_text="The fine is sent to this number by SMS")
    account = forms.ModelChoiceField(queryset=ClientAccount.objects.alive(), required=False,
                                     help_text="Existing council account – leave blank to find / open one from the ID or phone")
    vehicle_reg = forms.CharField(max_length=20, required=False)
    location = forms.CharField(max_length=200)
    ward = forms.IntegerField(required=False, min_value=1, max_value=40)
    date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    amount = forms.DecimalField(max_digits=12, decimal_places=2, required=False, help_text="Leave blank for the standard fine")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
