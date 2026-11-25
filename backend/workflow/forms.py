from django import forms
from django.contrib.auth import get_user_model

from core.crud import BaseModelForm, date_widgets

from .models import Complaint, Correspondence, ServiceRequest, Task

User = get_user_model()


def staff_queryset(department=None):
    qs = User.objects.filter(user_type=User.UserType.STAFF, is_active=True)
    return qs.filter(department=department) if department else qs


class TaskForm(BaseModelForm):
    class Meta:
        model = Task
        fields = ["kind", "title", "description", "department", "assigned_to", "priority", "due_date"]
        widgets = date_widgets("due_date")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.has_cap("tasks.assign_any"):
            self.fields["department"].choices = [(user.department, user.get_department_display())]
            self.fields["assigned_to"].queryset = staff_queryset(user.department)
        else:
            self.fields["assigned_to"].queryset = staff_queryset()
        self.fields["assigned_to"].help_text = "Leave blank to send to the Head of the department"


class ComplaintForm(BaseModelForm):
    class Meta:
        model = Complaint
        fields = ["kind", "channel", "name", "phone", "email", "ward", "department", "subject", "details"]


class ServiceRequestForm(BaseModelForm):
    class Meta:
        model = ServiceRequest
        fields = ["category", "description", "location", "ward", "reporter_name", "reporter_phone", "latitude", "longitude"]


class CorrespondenceForm(BaseModelForm):
    class Meta:
        model = Correspondence
        fields = ["sender", "sender_contact", "subject", "date_received", "department", "assigned_to", "status", "file_reference",
                  "response_summary"]
        widgets = date_widgets("date_received")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = staff_queryset()
