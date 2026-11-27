from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import cap_required
from core.crud import GenericCreateView, GenericListView, GenericUpdateView, run_action
from departments.views import ActionDetail
from finance.services import notify, users_with_cap

from . import forms, services
from .models import Beneficiary, Farm, HuntingQuota, ResourcePermit, TrophyHunt, WaterPoint, WildlifeRecord


def _fmt_qty(v):
    return f"{v:,.2f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------ wildlife
class WildlifeList(GenericListView):
    model = WildlifeRecord
    required_caps = ("wildlife.view", "wildlife.manage")
    title = "CAMPFIRE – wildlife database"
    columns = [("Ref.", "reference"), ("Date", "date"), ("Species", "species"), ("Record", "record_type"), ("Count", "count"), ("Ward", "ward"),
               ("Location", "location"), ("Recorded by", "recorded_by")]
    search_fields = ["reference", "location", "notes"]
    filter_field = "species"
    detail_url_name = "social:wildlife"
    create_url_name = "social:wildlife_new"
    create_caps = ("wildlife.manage",)
    extra_buttons = [("Hunting quotas", "social:quotas", ("hunts.view", "hunts.manage")), ("Trophy hunts", "social:hunts", ("hunts.view", "hunts.manage"))]


class WildlifeNew(GenericCreateView):
    model = WildlifeRecord
    form_class = forms.WildlifeForm
    required_caps = ("wildlife.manage",)
    title = "Record wildlife (count, sighting, mortality, poaching)"
    detail_url_name = "social:wildlife"

    def prepare(self, obj):
        obj.recorded_by = self.request.user


class WildlifeDetail(ActionDetail):
    model = WildlifeRecord
    required_caps = ("wildlife.view", "wildlife.manage")
    edit_url_name = "social:wildlife_edit"
    edit_caps = ("wildlife.manage",)
    fields = [("Species", "species"), ("Record type", "record_type"), ("Date", "date"), ("Count", "count"), ("Ward", "ward"),
              ("Location", "location"), ("GPS", "gps"), ("Notes", "notes"), ("Recorded by", "recorded_by")]


class WildlifeEdit(GenericUpdateView):
    model = WildlifeRecord
    form_class = forms.WildlifeForm
    required_caps = ("wildlife.manage",)
    detail_url_name = "social:wildlife"


# -------------------------------------------------------------------- quotas
class QuotaList(GenericListView):
    model = HuntingQuota
    required_caps = ("hunts.view", "hunts.manage")
    title = "CAMPFIRE – hunting quotas"
    columns = [("Year", "year"), ("Species", "species"), ("Ward", "ward"), ("Concession", "concession"), ("Quota", "quota"), ("Used", "used"),
               ("Left", "remaining"), ("Trophy fee (USD)", "trophy_fee")]
    search_fields = ["concession", "notes"]
    filter_field = "species"
    detail_url_name = "social:quota_edit"
    create_url_name = "social:quota_new"
    create_caps = ("hunts.manage",)
    extra_buttons = [("Trophy hunts", "social:hunts", ("hunts.view", "hunts.manage")), ("Revenue by ward", "social:campfire", ("hunts.view", "hunts.manage"))]


class QuotaNew(GenericCreateView):
    model = HuntingQuota
    form_class = forms.QuotaForm
    required_caps = ("hunts.manage",)
    title = "New hunting quota"

    def get_success_url(self):
        return "/staff/social/quotas/"


class QuotaEdit(GenericUpdateView):
    model = HuntingQuota
    form_class = forms.QuotaForm
    required_caps = ("hunts.manage",)

    def get_success_url(self):
        return "/staff/social/quotas/"


# --------------------------------------------------------------------- hunts
class HuntList(GenericListView):
    model = TrophyHunt
    required_caps = ("hunts.view", "hunts.manage")
    title = "CAMPFIRE – trophy hunts"
    columns = [("Ref.", "reference"), ("Date", "hunt_date"), ("Species", "species_label"), ("Ward", "ward"), ("Client", "client_name"),
               ("Operator", "operator"), ("Fee (USD)", "trophy_fee"), ("Community share", "community_share"), ("Status", "status")]
    search_fields = ["reference", "client_name", "operator__name", "professional_hunter"]
    detail_url_name = "social:hunt"
    create_url_name = "social:hunt_new"
    create_caps = ("hunts.manage",)
    extra_buttons = [("Quotas", "social:quotas", ("hunts.view", "hunts.manage")), ("Revenue by ward", "social:campfire", ("hunts.view", "hunts.manage"))]


