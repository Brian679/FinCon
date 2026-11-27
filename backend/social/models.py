"""Social Services registers: CAMPFIRE (wildlife database, hunting quotas, trophy hunts),
natural resources management (sand, mining, forestry permits and extraction),
agricultural farms, water points and social welfare."""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import SequenceCounter, SyncModel
from finance.models import MONEY, POSITIVE, Bill, ClientAccount, Property

ZERO = Decimal("0")


class Species(models.TextChoices):
    ELEPHANT = "ELEPHANT", "Elephant"
    BUFFALO = "BUFFALO", "Buffalo"
    LION = "LION", "Lion"
    LEOPARD = "LEOPARD", "Leopard"
    HIPPO = "HIPPO", "Hippopotamus"
    CROCODILE = "CROC", "Crocodile"
    SABLE = "SABLE", "Sable"
    KUDU = "KUDU", "Kudu"
    ELAND = "ELAND", "Eland"
    IMPALA = "IMPALA", "Impala"
    ZEBRA = "ZEBRA", "Zebra"
    WATERBUCK = "WATERBUCK", "Waterbuck"
    BUSHBUCK = "BUSHBUCK", "Bushbuck"
    HYENA = "HYENA", "Spotted hyena"
    BABOON = "BABOON", "Baboon"
    WILDDOG = "WILDDOG", "Painted (wild) dog"
    OTHER = "OTHER", "Other"


def _ref(prefix, width=5):
    return SequenceCounter.next(prefix, width)


# ------------------------------------------------------------------ CAMPFIRE
class WildlifeRecord(SyncModel):
    """The wildlife database: counts, sightings, mortalities and poaching cases per ward."""

    class RecordType(models.TextChoices):
        GROUND = "GROUND", "Ground count / transect"
        AERIAL = "AERIAL", "Aerial survey"
        SIGHTING = "SIGHTING", "Sighting"
        CAMERA = "CAMERA", "Camera trap"
        MORTALITY = "MORTALITY", "Mortality (found dead)"
        POACHING = "POACHING", "Poaching case / snare"
        PAC = "PAC", "Problem animal control"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    species = models.CharField(max_length=10, choices=Species.choices)
    record_type = models.CharField(max_length=10, choices=RecordType.choices, default=RecordType.SIGHTING)
    date = models.DateField(default=timezone.localdate)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, help_text="Area, river, village or concession")
    count = models.PositiveIntegerField(default=1, help_text="Number of animals")
    gps = models.CharField(max_length=60, blank=True, help_text="Latitude, longitude")
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.reference} {self.get_species_display()} × {self.count} ({self.get_record_type_display()})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _ref("WLD")
        super().save(*args, **kwargs)


class HuntingQuota(SyncModel):
    """Annual hunting quota per species and ward / concession (set with ZimParks)."""

    year = models.PositiveSmallIntegerField(default=timezone.localdate().year)
    species = models.CharField(max_length=10, choices=Species.choices)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    concession = models.CharField(max_length=120, blank=True)
    quota = models.PositiveSmallIntegerField(help_text="Animals that may be hunted this year")
    trophy_fee = models.DecimalField(**MONEY, default=ZERO, help_text="Standard trophy fee per animal (USD)")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-year", "species", "ward"]
        unique_together = [("year", "species", "ward", "concession")]

    def __str__(self):
        where = self.concession or (f"ward {self.ward}" if self.ward else "district")
        return f"{self.year} {self.get_species_display()} – {where}: {self.quota}"

    @property
    def used(self):
        return self.hunts.alive().exclude(status=TrophyHunt.Status.CANCELLED).count()

    @property
    def remaining(self):
        return max(self.quota - self.used, 0)


