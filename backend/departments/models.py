"""Department-specific registers for Administration (HR), Social Services,
Technical Services and Internal Audit."""
from django.conf import settings
from django.db import models
from django.utils import timezone

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
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.employee} {self.get_leave_type_display()} {self.start_date} - {self.end_date}"

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