@cap_required("hunts.manage")
def hunt_new(request):
    form = forms.HuntForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = dict(form.cleaned_data)
        hunt = run_action(request, services.book_hunt, success="Hunt booked on the quota.", quota=d.pop("quota"), operator=d.pop("operator"),
                          client_name=d.pop("client_name"), trophy_fee=d.pop("trophy_fee"), **d)
        if hunt:
            return redirect("social:hunt", pk=hunt.pk)
    return render(request, "generic/form.html", {"form": form, "title": "Book a trophy hunt"})


class HuntDetail(ActionDetail):
    model = TrophyHunt
    required_caps = ("hunts.view", "hunts.manage")
    action_url_name = "social:hunt_action"
    fields = [("Species", "species_label"), ("Quota", "quota"), ("Safari operator", "operator"), ("Professional hunter", "professional_hunter"),
              ("Client", "client_name"), ("Nationality", "client_nationality"), ("Hunt date", "hunt_date"), ("Trophy", "trophy_details"),
              ("Trophy fee (USD)", "trophy_fee"), ("Community share %", "community_share_pct"), ("Community (ward) share", "community_share"),
              ("Council share", "council_share"), ("Fee bill", "bill")]

    def actions(self, obj):
        if obj.status != TrophyHunt.Status.BOOKED or not self.request.user.has_cap("hunts.manage"):
            return []
        return [{"title": "Record the hunt", "fields": [("hunt_date", "Hunt date", "date", None), ("trophy_details", "Trophy (sex, size, tusk weight…)", "text", None)],
                 "buttons": [("hunted", "Animal taken – bill the trophy fee", "success"), ("cancel", "Cancel booking", "outline-danger")]}]


@cap_required("hunts.manage")
@require_POST
def hunt_action(request, pk):
    hunt = get_object_or_404(TrophyHunt, pk=pk)
    run_action(request, services.hunt_action, hunt, request.POST.get("action"), hunt_date=request.POST.get("hunt_date") or None,
               trophy_details=request.POST.get("trophy_details", ""), success="Hunt updated.")
    return redirect("social:hunt", pk=pk)


@cap_required("hunts.view", "hunts.manage")
def campfire(request):
    year = int(request.GET.get("year") or timezone.localdate().year)
    rows = services.campfire_by_ward(year)
    quotas = HuntingQuota.objects.alive().filter(year=year)
    return render(request, "social/campfire.html", {"title": f"CAMPFIRE revenue {year}", "rows": rows, "year": year, "quotas": quotas,
                                                    "totals": {k: sum(r[k] for r in rows) for k in ("hunts", "fees", "paid", "community", "council")}})


# ------------------------------------------------------------------- permits
class PermitList(GenericListView):
    model = ResourcePermit
    required_caps = ("permits.view", "permits.manage")
    title = "Natural resources – sand, mining & forestry permits"
    columns = [("Ref.", "reference"), ("Type", "permit_type"), ("Holder", "holder"), ("Ward", "ward"), ("Site", "location"),
               ("Allowed", "quantity_allowed"), ("Taken", "quantity_extracted"), ("Fee (USD)", "fee"), ("Valid to", "valid_to"), ("Status", "status")]
    search_fields = ["reference", "holder__name", "location", "ema_reference"]
    detail_url_name = "social:permit"
    create_url_name = "social:permit_new"
    create_caps = ("permits.manage",)


class PermitNew(GenericCreateView):
    model = ResourcePermit
    form_class = forms.PermitForm
    required_caps = ("permits.manage",)
    title = "New natural resources permit application"
    detail_url_name = "social:permit"

    def prepare(self, obj):
        obj.applied_by = self.request.user

    def after_save(self, obj):
        notify([u for u in users_with_cap("permits.approve") if u.pk != self.request.user.pk], f"Permit application {obj.reference}",
               f"{obj.get_permit_type_display()} – {obj.holder.name}, {obj.location}", f"/staff/social/permits/{obj.pk}/")


