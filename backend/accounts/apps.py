from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Users & roles"

    def ready(self):
        from core import audit

        from .models import User

        audit.register(User)
