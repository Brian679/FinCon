from django.db import models
from django.conf import settings
from services.models import ServiceRequest

def upload_to_documents(instance, filename):
    return f'documents/{instance.uploaded_by.id}/{filename}'

class Document(models.Model):
    DOCUMENT_TYPE_CHOICES = (
        ('financial_record', 'Financial Record'),
        ('tax_document', 'Tax Document'),
        ('permit', 'Permit'),
        ('certificate', 'Certificate'),
        ('form', 'Form'),
        ('report', 'Report'),
        ('other', 'Other'),
    )
    
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploaded_documents')
    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=upload_to_documents)
    description = models.TextField(blank=True)
    file_size = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} - {self.uploaded_by.username}"