class TrophyHunt(SyncModel):
    """A safari hunt on the CAMPFIRE quota: booked → hunted (trophy fee billed) → paid."""

    class Status(models.TextChoices):
        BOOKED = "BOOKED", "Booked"
        HUNTED = "HUNTED", "Hunted – awaiting payment"
        PAID = "PAID", "Trophy fee paid"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    quota = models.ForeignKey(HuntingQuota, on_delete=models.PROTECT, related_name="hunts")
    operator = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="trophy_hunts", help_text="Safari operator (council account)")
    professional_hunter = models.CharField(max_length=120, blank=True)
    client_name = models.CharField(max_length=120, help_text="Hunting client")
    client_nationality = models.CharField(max_length=60, blank=True)
    hunt_date = models.DateField(null=True, blank=True)
    trophy_fee = models.DecimalField(**MONEY, validators=POSITIVE)
    community_share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("55"),
                                              help_text="Share of the fee paid to the producer ward(s) under CAMPFIRE")
    trophy_details = models.CharField(max_length=255, blank=True, help_text="Sex, size, tusk weight / horn length …")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED, db_index=True)
    bill = models.ForeignKey(Bill, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-hunt_date", "-created_at"]

    def __str__(self):
        return f"{self.reference} {self.quota.get_species_display()} – {self.client_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _ref("HNT")
        super().save(*args, **kwargs)

    @property
    def species_label(self):
        return self.quota.get_species_display()

    @property
    def ward(self):
        return self.quota.ward

    @property
    def community_share(self):
        return (self.trophy_fee * self.community_share_pct / 100).quantize(Decimal("0.01"))

    @property
    def council_share(self):
        return self.trophy_fee - self.community_share


# ----------------------------------------------------------- natural resources
class ResourcePermit(SyncModel):
    """Sand / gravel extraction, quarrying, small-scale mining, timber and firewood permits."""

    class PermitType(models.TextChoices):
        SAND = "SAND", "Sand extraction"
        GRAVEL = "GRAVEL", "Gravel / quarry stone"
        CLAY = "CLAY", "Clay / brick moulding"
        MINING = "MINING", "Small-scale / artisanal mining"
        TIMBER = "TIMBER", "Timber harvesting (forestry)"
        FIREWOOD = "FIREWOOD", "Firewood / charcoal"
        THATCH = "THATCH", "Thatch grass & reeds"
        OTHER = "OTHER", "Other natural resource"

    class Unit(models.TextChoices):
        CUBIC = "M3", "cubic metres"
        TONNE = "T", "tonnes"
        LOAD = "LOAD", "truck loads"
        CORD = "CORD", "cords / stacks"
        BUNDLE = "BUNDLE", "bundles"
        MONTH = "MONTH", "months"

    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Application received"
        APPROVED = "APPROVED", "Awaiting payment"
        ACTIVE = "ACTIVE", "Active"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"
        EXPIRED = "EXPIRED", "Expired"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    permit_type = models.CharField(max_length=10, choices=PermitType.choices)
    holder = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="resource_permits")
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, help_text="Site: river bed, pit, forest block …")
    gps = models.CharField(max_length=60, blank=True)
    unit = models.CharField(max_length=6, choices=Unit.choices, default=Unit.CUBIC)
    quantity_allowed = models.DecimalField(max_digits=12, decimal_places=2, validators=POSITIVE)
    unit_fee = models.DecimalField(**MONEY, validators=POSITIVE, help_text="Council fee / royalty per unit (USD)")
    fee = models.DecimalField(**MONEY, default=ZERO, editable=False)
    valid_from = models.DateField(default=timezone.localdate)
    valid_to = models.DateField()
    ema_reference = models.CharField(max_length=60, blank=True, help_text="EMA / Mines / Forestry Commission approval no.")
    conditions = models.TextField(blank=True, help_text="Rehabilitation, depth limits, hours …")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPLIED, db_index=True)
    bill = models.ForeignKey(Bill, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decision_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.get_permit_type_display()} – {self.holder.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _ref("NRP")
        self.fee = (self.quantity_allowed or ZERO) * (self.unit_fee or ZERO)
        super().save(*args, **kwargs)

    @property
    def quantity_extracted(self):
        return self.extractions.alive().aggregate(t=models.Sum("quantity"))["t"] or ZERO

    @property
    def quantity_left(self):
        return self.quantity_allowed - self.quantity_extracted


class Extraction(SyncModel):
    """A load / quantity taken under a permit, checked at the site or a road block."""

    permit = models.ForeignKey(ResourcePermit, on_delete=models.PROTECT, related_name="extractions")
    date = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=POSITIVE)
    vehicle_reg = models.CharField(max_length=20, blank=True)
    destination = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.permit.reference}: {self.quantity} {self.permit.get_unit_display()} on {self.date}"


# --------------------------------------------------------------------- farms
class Farm(SyncModel):
    """Agricultural farm register. Each farm is also a council property, so the farm levy
    ($ per hectare) is billed to the owner's account by the levy billing run."""

    class FarmType(models.TextChoices):
        A1 = "A1", "A1 resettlement"
        A2 = "A2", "A2 commercial"
        COMMUNAL = "COMMUNAL", "Communal land"
        SMALL = "SSCF", "Small-scale commercial"
        LARGE = "LSCF", "Large-scale commercial"
        ESTATE = "ESTATE", "Estate / plantation"
        IRRIGATION = "IRRIG", "Irrigation scheme plot"

    class Activity(models.TextChoices):
        CROPS = "CROPS", "Crops"
        LIVESTOCK = "LIVESTOCK", "Livestock"
        MIXED = "MIXED", "Mixed farming"
        HORTICULTURE = "HORT", "Horticulture"
        PLANTATION = "PLANT", "Tea / coffee / timber plantation"
        DAIRY = "DAIRY", "Dairy"
        POULTRY = "POULTRY", "Poultry"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        IDLE = "IDLE", "Idle / under-used"
        DISPUTED = "DISPUTED", "Boundary / ownership dispute"
        ABANDONED = "ABANDONED", "Abandoned"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="farms")
    property = models.OneToOneField(Property, null=True, blank=True, on_delete=models.PROTECT, related_name="farm", editable=False)
    farm_number = models.CharField(max_length=40, help_text="Farm / plot number (e.g. offer letter or title number)")
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, help_text="Area / resettlement scheme / village")
    hectares = models.DecimalField(max_digits=10, decimal_places=2, validators=POSITIVE)
    farm_type = models.CharField(max_length=10, choices=FarmType.choices, default=FarmType.A1)
    activity = models.CharField(max_length=10, choices=Activity.choices, default=Activity.MIXED)
    main_crops = models.CharField(max_length=200, blank=True, help_text="e.g. maize, cotton, tea, macadamia")
    cattle = models.PositiveIntegerField(default=0)
    goats_sheep = models.PositiveIntegerField(default=0)
    irrigated_hectares = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    water_source = models.CharField(max_length=120, blank=True)
    gps = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["location", "name"]

    def __str__(self):
        return f"{self.reference} {self.name} ({self.hectares:g} ha)"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _ref("FRM")
        place = self.location or "Farms"
        if self.property_id is None:
            existing = Property.objects.filter(location=place, stand_number=self.farm_number).first()
            self.property = existing or Property.objects.create(
                account=self.owner, location=place, stand_number=self.farm_number, ward=self.ward, land_use=Property.LandUse.AGRICULTURAL,
                hectares=self.hectares, business_name="", created_by=self.created_by)
        super().save(*args, **kwargs)
        p = self.property
        changed = {k: v for k, v in (("account_id", self.owner_id), ("hectares", self.hectares), ("ward", self.ward),
                                     ("is_active", self.status != self.Status.ABANDONED)) if getattr(p, k) != v}
        if changed:
            Property.objects.filter(pk=p.pk).update(updated_at=timezone.now(), land_use=Property.LandUse.AGRICULTURAL, **changed)


