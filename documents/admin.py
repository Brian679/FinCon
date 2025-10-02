from django.contrib import admin
from .models import Document

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'uploaded_by', 'document_type', 'uploaded_at']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['title', 'uploaded_by__username']
    raw_id_fields = ['uploaded_by', 'service_request']
