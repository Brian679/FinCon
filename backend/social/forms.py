from django import forms

from core.crud import BaseModelForm, date_widgets
from finance.models import ClientAccount

from .models import Assistance, Beneficiary, Extraction, Farm, HuntingQuota, ResourcePermit, TrophyHunt, WaterPoint, WildlifeRecord


class WildlifeForm(BaseModelForm):
    class Meta:
        model = WildlifeRecord
        fields = ["species", "record_type", "date", "ward", "location", "count", "gps", "notes"]
        widgets = date_widgets("date")


class QuotaForm(BaseModelForm):
    class Meta:
        model = HuntingQuota
        fields = ["year", "species", "ward", "concession", "quota", "trophy_fee", "notes"]


class HuntForm(BaseModelForm):
    operator = forms.ModelChoiceField(queryset=ClientAccount.objects.alive(), label="Safari operator (council account)")

    class Meta:
        model = TrophyHunt
        fields = ["quota", "operator", "professional_hunter", "client_name", "client_nationality", "hunt_date", "trophy_fee", "community_share_pct"]
        widgets = date_widgets("hunt_date")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["trophy_fee"].required = False
        self.fields["trophy_fee"].help_text = "Leave blank to use the quota's standard trophy fee"


class PermitForm(BaseModelForm):
    holder = forms.ModelChoiceField(queryset=ClientAccount.objects.alive(), label="Permit holder (council account)")

    class Meta:
        model = ResourcePermit
        fields = ["permit_type", "holder", "ward", "location", "gps", "unit", "quantity_allowed", "unit_fee", "valid_from", "valid_to",
                  "ema_reference", "conditions"]
        widgets = date_widgets("valid_from", "valid_to")

    def clean(self):
        data = super().clean()
        if data.get("valid_from") and data.get("valid_to") and data["valid_to"] < data["valid_from"]:
            self.add_error("valid_to", "Must be after the start date.")
        return data


class ExtractionForm(BaseModelForm):
    class Meta:
        model = Extraction
        fields = ["date", "quantity", "vehicle_reg", "destination", "notes"]
        widgets = date_widgets("date")


class FarmForm(BaseModelForm):
    owner = forms.ModelChoiceField(queryset=ClientAccount.objects.alive(), label="Owner / occupier (council account)")

    class Meta:
        model = Farm
        fields = ["name", "owner", "farm_number", "ward", "location", "hectares", "farm_type", "activity", "main_crops", "cattle", "goats_sheep",
                  "irrigated_hectares", "water_source", "gps", "status", "notes"]


class WaterPointForm(BaseModelForm):
    class Meta:
        model = WaterPoint
        fields = ["name", "point_type", "ward", "village", "households_served", "status", "last_serviced", "water_quality_ok", "committee_contact",
                  "gps", "notes"]
        widgets = date_widgets("last_serviced")


class BeneficiaryForm(BaseModelForm):
    class Meta:
        model = Beneficiary
        fields = ["name", "national_id", "phone", "ward", "village", "household_size", "children", "category", "need", "is_active", "notes"]


class AssistanceForm(BaseModelForm):
    class Meta:
        model = Assistance
        fields = ["date", "kind", "description", "value", "programme"]
        widgets = date_widgets("date")
