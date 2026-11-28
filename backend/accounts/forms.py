from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from core.crud import BootstrapFormMixin
from core.models import Department

from . import roles
from .models import User


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    error_messages = {
        "invalid_login": "Incorrect username or password. After 5 failed attempts the account is locked for 15 minutes.",
        "inactive": "This account has been deactivated. Contact the ICT administrator.",
    }


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class StaffUserForm(BootstrapFormMixin, forms.ModelForm):
    """Used by the System Administrator to register council employees."""

    temporary_password = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank when editing to keep the current password. The user must change it at first login.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "employee_number", "national_id", "role", "department",
                  "annual_leave_days", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].required = True
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["annual_leave_days"].required = False
        grouped = {}
        for code, (label, dept, _lvl) in roles.ROLES.items():
            grouped.setdefault(Department(dept).label if dept else "Any department", []).append((code, label))
        self.fields["role"].choices = [("", "---------")] + list(grouped.items())
        self.fields["department"].required = False
        self.fields["department"].help_text = "Only for interns – other roles belong to their role's department."

    def clean(self):
        data = super().clean()
        role = data.get("role")
        if role in roles.ANY_DEPARTMENT_ROLES and not data.get("department"):
            self.add_error("department", "Choose the department this intern works in.")
        return data
        if not self.instance.pk:
            self.fields["temporary_password"].required = True

    def clean_annual_leave_days(self):
        return self.cleaned_data.get("annual_leave_days") or 22

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = User.UserType.STAFF
        user.department = roles.role_department(user.role) or self.cleaned_data.get("department") or ""
        pwd = self.cleaned_data.get("temporary_password")
        if pwd:
            user.set_password(pwd)
            user.must_change_password = True
        if commit:
            user.save()
        return user


class ClientRegistrationForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)
    # How the person is connected to a stand / house / shop – owners are linked to the owner's account, renters get their own.
    RELATIONSHIPS = [("NONE", "I don't own or rent a stand yet"), ("OWNER", "I own a stand / house"),
                     ("SHOP", "I own a stand and run a shop / business on it"), ("RENT", "I rent a house / shop from its owner"),
                     ("TENANT", "I lease council premises (shop / market stall)")]
    relationship = forms.ChoiceField(choices=RELATIONSHIPS, initial="NONE", label="Your stand / property")
    stand_number = forms.CharField(max_length=40, required=False, label="Stand number",
                                   help_text="The stand number on your bill, lease or agreement of sale.")
    area = forms.ModelChoiceField(queryset=None, required=False, label="Shopping centre / township")
    location = forms.CharField(max_length=200, required=False, label="…or type the place (township, village, growth point)")
    business_name = forms.CharField(max_length=200, required=False, label="Shop / business name (if any)")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "phone", "national_id", "ward"]
        labels = {"username": "Username (you will log in with this)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("first_name", "last_name", "phone", "national_id"):
            self.fields[f].required = True
        from finance.models import TradingArea

        self.fields["area"].queryset = TradingArea.objects.alive().filter(is_active=True)
        self.order_fields(["first_name", "last_name", "username", "email", "phone", "national_id", "ward", "relationship", "stand_number", "area", "location",
                           "business_name", "password1", "password2"])

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            raise forms.ValidationError("The passwords do not match.")
        if data.get("relationship", "NONE") != "NONE" and not data.get("stand_number"):
            self.add_error("stand_number", "Enter the stand number so we can link it to you.")
        from django.contrib.auth.password_validation import validate_password

        if data.get("password1"):
            validate_password(data["password1"])
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = User.UserType.CLIENT
        user.role = ""
        user.department = ""
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user
