from django.contrib import admin

from . import models

for m in [models.Task, models.TaskComment, models.Complaint, models.ServiceRequest, models.Correspondence]:
    admin.site.register(m)
