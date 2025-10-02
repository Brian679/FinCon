from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'user_type', 'company_name', 'phone', 'is_active']
    list_filter = ['user_type', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'company_name', 'phone']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('user_type', 'phone', 'company_name', 'address')}),
    )
