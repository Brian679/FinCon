from django.contrib import admin

from .models import AuditLog, Notification, SequenceCounter, ServiceStandard


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "username", "department", "action", "model", "object_repr", "ip_address", "channel")
    list_filter = ("action", "department", "channel", "model")
    search_fields = ("username", "object_repr", "message", "object_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ServiceStandard)
class ServiceStandardAdmin(admin.ModelAdmin):
    list_display = ("service", "standard_text", "value", "unit", "is_digital")


admin.site.register(Notification)
admin.site.register(SequenceCounter)
