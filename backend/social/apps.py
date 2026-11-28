from django.apps import AppConfig


class SocialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "social"
    verbose_name = "Social services – CAMPFIRE, natural resources, farms & water"

    def ready(self):
        from core import audit

        from . import models as m

        audit.register(m.WildlifeRecord, m.HuntingQuota, m.TrophyHunt, m.ResourcePermit, m.Extraction, m.Farm, m.WaterPoint,
                       m.HealthInspection, m.SanitationFacility, m.SocialFacility)
