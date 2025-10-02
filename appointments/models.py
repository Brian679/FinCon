from django.db import models
from django.conf import settings

class Appointment(models.Model):
    STATUS_CHOICES = (
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled'),
    )
    
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments')
    consultant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='consultations')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    appointment_date = models.DateTimeField()
    duration = models.IntegerField(default=60, help_text="Duration in minutes")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    meeting_link = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-appointment_date']
    
    def __str__(self):
        return f"{self.client.username} - {self.subject} on {self.appointment_date}"
