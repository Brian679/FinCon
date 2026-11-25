from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User

# The administration site is restricted to the ICT / System Administrator
# (superuser). Other staff - including the CEO - are refused even if they
# know the URL.
admin.site.site_header = "Chipinge RDC – Restricted System Administration"
admin.site.site_title = "Chipinge RDC admin"
admin.site.index_title = "System administration"
admin.site.has_permission = lambda request: bool(
    request.user.is_active and request.user.is_superuser and getattr(request.user, "is_staff_member", False)
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "get_full_name", "user_type", "department", "role", "employee_number", "is_active", "last_login")
    list_filter = ("user_type", "department", "role", "is_active")
    search_fields = ("username", "first_name", "last_name", "employee_number", "email", "national_id")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Council", {"fields": ("user_type", "department", "role", "employee_number", "phone", "national_id", "ward",
                                "must_change_password", "failed_login_attempts", "locked_until")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Council", {"fields": ("first_name", "last_name", "email", "user_type", "role", "employee_number", "phone")}),
    )
