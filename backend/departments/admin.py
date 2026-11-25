from django.contrib import admin

from . import models

for m in [models.LeaveRequest, models.StandApplication, models.Project, models.AuditFinding]:
    admin.site.register(m)
