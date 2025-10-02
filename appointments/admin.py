from django.contrib import admin
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['client', 'subject', 'appointment_date', 'status', 'consultant']
    list_filter = ['status', 'appointment_date']
    search_fields = ['client__username', 'subject', 'description']
    raw_id_fields = ['client', 'consultant']
