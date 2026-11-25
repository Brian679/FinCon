from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import audit
from core.crud import GenericListView
from core.models import AuditLog, Department

from .decorators import cap_required
from .forms import LoginForm, StaffUserForm, StyledPasswordChangeForm
from .models import User


class LoginView(auth_views.LoginView):
    """Staff website login. Residents / businesses are sent to the client site."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        if form.get_user().is_client:
            audit.log(AuditLog.Action.ACCESS_DENIED, form.get_user(), user=form.get_user(), message="Client tried to use the staff website")
            form.add_error(None, "This website is for council staff only. Residents and businesses: please use the council's online services site.")
            return self.form_invalid(form)
        return super().form_valid(form)


@require_POST
def logout_view(request):
    was_client = request.user.is_authenticated and request.user.is_client
    if request.user.is_authenticated:
        audit.log(AuditLog.Action.LOGOUT, request.user, request=request)
    logout(request)
    return redirect("portal:login" if was_client or getattr(request, "site_kind", "") == "client" else "accounts:login")


@login_required
def home(request):
    if request.user.is_client:
        return redirect("portal:dashboard")
    if request.user.is_ceo:
        return redirect("core:executive")
    return redirect("core:dashboard")


@login_required
def password_change(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        audit.log(AuditLog.Action.UPDATE, user, message="Password changed")
        messages.success(request, "Your password has been changed.")
        return redirect("accounts:home")
    return render(request, "accounts/password_change.html", {"form": form, "title": "Change password"})


class UserListView(GenericListView):
    model = User
    required_caps = ("users.manage", "users.view")
    title = "Council staff accounts"
    columns = [("Username", "username"), ("Name", lambda u: u.get_full_name()), ("Employee no.", "employee_number"),
               ("Department", "department"), ("Role", "role"), ("Active", "is_active"), ("Last login", "last_login")]
    search_fields = ["username", "first_name", "last_name", "employee_number", "email"]
    filter_field = "department"
    detail_url_name = "accounts:user_edit"

    def base_queryset(self):
        return User.objects.filter(user_type=User.UserType.STAFF)

    def filter_choices(self):
        return Department.choices

    def row_url(self, obj):
        from django.urls import reverse

        return reverse("accounts:user_edit", args=[obj.pk]) if self.request.user.has_cap("users.manage") else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.user.has_cap("users.manage"):
            from django.urls import reverse

            ctx["create_url"] = reverse("accounts:user_new")
        return ctx


@cap_required("users.manage")
def user_form(request, pk=None):
    instance = get_object_or_404(User, pk=pk, user_type=User.UserType.STAFF) if pk else None
    form = StaffUserForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Staff account {user.username} saved. Give the user their temporary password; they must change it at first login.")
        return redirect("accounts:users")
    return render(request, "generic/form.html", {"form": form, "title": f"Edit {instance}" if instance else "Register council employee"})


@cap_required("users.manage")
@require_POST
def user_unlock(request, pk):
    user = get_object_or_404(User, pk=pk)
    User.objects.filter(pk=pk).update(locked_until=None, failed_login_attempts=0)
    audit.log(AuditLog.Action.UPDATE, user, message="Account unlocked by administrator")
    messages.success(request, f"{user.username} unlocked.")
    return redirect("accounts:user_edit", pk=pk)
