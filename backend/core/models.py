import hashlib
import json
import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.utils import timezone


class Department(models.TextChoices):
    """Departments as set out in the Client Charter 2026-2030."""

    EXECUTIVE = "EXEC", "Office of the Chief Executive Officer"
    ADMINISTRATION = "ADMIN", "Administration"
    FINANCE = "FINANCE", "Finance"
    INTERNAL_AUDIT = "AUDIT", "Internal Audit"
    SOCIAL_SERVICES = "SOCIAL", "Social Services"
    TECHNICAL_SERVICES = "TECH", "Technical Services"


class Currency(models.TextChoices):
    USD = "USD", "US Dollar"
    ZWG = "ZWG", "Zimbabwe Gold"


class SyncQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(is_deleted=False)


class SyncModel(models.Model):
    """Base for every record that is replicated to the mobile apps.

    * UUID primary keys let phones create records offline without clashing.
    * ``updated_at`` drives incremental "pull" synchronisation.
    * Records are never hard-deleted - ``is_deleted`` is synchronised instead
      so that offline devices learn about removals and the audit trail stays
      complete.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", editable=False,
    )
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects = SyncQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])


class SequenceCounter(models.Model):
    """Gap-free document numbering (receipts, vouchers, licences ...)."""

    key = models.CharField(max_length=60, unique=True)
    value = models.PositiveIntegerField(default=0)

    @classmethod
    def next(cls, prefix: str, width: int = 6) -> str:
        year = timezone.localdate().year
        key = f"{prefix}-{year}"
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(key=key)
            counter.value += 1
            counter.save(update_fields=["value"])
            return f"{prefix}-{year}-{counter.value:0{width}d}"

    def __str__(self):
        return f"{self.key}={self.value}"


class ServiceStandard(models.Model):
    """Service standards published in the Client Charter."""

    class Unit(models.TextChoices):
        MINUTES = "MIN", "Minutes"
        HOURS = "HRS", "Hours"
        WORKING_DAYS = "WDAYS", "Working days"
        IMMEDIATE = "NOW", "Immediately"
        RINGS = "RINGS", "Rings"
        ALWAYS = "ALWAYS", "At all times"

    code = models.SlugField(max_length=60, unique=True)
    service = models.CharField(max_length=120)
    standard_text = models.CharField(max_length=120)
    value = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=6, choices=Unit.choices)
    is_digital = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["is_digital", "id"]

    def __str__(self):
        return f"{self.service}: {self.standard_text}"


def _jsonable(value):
    return json.loads(json.dumps(value, default=str))


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):  # pragma: no cover - defensive
        raise PermissionDenied("Audit trail entries cannot be modified.")

    def delete(self):
        raise PermissionDenied("Audit trail entries cannot be deleted.")


class AuditLog(models.Model):
    """Immutable, hash-chained audit trail.

    Every entry stores a SHA-256 hash of its own content plus the hash of the
    previous entry. Altering or removing any row directly in the database
    breaks the chain, which ``python manage.py verify_audit_chain`` (and the
    Audit Trail page) will detect.
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", "Created"
        UPDATE = "UPDATE", "Updated"
        DELETE = "DELETE", "Deleted"
        LOGIN = "LOGIN", "Logged in"
        LOGOUT = "LOGOUT", "Logged out"
        LOGIN_FAILED = "LOGIN_FAILED", "Failed login"
        APPROVE = "APPROVE", "Approved"
        REJECT = "REJECT", "Rejected"
        VOID = "VOID", "Voided / cancelled"
        PAYMENT = "PAYMENT", "Payment"
        EXPORT = "EXPORT", "Exported / printed"
        SYNC = "SYNC", "Mobile sync"
        ACCESS_DENIED = "DENIED", "Access denied"
        OTHER = "OTHER", "Other"

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    username = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=10, blank=True, db_index=True)
    action = models.CharField(max_length=12, choices=Action.choices, db_index=True)
    model = models.CharField(max_length=100, blank=True, db_index=True)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    channel = models.CharField(max_length=10, default="web")
    prev_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, blank=True, editable=False)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-timestamp", "-id"]
        permissions = [("view_full_audit", "Can view the full audit trail")]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.username} {self.action} {self.model} {self.object_repr}"

    def compute_hash(self) -> str:
        payload = json.dumps(
            {
                "ts": self.timestamp.isoformat(),
                "user": self.username,
                "action": self.action,
                "model": self.model,
                "object_id": self.object_id,
                "changes": self.changes,
                "message": self.message,
                "prev": self.prev_hash,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied("Audit trail entries cannot be modified.")
        self.changes = _jsonable(self.changes or {})
        with transaction.atomic():
            last = AuditLog.objects.select_for_update().order_by("-id").only("hash").first()
            self.prev_hash = last.hash if last else ""
            self.hash = self.compute_hash()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Audit trail entries cannot be deleted.")

    @classmethod
    def verify_chain(cls):
        """Return (ok, first_broken_entry_id)."""
        prev = ""
        for entry in cls.objects.order_by("id").iterator():
            if entry.prev_hash != prev or entry.compute_hash() != entry.hash:
                return False, entry.id
            prev = entry.hash
        return True, None


class Notification(SyncModel):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class IdempotencyKey(models.Model):
    """Prevents duplicate submissions when offline web forms are replayed."""

    key = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)
    redirect_to = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MessageLog(models.Model):
    """Every SMS / email / in-app reminder or invitation sent to a client."""

    class Channel(models.TextChoices):
        SMS = "SMS", "SMS"
        EMAIL = "EMAIL", "Email"
        APP = "APP", "App / portal notification"

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    channel = models.CharField(max_length=5, choices=Channel.choices)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    to = models.CharField(max_length=200, blank=True)
    account_number = models.CharField(max_length=30, blank=True, db_index=True)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=10, default="SENT")
    error = models.CharField(max_length=255, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    campaign = models.CharField(max_length=60, blank=True, help_text="e.g. 'Licence reminder – Checheche'")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} to {self.to}: {self.subject or self.body[:40]}"
