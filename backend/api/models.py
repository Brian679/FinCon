from django.conf import settings
from django.db import models


class SyncOperation(models.Model):
    """Every offline operation pushed by a phone is recorded once, keyed by the
    UUID the phone generated. Re-sending the same operation (e.g. after a
    dropped connection) returns the stored result instead of applying it
    twice."""

    op_id = models.UUIDField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sync_operations")
    device_id = models.CharField(max_length=64, blank=True)
    op_type = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10)  # applied | rejected
    error = models.TextField(blank=True)
    result = models.JSONField(default=dict, blank=True)
    client_created_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.op_type} {self.status} ({self.user})"
