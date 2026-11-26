from django import forms
from django.utils import timezone
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
            from django.db.models import Q

            from accounts.roles import ROLES, Level

            head_roles = [code for code, (_l, _d, lvl) in ROLES.items() if lvl in (Level.HEAD, Level.EXECUTIVE)]
            self.fields["assigned_to"].queryset = staff_queryset().filter(Q(department=user.department) | Q(role__in=head_roles))
            self.fields["department"].help_text = "Another department's task goes to its Head of Department."
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


# ------------------------------------------------------------ funds requests
from django.forms import inlineformset_factory  # noqa: E402

from core.models import Department  # noqa: E402

from .models import FundsRequest, FundsRequestLine, Memo  # noqa: E402


class FundsRequestForm(BaseModelForm):
    class Meta:
        model = FundsRequest
        fields = ["request_type", "title", "purpose", "destination", "depart_date", "return_date", "travellers", "currency", "needed_by",
                  "requires_payment", "payee_name", "payment_method", "payment_details", "budget_line", "attachment"]
        widgets = date_widgets("depart_date", "return_date", "needed_by")

    GROUPS = [
        ("Request", ["request_type", "title", "purpose", "needed_by", "attachment"]),
        ("Travel details (travel & subsistence only)", ["destination", "depart_date", "return_date", "travellers"]),
        ("Payment", ["requires_payment", "currency", "payee_name", "payment_method", "payment_details", "budget_line"]),
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from finance.models import BudgetLine

        dept = user.department if user else None
        self.fields["budget_line"].queryset = BudgetLine.objects.alive().filter(department=dept, financial_year=timezone.localdate().year)
        self.fields["budget_line"].required = False
        self.fields["budget_line"].help_text = "Your department's budget vote (optional – Finance can choose)"
        self.fields["payee_name"].help_text = "Leave blank to pay the requester"
        self.fields["title"].widget.attrs["placeholder"] = "e.g. T&S for ward 12 water point inspection"

    def groups(self):
        return [(title, [self[n] for n in names]) for title, names in self.GROUPS]

    def clean(self):
        d = super().clean()
        if d.get("depart_date") and d.get("return_date") and d["return_date"] < d["depart_date"]:
            self.add_error("return_date", "The return date is before the departure date.")
        return d


class LineForm(BaseModelForm):
    class Meta:
        model = FundsRequestLine
        fields = ["description", "quantity", "unit_cost"]

    def has_changed(self):
        return bool(self.data.get(self.add_prefix("description"))) or (self.instance.pk is not None and super().has_changed())


LineFormSet = inlineformset_factory(FundsRequest, FundsRequestLine, form=LineForm, extra=4, can_delete=True, min_num=1, validate_min=True)


class MemoForm(BaseModelForm):
    class Meta:
        model = Memo
        fields = ["kind", "to_department", "to_user", "priority", "subject", "body"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["to_user"].queryset = staff_queryset().order_by("department", "first_name")
        self.fields["to_user"].label_from_instance = lambda u: f"{u.get_full_name() or u.username} – {u.role_label} ({u.get_department_display()})"
        self.fields["to_department"].choices = Department.choices

    def clean(self):
        d = super().clean()
        if d.get("to_user") and d.get("to_department") and d["to_user"].department != d["to_department"]:
            self.add_error("to_user", "That officer is not in the department you chose.")
        return d
