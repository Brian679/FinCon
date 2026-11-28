from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workflow"
    verbose_name = "Tasks, complaints & service requests"

    def ready(self):
        from core import audit

        from . import models as m

        audit.register(m.Task, m.Complaint, m.ServiceRequest, m.Correspondence, m.Attachment, m.PhoneMessage)
