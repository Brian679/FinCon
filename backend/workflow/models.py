"""Cross-departmental work: tasks & requests from the CEO / heads of
department, client complaints & feedback, service requests (faults) and the
correspondence register - each tracked against the Client Charter standards."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import Department, SequenceCounter, SyncModel


class Priority(models.TextChoices):
    LOW = "LOW", "Low"
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class Task(SyncModel):
    class Kind(models.TextChoices):
        TASK = "TASK", "Task / assignment"
        REQUEST = "REQUEST", "Request for information / report"
        MEMO = "MEMO", "Memo / directive"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        DONE = "DONE", "Completed - awaiting sign-off"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.TASK)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tasks_assigned")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="tasks")
    department = models.CharField(max_length=10, choices=Department.choices)
    priority = models.CharField(max_length=6, choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = SequenceCounter.next("TSK", 5)
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return bool(self.due_date and self.due_date < timezone.localdate() and self.status in (self.Status.OPEN, self.Status.IN_PROGRESS))


class TaskComment(SyncModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.task.reference}"


class Complaint(SyncModel):
    """Complaints, compliments, suggestions and enquiries (Charter: Feedback &
    Complaints - acknowledged within 48 hours)."""

    class Kind(models.TextChoices):
        COMPLAINT = "COMPLAINT", "Complaint"
        COMPLIMENT = "COMPLIMENT", "Compliment"
        SUGGESTION = "SUGGESTION", "Suggestion"
        ENQUIRY = "ENQUIRY", "Enquiry"

    class Channel(models.TextChoices):
        CEO = "CEO", "Chief Executive Officer"
        SUGGESTION_BOX = "BOX", "Suggestion box"
        OFFICE = "OFFICE", "Council offices"
        EMAIL = "EMAIL", "Email"
        PHONE = "PHONE", "Telephone"
        CONSULTATION = "CONSULT", "Community consultation"
        SOCIAL_MEDIA = "SOCIAL", "Social media"
        PORTAL = "PORTAL", "Client web portal"
        APP = "APP", "Client mobile app"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        ACKNOWLEDGED = "ACK", "Acknowledged"
        IN_PROGRESS = "IN_PROGRESS", "Being attended to"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.COMPLAINT)
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.OFFICE)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints")
    name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    department = models.CharField(max_length=10, choices=Department.choices, default=Department.ADMINISTRATION)
    subject = models.CharField(max_length=200)
    details = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints_assigned")
    acknowledge_due = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    response_due = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.subject}"

    def save(self, *args, **kwargs):
        from core.sla import due_from_standard

        if not self.reference:
            self.reference = SequenceCounter.next("FB", 5)
        if self._state.adding:
            now = self.created_at or timezone.now()
            self.acknowledge_due = self.acknowledge_due or due_from_standard("acknowledge-complaints", now)
            self.response_due = self.response_due or due_from_standard("feedback-on-enquiries", now)
        super().save(*args, **kwargs)

    @property
    def ack_breached(self):
        if not self.acknowledge_due:
            return False
        reference = self.acknowledged_at or timezone.now()
        return reference > self.acknowledge_due


class ServiceRequest(SyncModel):
    """Service delivery requests / fault reports from the community."""

    # category: (label, department, charter standard code)
    CATEGORIES = {
        "WATER_FAULT": ("Major water fault / burst pipe", Department.SOCIAL_SERVICES, "attend-water-faults"),
        "BOREHOLE": ("Borehole breakdown", Department.SOCIAL_SERVICES, "attend-water-faults"),
        "SEWER": ("Sewer blockage / ablutions", Department.SOCIAL_SERVICES, "attend-water-faults"),
        "REFUSE": ("Refuse not collected / illegal dumping", Department.SOCIAL_SERVICES, "process-applications"),
        "HEALTH": ("Public health concern", Department.SOCIAL_SERVICES, "process-applications"),
        "WILDLIFE": ("Human-wildlife conflict", Department.SOCIAL_SERVICES, "attend-water-faults"),
        "FIRE": ("Veld fire / fire incident", Department.SOCIAL_SERVICES, "attend-water-faults"),
        "DISASTER": ("Disaster / emergency", Department.SOCIAL_SERVICES, "attend-water-faults"),
        "ROAD": ("Road damage / pothole / bridge", Department.TECHNICAL_SERVICES, "process-applications"),
        "LIGHTING": ("Public lighting fault", Department.TECHNICAL_SERVICES, "process-applications"),
        "BUILDING": ("Illegal structure / development control", Department.TECHNICAL_SERVICES, "process-applications"),
        "BILLING": ("Billing / account query", Department.FINANCE, "feedback-on-enquiries"),
        "OTHER": ("Other", Department.ADMINISTRATION, "feedback-on-enquiries"),
    }
    CATEGORY_CHOICES = [(k, v[0]) for k, v in CATEGORIES.items()]

    class Status(models.TextChoices):
        REPORTED = "REPORTED", "Reported"
        ASSIGNED = "ASSIGNED", "Assigned to officer"
        IN_PROGRESS = "IN_PROGRESS", "Work in progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"
        REJECTED = "REJECTED", "Not council responsibility"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES)
    department = models.CharField(max_length=10, choices=Department.choices, editable=False)
    description = models.TextField()
    location = models.CharField(max_length=255)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="service_requests")
    reporter_name = models.CharField(max_length=200, blank=True)
    reporter_phone = models.CharField(max_length=30, blank=True)
    priority = models.CharField(max_length=6, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REPORTED, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="service_requests_assigned")
    due_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.get_category_display()} - {self.location}"

    def save(self, *args, **kwargs):
        from core.sla import due_from_standard

        if not self.reference:
            self.reference = SequenceCounter.next("SR", 5)
        _label, dept, std = self.CATEGORIES.get(self.category, self.CATEGORIES["OTHER"])
        self.department = dept
        if self._state.adding and not self.due_at:
            self.due_at = due_from_standard(std, self.created_at or timezone.now())
            if self.category in ("WATER_FAULT", "FIRE", "DISASTER", "WILDLIFE"):
                self.priority = Priority.URGENT
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return bool(self.due_at and self.due_at < timezone.now() and self.status not in (self.Status.RESOLVED, self.Status.CLOSED, self.Status.REJECTED))


class Correspondence(SyncModel):
    """Incoming letters register - Charter: respond within 7 working days."""

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        ASSIGNED = "ASSIGNED", "Assigned"
        RESPONDED = "RESPONDED", "Responded"
        FILED = "FILED", "Filed (no response needed)"

    reference = models.CharField(max_length=30, unique=True, editable=False)
    sender = models.CharField(max_length=200)
    sender_contact = models.CharField(max_length=200, blank=True)
    subject = models.CharField(max_length=255)
    date_received = models.DateField(default=timezone.localdate)
    department = models.CharField(max_length=10, choices=Department.choices)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    response_due = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    response_summary = models.TextField(blank=True)
    file_reference = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["-date_received", "-created_at"]
        verbose_name_plural = "correspondence"

    def __str__(self):
        return f"{self.reference} {self.subject}"

    def save(self, *args, **kwargs):
        from core.sla import due_from_standard

        if not self.reference:
            self.reference = SequenceCounter.next("COR", 5)
        if self._state.adding and not self.response_due:
            self.response_due = due_from_standard("respond-to-correspondence")
        super().save(*args, **kwargs)