class PermitDetail(ActionDetail):
    model = ResourcePermit
    required_caps = ("permits.view", "permits.manage")
    action_url_name = "social:permit_action"
    fields = [("Type", "permit_type"), ("Holder", "holder"), ("Ward", "ward"), ("Site", "location"), ("GPS", "gps"),
              ("Quantity allowed", "quantity_allowed"), ("Unit", "unit"), ("Fee per unit (USD)", "unit_fee"), ("Permit fee (USD)", "fee"),
              ("Quantity taken", "quantity_extracted"), ("Quantity left", "quantity_left"), ("Valid", "valid_from"), ("Valid to", "valid_to"),
              ("EMA / Mines / Forestry ref.", "ema_reference"), ("Conditions", "conditions"), ("Captured by", "applied_by"),
              ("Decided by", "decided_by"), ("Decision note", "decision_note"), ("Fee bill", "bill")]

    def sections(self, obj):
        return [{"title": "Extraction log (loads checked)", "rows": [
            (f"{e.date:%d %b %Y} – {_fmt_qty(e.quantity)} {obj.get_unit_display()}", f"{e.vehicle_reg} {e.destination} {e.notes} · {e.recorded_by or ''}")
            for e in obj.extractions.alive()]}]

    def actions(self, obj):
        u = self.request.user
        acts = []
        if obj.status == ResourcePermit.Status.APPLIED and u.has_cap("permits.approve") and obj.applied_by_id != u.pk:
            acts.append({"title": "Decision", "fields": [("unit_fee", f"Fee per unit (USD) – now {obj.unit_fee}", "number", None),
                                                         ("note", "Comment / reason", "textarea", None)],
                         "buttons": [("approve", "Approve & bill the fee", "success"), ("reject", "Reject", "outline-danger")]})
        if obj.status == ResourcePermit.Status.ACTIVE and u.has_cap("permits.manage"):
            acts.append({"title": "Record a load / quantity taken", "fields": [("quantity", f"Quantity ({obj.get_unit_display()})", "number", None),
                                                                              ("vehicle_reg", "Vehicle registration", "text", None),
                                                                              ("destination", "Destination", "text", None)],
                         "buttons": [("extract", "Record", "primary")]})
        if obj.status == ResourcePermit.Status.ACTIVE and u.has_cap("permits.approve"):
            acts.append({"title": "Suspend permit", "fields": [("note", "Reason (e.g. no rehabilitation, over-extraction)", "textarea", None)],
                         "buttons": [("suspend", "Suspend", "outline-danger")]})
        if obj.status == ResourcePermit.Status.SUSPENDED and u.has_cap("permits.approve"):
            acts.append({"title": "Reinstate permit", "fields": [("note", "Comment", "textarea", None)], "buttons": [("reinstate", "Reinstate", "success")]})
        return acts


@cap_required("permits.manage", "permits.approve")
@require_POST
def permit_action(request, pk):
    permit = get_object_or_404(ResourcePermit, pk=pk)
    action = request.POST.get("action")
    if action == "extract":
        run_action(request, services.record_extraction, permit, quantity=request.POST.get("quantity") or "0",
                   vehicle_reg=request.POST.get("vehicle_reg", ""), destination=request.POST.get("destination", ""), success="Load recorded.")
    else:
        run_action(request, services.decide_permit, permit, action, request.POST.get("note", ""), unit_fee=request.POST.get("unit_fee") or None,
                   success="Permit updated.")
    return redirect("social:permit", pk=pk)


# --------------------------------------------------------------------- farms
class FarmList(GenericListView):
    model = Farm
    required_caps = ("farms.view", "farms.manage")
    title = "Agricultural farms register"
    columns = [("Ref.", "reference"), ("Farm", "name"), ("No.", "farm_number"), ("Owner", "owner"), ("Ward", "ward"), ("Area", "location"),
               ("Hectares", "hectares"), ("Type", "farm_type"), ("Activity", "activity"), ("Cattle", "cattle"), ("Status", "status")]
    search_fields = ["reference", "name", "farm_number", "owner__name", "location", "main_crops"]
    detail_url_name = "social:farm"
    create_url_name = "social:farm_new"
    create_caps = ("farms.manage",)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        agg = Farm.objects.alive().aggregate(n=Count("id"), ha=Sum("hectares"), cattle=Sum("cattle"))
        ctx["subtitle"] = f"{agg['n'] or 0} farms · {agg['ha'] or 0:,.1f} ha · {agg['cattle'] or 0:,} cattle. Each farm pays the farm levy per hectare."
        return ctx


class FarmNew(GenericCreateView):
    model = Farm
    form_class = forms.FarmForm
    required_caps = ("farms.manage",)
    title = "Register a farm"
    detail_url_name = "social:farm"


class FarmDetail(ActionDetail):
    model = Farm
    required_caps = ("farms.view", "farms.manage")
    edit_url_name = "social:farm_edit"
    edit_caps = ("farms.manage",)
    fields = [("Farm", "name"), ("Farm / plot no.", "farm_number"), ("Owner", "owner"), ("Ward", "ward"), ("Area / scheme", "location"),
              ("Hectares", "hectares"), ("Type", "farm_type"), ("Activity", "activity"), ("Main crops", "main_crops"), ("Cattle", "cattle"),
              ("Goats / sheep", "goats_sheep"), ("Irrigated (ha)", "irrigated_hectares"), ("Water source", "water_source"), ("GPS", "gps"),
              ("Notes", "notes")]

    def sections(self, obj):
        bills = obj.property.bills.alive().order_by("-created_at")[:10] if obj.property_id else []
        return [{"title": "Farm levy bills", "rows": [(f"{b.number} – USD {b.amount}", f"{b.description} · {b.get_status_display()}") for b in bills]}]


