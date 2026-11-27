"""Department-specific registers for Administration (HR), Social Services,
Technical Services and Internal Audit."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.validators import validate_document
from core.models import Department, SequenceCounter, SyncModel


class LeaveRequest(SyncModel):
    class LeaveType(models.TextChoices):
        ANNUAL = "ANNUAL", "Annual / vacation"
        SICK = "SICK", "Sick"
        MATERNITY = "MATERNITY", "Maternity"
        COMPASSIONATE = "COMPASS", "Compassionate"
        STUDY = "STUDY", "Study"
        UNPAID = "UNPAID", "Unpaid"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leave_requests")
    leave_type = models.CharField(max_length=10, choices=LeaveType.choices, default=LeaveType.ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    stage = models.CharField(max_length=6, blank=True, choices=[("HOD", "Head of Department"), ("HR", "HR / Administration Officer"),
                                                                 ("CEO", "Chief Executive Officer")],
                             help_text="Who the application is waiting for")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.employee} {self.get_leave_type_display()} {self.start_date} - {self.end_date}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            from django.core.exceptions import ValidationError

            if self.end_date < self.start_date:
                raise ValidationError("End date is before the start date.")
            clash = LeaveRequest.objects.alive().filter(employee_id=self.employee_id, status__in=[self.Status.PENDING, self.Status.APPROVED],
                                                       start_date__lte=self.end_date, end_date__gte=self.start_date)
            if clash.exists():
                raise ValidationError("You already have leave applied for or approved on some of these days.")
            if self.leave_type == self.LeaveType.ANNUAL:
                from payroll.services import leave_balance

                left = leave_balance(self.employee, self.start_date.year)["left"]
                if self.days > left:
                    raise ValidationError(f"Not enough annual leave: you asked for {self.days} working day(s) but have {left} left this year.")
        super().save(*args, **kwargs)

    @property
    def days(self):
        from core.sla import is_working_day

        n, d = 0, self.start_date
        while d <= self.end_date:
            n += 1 if is_working_day(d) else 0
            d += timezone.timedelta(days=1)
        return n


class StandApplication(SyncModel):
    """Housing development / stand allocation (Social Services)."""

    class StandType(models.TextChoices):
        RESIDENTIAL = "RES", "Residential"
        COMMERCIAL = "COM", "Commercial"
        INSTITUTIONAL = "INST", "Institutional / church / school"
        INDUSTRIAL = "IND", "Industrial"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received (waiting list)"
        SHORTLISTED = "SHORTLISTED", "Shortlisted"
        ALLOCATED = "ALLOCATED", "Stand allocated"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="stand_applications")
    applicant_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=30)
    phone = models.CharField(max_length=30, blank=True)
    stand_type = models.CharField(max_length=4, choices=StandType.choices, default=StandType.RESIDENTIAL)
    preferred_location = models.CharField(max_length=200)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    allocated_stand = models.CharField(max_length=60, blank=True)
    allocated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    allocated_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.reference} {self.applicant_name} ({self.get_stand_type_display()})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("STA", 5)
        super().save(*args, **kwargs)


class Project(SyncModel):
    """Capital / infrastructure projects (roads, boreholes, schools, clinics, lighting)."""

    class Category(models.TextChoices):
        ROADS = "ROADS", "Roads construction / rehabilitation"
        WATER = "WATER", "Water supply / boreholes"
        BUILDINGS = "BUILDINGS", "Schools & clinics development"
        LIGHTING = "LIGHTING", "Public lighting"
        HOUSING = "HOUSING", "Housing development / servicing"
        ENVIRONMENT = "ENV", "Environment / land reclamation"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        PROCUREMENT = "PROCUREMENT", "Procurement"
        ONGOING = "ONGOING", "Ongoing"
        COMPLETED = "COMPLETED", "Completed"
        SUSPENDED = "SUSPENDED", "Suspended"

    code = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=10, choices=Category.choices)
    department = models.CharField(max_length=10, choices=Department.choices, default=Department.TECHNICAL_SERVICES)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    budget_line = models.ForeignKey("finance.BudgetLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="projects")
    funder = models.CharField(max_length=120, blank=True, help_text="e.g. Council, ZINARA, Devolution funds, Partner")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    progress = models.PositiveSmallIntegerField(default=0, help_text="Percent complete")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects")

    class Meta:
        ordering = ["status", "name"]

    def __str__(self):
        return f"{self.code} {self.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = SequenceCounter.next("PRJ", 4)
        super().save(*args, **kwargs)


class AuditFinding(SyncModel):
    """Internal Audit: risk management, compliance audits, systems reviews,
    performance audits."""

    class AuditType(models.TextChoices):
        COMPLIANCE = "COMPLIANCE", "Compliance audit"
        RISK = "RISK", "Risk management review"
        SYSTEMS = "SYSTEMS", "Systems review"
        PERFORMANCE = "PERFORMANCE", "Performance audit"
        CASH = "CASH", "Cash / revenue audit"

    class Risk(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open - awaiting management response"
        RESPONDED = "RESPONDED", "Management responded"
        IMPLEMENTING = "IMPLEMENTING", "Being implemented"
        CLOSED = "CLOSED", "Closed / verified"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    audit_type = models.CharField(max_length=12, choices=AuditType.choices)
    department = models.CharField(max_length=10, choices=Department.choices)
    title = models.CharField(max_length=200)
    finding = models.TextField()
    risk_rating = models.CharField(max_length=8, choices=Risk.choices, default=Risk.MEDIUM)
    recommendation = models.TextField()
    management_response = models.TextField(blank=True)
    responded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    implementation_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    auditor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audit_findings")

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("AUD", 4)
        super().save(*args, **kwargs)


# =====================================================================
# Assets & infrastructure (Finance: asset management; WASH: boreholes &
# public ablutions; Technical: roads, bridges, public lighting)
# =====================================================================
class Asset(SyncModel):
    class Category(models.TextChoices):
        VEHICLE = "VEHICLE", "Motor vehicle"
        PLANT = "PLANT", "Plant & earth-moving equipment"
        EQUIPMENT = "EQUIP", "Tools & equipment"
        ICT = "ICT", "ICT equipment"
        FURNITURE = "FURN", "Furniture & fittings"
        BUILDING = "BUILDING", "Building"
        LAND = "LAND", "Land"
        BOREHOLE = "BOREHOLE", "Borehole"
        WATER_SCHEME = "WATER", "Piped water scheme"
        ABLUTION = "ABLUTION", "Public ablution block"
        STREET_LIGHT = "LIGHT", "Street / high-mast light"
        ROAD = "ROAD", "Road"
        BRIDGE = "BRIDGE", "Bridge / culvert"
        OTHER = "OTHER", "Other"

    class Condition(models.TextChoices):
        GOOD = "GOOD", "Good / working"
        FAIR = "FAIR", "Fair"
        POOR = "POOR", "Poor – needs repair"
        BROKEN = "BROKEN", "Broken down / not working"

    class Status(models.TextChoices):
        IN_USE = "IN_USE", "In use"
        UNDER_REPAIR = "REPAIR", "Under repair"
        IDLE = "IDLE", "Idle / in store"
        DISPOSED = "DISPOSED", "Disposed"

    asset_number = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=10, choices=Category.choices)
    department = models.CharField(max_length=10, choices=Department.choices)
    serial_number = models.CharField("Serial / registration no.", max_length=80, blank=True)
    location = models.CharField(max_length=200, blank=True)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    acquisition_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    useful_life_years = models.PositiveSmallIntegerField(default=10)
    custodian = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    condition = models.CharField(max_length=6, choices=Condition.choices, default=Condition.GOOD)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.IN_USE, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.asset_number} {self.name}"

    def save(self, *args, **kwargs):
        if not self.asset_number:
            self.asset_number = SequenceCounter.next("AST", 5)
        super().save(*args, **kwargs)

    def book_value(self):
        """Straight-line depreciation."""
        from decimal import Decimal

        if not self.acquisition_date or not self.useful_life_years:
            return self.cost
        years = (timezone.localdate() - self.acquisition_date).days / 365.25
        remaining = max(0.0, 1 - years / self.useful_life_years)
        return (self.cost * Decimal(str(remaining))).quantize(Decimal("0.01"))


class AssetMaintenance(SyncModel):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="maintenance")
    date = models.DateField(default=timezone.localdate)
    work_done = models.TextField()
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    performed_by = models.CharField(max_length=200, blank=True)
    condition_after = models.CharField(max_length=6, choices=Asset.Condition.choices, default=Asset.Condition.GOOD)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.asset} {self.date}"


# =====================================================================
# Social Services: Public Safety (disaster risk), Natural Resources
# (fire, human-wildlife conflict), community programmes & campaigns
# =====================================================================
class Incident(SyncModel):
    class IncidentType(models.TextChoices):
        FIRE = "FIRE", "Veld / structure fire"
        FLOOD = "FLOOD", "Flood"
        STORM = "STORM", "Storm / cyclone"
        DROUGHT = "DROUGHT", "Drought"
        HWC = "HWC", "Human-wildlife conflict"
        DISEASE = "DISEASE", "Disease outbreak"
        ACCIDENT = "ACCIDENT", "Accident"
        COLLAPSE = "COLLAPSE", "Structure collapse"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        REPORTED = "REPORTED", "Reported"
        RESPONDING = "RESPONDING", "Response under way"
        CONTAINED = "CONTAINED", "Contained – recovery"
        CLOSED = "CLOSED", "Closed (HOD signed off)"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    incident_type = models.CharField(max_length=10, choices=IncidentType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField()
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200)
    occurred_at = models.DateTimeField(default=timezone.now)
    households_affected = models.PositiveIntegerField(default=0)
    people_injured = models.PositiveIntegerField(default=0)
    deaths = models.PositiveIntegerField(default=0)
    livestock_lost = models.PositiveIntegerField(default=0)
    crops_hectares = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    response = models.TextField(blank=True, help_text="Actions taken, relief distributed, agencies involved")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REPORTED, db_index=True)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    lead_officer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("INC", 5)
        super().save(*args, **kwargs)


class CommunityActivity(SyncModel):
    """Programmes delivered in the community: hygiene promotion, environmental
    campaigns, public-safety awareness, emergency drills, community services,
    stakeholder consultations (WDCs, village assemblies)."""

    class ActivityType(models.TextChoices):
        HYGIENE = "HYGIENE", "Hygiene promotion (WASH)"
        HEALTH = "HEALTH", "Public health programme"
        ENVIRONMENT = "ENV", "Environmental campaign"
        CONSERVATION = "CONSERVE", "Natural resource conservation"
        RECLAMATION = "RECLAIM", "Land reclamation"
        FIRE = "FIRE", "Fire management / fireguards"
        SAFETY = "SAFETY", "Public safety awareness"
        PREPAREDNESS = "PREPARE", "Emergency preparedness / drill"
        SECURITY = "SECURITY", "Community security programme"
        COMMUNITY = "COMMUNITY", "Community services"
        CONSULTATION = "CONSULT", "Community consultation / WDC / village assembly"
        TRAINING = "TRAINING", "Staff / stakeholder training"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        DONE = "DONE", "Held – report submitted"
        VERIFIED = "VERIFIED", "Verified by Head of Department"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    activity_type = models.CharField(max_length=10, choices=ActivityType.choices)
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=10, choices=Department.choices, default=Department.SOCIAL_SERVICES)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    venue = models.CharField(max_length=200, blank=True)
    date = models.DateField(default=timezone.localdate)
    participants = models.PositiveIntegerField(default=0)
    report = models.TextField(blank=True, help_text="Outcome, issues raised, follow-up actions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED, db_index=True)
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="activities")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "community activities"

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("ACT", 5)
        super().save(*args, **kwargs)


# =====================================================================
# Technical Services: development control (building plans)
# =====================================================================
class BuildingPlan(SyncModel):
    class DevType(models.TextChoices):
        RESIDENTIAL = "RES", "Residential house"
        COMMERCIAL = "COM", "Commercial / shop"
        INDUSTRIAL = "IND", "Industrial"
        INSTITUTIONAL = "INST", "Institutional (school, clinic, church)"
        ALTERATION = "ALT", "Alteration / extension"
        CHANGE_OF_USE = "COU", "Change of use / subdivision"

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted – awaiting fee & review"
        UNDER_REVIEW = "REVIEW", "Under technical review"
        RECOMMENDED = "RECOMMEND", "Recommended – awaiting Engineer"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected / returned for corrections"
        CONSTRUCTION = "BUILDING", "Construction – inspections"
        COMPLETED = "COMPLETED", "Completion certificate issued"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="building_plans")
    applicant_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    stand_number = models.CharField(max_length=40)
    location = models.CharField(max_length=200)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    development_type = models.CharField(max_length=4, choices=DevType.choices)
    description = models.TextField()
    floor_area = models.DecimalField("Floor area (m²)", max_digits=10, decimal_places=2, default=0)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bill = models.ForeignKey("finance.Bill", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    review_notes = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decision_notes = models.TextField(blank=True)
    inspection_log = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True, help_text="Charter: process applications within 30 working days")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.applicant_name} – stand {self.stand_number}"

    def save(self, *args, **kwargs):
        from core.sla import due_from_standard

        if not self.reference:
            self.reference = SequenceCounter.next("BP", 5)
        if self._state.adding and not self.due_at:
            self.due_at = due_from_standard("process-applications")
        super().save(*args, **kwargs)


# =====================================================================
# Internal Audit: risk management
# =====================================================================
class Risk(SyncModel):
    class Category(models.TextChoices):
        FINANCIAL = "FIN", "Financial"
        FRAUD = "FRAUD", "Fraud & corruption"
        OPERATIONAL = "OPS", "Operational / service delivery"
        COMPLIANCE = "COMPLY", "Legal & compliance"
        STRATEGIC = "STRAT", "Strategic"
        ICT = "ICT", "ICT & data"
        HEALTH_SAFETY = "OHS", "Health, safety & environment"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        MITIGATING = "MITIGATING", "Mitigation in progress"
        CLOSED = "CLOSED", "Closed / accepted"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    department = models.CharField(max_length=10, choices=Department.choices)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=6, choices=Category.choices)
    likelihood = models.PositiveSmallIntegerField(default=3, help_text="1 (rare) – 5 (almost certain)")
    impact = models.PositiveSmallIntegerField(default=3, help_text="1 (minor) – 5 (catastrophic)")
    existing_controls = models.TextField(blank=True)
    mitigation = models.TextField(blank=True, help_text="Planned actions")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="risks")
    review_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["status", "-likelihood", "-impact"]

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("RSK", 4)
        super().save(*args, **kwargs)

    @property
    def score(self):
        return self.likelihood * self.impact

    @property
    def rating(self):
        s = self.score
        return "CRITICAL" if s >= 20 else "HIGH" if s >= 12 else "MEDIUM" if s >= 6 else "LOW"


# =====================================================================
# Administration: council secretariat, ICT services, policy development
# =====================================================================
class CouncilMeeting(SyncModel):
    class MeetingType(models.TextChoices):
        FULL_COUNCIL = "FULL", "Full council"
        FINANCE = "FIN", "Finance & General Purposes committee"
        HEALTH = "HEALTH", "Health, Housing & Social Services committee"
        WORKS = "WORKS", "Roads & Works committee"
        AUDIT = "AUDIT", "Audit committee"
        HR = "HR", "Human Resources committee"
        NATURAL = "NATRES", "Natural Resources committee"
        MANAGEMENT = "MGMT", "Management meeting"
        WDC = "WDC", "Ward Development Committee"

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        HELD = "HELD", "Held – minutes recorded"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    meeting_type = models.CharField(max_length=6, choices=MeetingType.choices)
    title = models.CharField(max_length=200)
    date = models.DateTimeField()
    venue = models.CharField(max_length=200, default="Council Chamber, Chipinge")
    agenda = models.TextField(blank=True)
    minutes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("MTG", 4)
        super().save(*args, **kwargs)


class Resolution(SyncModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Not started"
        IN_PROGRESS = "IN_PROGRESS", "Being implemented"
        IMPLEMENTED = "DONE", "Implemented"
        RESCINDED = "RESCINDED", "Rescinded"

    number = models.CharField(max_length=30, unique=True, editable=False)
    meeting = models.ForeignKey(CouncilMeeting, on_delete=models.CASCADE, related_name="resolutions")
    text = models.TextField()
    department = models.CharField(max_length=10, choices=Department.choices)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolutions")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=11, choices=Status.choices, default=Status.PENDING, db_index=True)
    progress_note = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "due_date"]

    def __str__(self):
        return f"{self.number} {self.text[:60]}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = SequenceCounter.next("RES", 4)
        super().save(*args, **kwargs)


class ICTTicket(SyncModel):
    class Category(models.TextChoices):
        HARDWARE = "HW", "Computer / hardware"
        SOFTWARE = "SW", "Software / system"
        NETWORK = "NET", "Network / internet"
        ACCOUNT = "ACCT", "User account / password"
        PRINTER = "PRINT", "Printer / scanner"
        PHONE = "PHONE", "Telephone / mobile app"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "Being attended"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ict_tickets")
    department = models.CharField(max_length=10, choices=Department.choices)
    category = models.CharField(max_length=5, choices=Category.choices)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=6, choices=[("LOW", "Low"), ("NORMAL", "Normal"), ("HIGH", "High"), ("URGENT", "Urgent")], default="NORMAL")
    status = models.CharField(max_length=11, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets")
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]

    def __str__(self):
        return f"{self.reference} {self.subject}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("ICT", 5)
        super().save(*args, **kwargs)


class Policy(SyncModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONSULTATION = "CONSULT", "Stakeholder consultation"
        COUNCIL = "COUNCIL", "Awaiting council adoption"
        ADOPTED = "ADOPTED", "Adopted / in force"
        RETIRED = "RETIRED", "Retired"

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=[("POLICY", "Policy"), ("BYLAW", "By-law"), ("PROCEDURE", "Procedure / manual"),
                                                    ("STRATEGY", "Strategic plan")], default="POLICY")
    department = models.CharField(max_length=10, choices=Department.choices)
    version = models.CharField(max_length=20, default="1.0")
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    adopted_on = models.DateField(null=True, blank=True)
    review_date = models.DateField(null=True, blank=True)
    document = models.FileField(upload_to="policies/", blank=True, validators=[validate_document])

    class Meta:
        ordering = ["department", "title"]
        verbose_name_plural = "policies"

    def __str__(self):
        return f"{self.title} v{self.version}"


# ================================================== Technical Services (charter: roads, lighting, engineering)
class Road(SyncModel):
    """Road network register: roads construction / rehabilitation and maintenance."""

    class Surface(models.TextChoices):
        TAR = "TAR", "Tarred / bitumen"
        GRAVEL = "GRAVEL", "Gravel"
        EARTH = "EARTH", "Earth / track"
        CONCRETE = "CONCRETE", "Concrete strip"

    class Condition(models.TextChoices):
        GOOD = "GOOD", "Good"
        FAIR = "FAIR", "Fair"
        POOR = "POOR", "Poor – needs rehabilitation"
        IMPASSABLE = "IMPASSABLE", "Impassable"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=150, help_text="e.g. Checheche – Chibuwe road")
    road_number = models.CharField(max_length=30, blank=True, help_text="District road number")
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    start_point = models.CharField(max_length=120)
    end_point = models.CharField(max_length=120)
    length_km = models.DecimalField(max_digits=8, decimal_places=2)
    surface = models.CharField(max_length=10, choices=Surface.choices, default=Surface.GRAVEL)
    condition = models.CharField(max_length=10, choices=Condition.choices, default=Condition.FAIR, db_index=True)
    last_graded = models.DateField(null=True, blank=True, help_text="Last grading / maintenance")
    bridges_culverts = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True, help_text="Potholes, washaways, drainage problems …")

    class Meta:
        ordering = ["ward", "name"]

    def __str__(self):
        return f"{self.reference} {self.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("RD", 4)
        super().save(*args, **kwargs)


class PublicLight(SyncModel):
    """Public lighting: street lights and high-mast lights."""

    class LightType(models.TextChoices):
        STREET = "STREET", "Street light"
        HIGHMAST = "HIGHMAST", "High-mast light"
        SOLAR = "SOLAR", "Solar street light"
        FLOOD = "FLOOD", "Flood light"

    class Status(models.TextChoices):
        WORKING = "WORKING", "Working"
        FAULTY = "FAULTY", "Faulty / not lighting"
        VANDALISED = "VANDAL", "Vandalised / stolen parts"
        REPAIR = "REPAIR", "Under repair"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    light_type = models.CharField(max_length=10, choices=LightType.choices, default=LightType.STREET)
    location = models.CharField(max_length=200, help_text="Street / growth point / landmark")
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    pole_number = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WORKING, db_index=True)
    last_checked = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["ward", "location"]

    def __str__(self):
        return f"{self.reference} {self.get_light_type_display()} – {self.location}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("PL", 4)
        super().save(*args, **kwargs)


class WorkOrder(SyncModel):
    """Engineering services job card: road maintenance, lighting repairs, council buildings, plant."""

    class Kind(models.TextChoices):
        ROAD = "ROAD", "Road maintenance / grading / patching"
        DRAINAGE = "DRAIN", "Drainage / culverts"
        LIGHTING = "LIGHT", "Public lighting repair"
        BUILDING = "BUILDING", "Council building maintenance"
        PLANT = "PLANT", "Plant & vehicle repair"
        WATER = "WATER", "Water / borehole repair"
        OTHER = "OTHER", "Other engineering work"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        DONE = "DONE", "Work done – awaiting sign-off"
        CLOSED = "CLOSED", "Signed off"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.ROAD)
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=200)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    road = models.ForeignKey(Road, null=True, blank=True, on_delete=models.SET_NULL, related_name="work_orders")
    light = models.ForeignKey(PublicLight, null=True, blank=True, on_delete=models.SET_NULL, related_name="work_orders")
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="work_orders")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    materials = models.TextField(blank=True, help_text="Materials used")
    labour_days = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="USD")
    completion_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    signed_off_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["status", "due_date", "-created_at"]

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("WO", 5)
        super().save(*args, **kwargs)


# ================================================== Administration (charter: records management)
class RecordFile(SyncModel):
    """Registry: council files and records – where they are, who has them, how long to keep them."""

    class Status(models.TextChoices):
        IN_REGISTRY = "IN", "In the registry"
        ON_LOAN = "LOAN", "Out on loan"
        ARCHIVED = "ARCHIVED", "Archived"
        DISPOSED = "DISPOSED", "Disposed (retention ended)"

    file_number = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=10, choices=Department.choices)
    category = models.CharField(max_length=60, blank=True, help_text="e.g. Personnel, Stands, Contracts, Council minutes")
    location = models.CharField(max_length=100, help_text="Cabinet / shelf / box")
    confidential = models.BooleanField(default=False)
    opened_on = models.DateField(default=timezone.localdate)
    retain_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.IN_REGISTRY, db_index=True)
    borrowed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    borrowed_at = models.DateTimeField(null=True, blank=True)
    due_back = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["file_number"]

    def __str__(self):
        return f"{self.file_number} {self.title}"