# --------------------------------------------------------------- water points
class WaterPoint(SyncModel):
    class PointType(models.TextChoices):
        BOREHOLE = "BOREHOLE", "Borehole (bush pump)"
        SOLAR = "SOLAR", "Solar-powered borehole"
        WELL = "WELL", "Protected well"
        PIPED = "PIPED", "Piped water scheme"
        SPRING = "SPRING", "Protected spring"
        DAM = "DAM", "Dam / weir"

    class Status(models.TextChoices):
        WORKING = "WORKING", "Working"
        BROKEN = "BROKEN", "Broken down"
        REPAIR = "REPAIR", "Under repair"
        DRY = "DRY", "Dry / low yield"
        DECOMMISSIONED = "DECOM", "Decommissioned"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=150, help_text="e.g. Chibuwe Primary School borehole")
    point_type = models.CharField(max_length=10, choices=PointType.choices, default=PointType.BOREHOLE)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    village = models.CharField(max_length=120)
    households_served = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WORKING, db_index=True)
    last_serviced = models.DateField(null=True, blank=True)
    water_quality_ok = models.BooleanField(default=True, help_text="Last water test passed")
    committee_contact = models.CharField(max_length=120, blank=True, help_text="Water point committee chair / phone")
    gps = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True, help_text="Faults, repairs, parts used")

    class Meta:
        ordering = ["ward", "village", "name"]

    def __str__(self):
        return f"{self.reference} {self.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _ref("WP")
        super().save(*args, **kwargs)


# ------------------------------------------------------------- social welfare
class Beneficiary(SyncModel):
    class Category(models.TextChoices):
        ELDERLY = "ELDERLY", "Elderly (no support)"
        CHILD_HEADED = "CHILD", "Child-headed household"
        DISABILITY = "DISABLED", "Person with disability"
        CHRONIC = "CHRONIC", "Chronically ill"
        DISASTER = "DISASTER", "Disaster-affected household"
        FOOD_INSECURE = "FOOD", "Food-insecure household"
        OTHER = "OTHER", "Other vulnerable"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=150, help_text="Head of household")
    national_id = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    village = models.CharField(max_length=120)
    household_size = models.PositiveSmallIntegerField(default=1)
    category = models.CharField(max_length=10, choices=Category.choices)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["ward", "village", "name"]
        verbose_name_plural = "beneficiaries"

    def __str__(self):
        return f"{self.reference} {self.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _ref("SW")
        super().save(*args, **kwargs)


class Assistance(SyncModel):
    class Kind(models.TextChoices):
        FOOD = "FOOD", "Food aid"
        CASH = "CASH", "Cash transfer"
        SCHOOL = "SCHOOL", "School fees (BEAM)"
        MEDICAL = "MEDICAL", "Medical / assisted treatment"
        SHELTER = "SHELTER", "Shelter / building materials"
        BURIAL = "BURIAL", "Pauper burial"
        OTHER = "OTHER", "Other"

    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.PROTECT, related_name="assistance")
    date = models.DateField(default=timezone.localdate)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    description = models.CharField(max_length=255, help_text="e.g. 50 kg maize, 2 L cooking oil")
    value = models.DecimalField(**MONEY, default=ZERO, help_text="Value in USD")
    programme = models.CharField(max_length=120, blank=True, help_text="Donor / programme (e.g. drought relief 2026)")
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name_plural = "assistance"

    def __str__(self):
        return f"{self.get_kind_display()} to {self.beneficiary.name} on {self.date}"