class FarmEdit(GenericUpdateView):
    model = Farm
    form_class = forms.FarmForm
    required_caps = ("farms.manage",)
    detail_url_name = "social:farm"


# --------------------------------------------------------------- water points
class WaterList(GenericListView):
    model = WaterPoint
    required_caps = ("water.view", "water.manage")
    title = "Water points – boreholes, wells & piped schemes (WASH)"
    columns = [("Ref.", "reference"), ("Name", "name"), ("Type", "point_type"), ("Ward", "ward"), ("Village", "village"),
               ("Households", "households_served"), ("Last serviced", "last_serviced"), ("Status", "status")]
    search_fields = ["reference", "name", "village", "committee_contact"]
    detail_url_name = "social:water"
    create_url_name = "social:water_new"
    create_caps = ("water.manage",)


class WaterNew(GenericCreateView):
    model = WaterPoint
    form_class = forms.WaterPointForm
    required_caps = ("water.manage",)
    title = "Add a water point"
    detail_url_name = "social:water"


class WaterDetail(ActionDetail):
    model = WaterPoint
    required_caps = ("water.view", "water.manage")
    edit_url_name = "social:water_edit"
    edit_caps = ("water.manage",)
    fields = [("Name", "name"), ("Type", "point_type"), ("Ward", "ward"), ("Village", "village"), ("Households served", "households_served"),
              ("Last serviced", "last_serviced"), ("Water test passed", "water_quality_ok"), ("Committee contact", "committee_contact"),
              ("GPS", "gps"), ("Notes / repairs", "notes")]


class WaterEdit(GenericUpdateView):
    model = WaterPoint
    form_class = forms.WaterPointForm
    required_caps = ("water.manage",)
    detail_url_name = "social:water"


# -------------------------------------------------------------- social welfare
class BeneficiaryList(GenericListView):
    model = Beneficiary
    required_caps = ("welfare.view", "welfare.manage")
    title = "Social welfare – vulnerable households"
    columns = [("Ref.", "reference"), ("Head of household", "name"), ("Ward", "ward"), ("Village", "village"), ("Household", "household_size"),
               ("Category", "category"), ("Active", "is_active")]
    search_fields = ["reference", "name", "national_id", "village"]
    filter_field = "category"
    detail_url_name = "social:beneficiary"
    create_url_name = "social:beneficiary_new"
    create_caps = ("welfare.manage",)


class BeneficiaryNew(GenericCreateView):
    model = Beneficiary
    form_class = forms.BeneficiaryForm
    required_caps = ("welfare.manage",)
    title = "Register a vulnerable household"
    detail_url_name = "social:beneficiary"


class BeneficiaryDetail(ActionDetail):
    model = Beneficiary
    required_caps = ("welfare.view", "welfare.manage")
    action_url_name = "social:beneficiary_action"
    edit_url_name = "social:beneficiary_edit"
    edit_caps = ("welfare.manage",)
    fields = [("Head of household", "name"), ("National ID", "national_id"), ("Phone", "phone"), ("Ward", "ward"), ("Village", "village"),
              ("Household size", "household_size"), ("Category", "category"), ("Active", "is_active"), ("Notes", "notes")]

    def sections(self, obj):
        return [{"title": "Assistance given", "rows": [(f"{a.date:%d %b %Y} – {a.get_kind_display()} (USD {a.value})",
                                                         f"{a.description} · {a.programme} · {a.given_by or ''}") for a in obj.assistance.alive()]}]

    def actions(self, obj):
        if not (obj.is_active and self.request.user.has_cap("welfare.manage")):
            return []
        from .models import Assistance

        return [{"title": "Record assistance given", "fields": [("kind", "Type", "select", Assistance.Kind.choices),
                                                               ("description", "What was given", "text", None), ("value", "Value (USD)", "number", None),
                                                               ("programme", "Programme / donor", "text", None)],
                 "buttons": [("give", "Record", "primary")]}]


class BeneficiaryEdit(GenericUpdateView):
    model = Beneficiary
    form_class = forms.BeneficiaryForm
    required_caps = ("welfare.manage",)
    detail_url_name = "social:beneficiary"


@cap_required("welfare.manage")
@require_POST
def beneficiary_action(request, pk):
    b = get_object_or_404(Beneficiary, pk=pk)
    run_action(request, services.give_assistance, b, kind=request.POST.get("kind"), description=request.POST.get("description", ""),
               value=request.POST.get("value") or 0, programme=request.POST.get("programme", ""), success="Assistance recorded.")
    return redirect("social:beneficiary", pk=pk)
