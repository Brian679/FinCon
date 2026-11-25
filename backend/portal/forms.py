from django import forms

from core.crud import BaseModelForm, BootstrapFormMixin
from departments.models import StandApplication
from finance.models import Licence, Receipt, RevenueHead
from workflow.models import Complaint, ServiceRequest


class LinkAccountForm(BootstrapFormMixin, forms.Form):
    account_number = forms.CharField(max_length=20, help_text="Shown on your council bill or receipt, e.g. CR2026-00001")
    verifier = forms.CharField(max_length=40, label="Phone number or National ID on the account")


class PayForm(BootstrapFormMixin, forms.Form):
    account = forms.ChoiceField()
    revenue_head = forms.ModelChoiceField(queryset=RevenueHead.objects.alive().filter(is_active=True, payable_online=True), label="Paying for")
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    method = forms.ChoiceField(choices=[(Receipt.Method.ECOCASH, "EcoCash"), (Receipt.Method.ONEMONEY, "OneMoney"), (Receipt.Method.INNBUCKS, "InnBucks")])
    phone = forms.CharField(max_length=20, help_text="Mobile money number to receive the payment prompt")

    def __init__(self, *args, accounts=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].choices = [(str(a.pk), f"{a.account_number} – {a.name} (owes ${a.balance})") for a in accounts]


class ClientLicenceForm(BaseModelForm):
    class Meta:
        model = Licence
        fields = ["licence_type", "business_name", "business_activity", "premises", "ward"]


class ClientComplaintForm(BaseModelForm):
    class Meta:
        model = Complaint
        fields = ["kind", "department", "subject", "details", "ward"]


class ClientRequestForm(BaseModelForm):
    class Meta:
        model = ServiceRequest
        fields = ["category", "description", "location", "ward"]


class ClientStandForm(BaseModelForm):
    class Meta:
        model = StandApplication
        fields = ["stand_type", "preferred_location", "ward", "national_id", "phone"]
