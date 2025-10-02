from django.contrib import admin
from .models import ServiceCategory, Service, ServiceRequest

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['order', 'name']

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ['client', 'service', 'status', 'assigned_to', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['client__username', 'service__name']
    raw_id_fields = ['client', 'service', 'assigned_to']
