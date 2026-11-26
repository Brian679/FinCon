from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core.models import Department

from . import roles


class User(AbstractUser):
    """Council staff member or registered client (ratepayer / resident).

    Staff accounts can only be created by the System Administrator through the
    restricted administration pages; there is no staff self-registration.
    """

    class UserType(models.TextChoices):
        STAFF = "STAFF", "Council staff"
        CLIENT = "CLIENT", "Client / community member"

    user_type = models.CharField(max_length=6, choices=UserType.choices, default=UserType.STAFF, db_index=True)
    department = models.CharField(max_length=10, choices=Department.choices, blank=True, db_index=True)
    role = models.CharField(max_length=30, choices=roles.ROLE_CHOICES, blank=True, db_index=True)
    employee_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    national_id = models.CharField(max_length=30, blank=True)
    ward = models.PositiveSmallIntegerField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False)
    annual_leave_days = models.PositiveSmallIntegerField("Annual leave days a year", default=22)
    tokens_valid_after = models.DateTimeField(null=True, blank=True, editable=False,
                                              help_text="App logins issued before this time no longer work (password changed, user deactivated …)")
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["department", "last_name", "first_name"]

    def __str__(self):
        name = self.get_full_name() or self.username
        if self.is_staff_member and self.role:
            return f"{name} ({self.role_label})"
        return name

    # ------------------------------------------------------------------ RBAC
    @property
    def is_staff_member(self):
        return self.user_type == self.UserType.STAFF

    @property
    def is_client(self):
        return self.user_type == self.UserType.CLIENT

    @property
    def role_label(self):
        return roles.role_label(self.role)

    @property
    def level(self):
        return roles.role_level(self.role)

    @property
    def is_head(self):
        return self.level in (roles.Level.HEAD, roles.Level.EXECUTIVE)

    @property
    def is_ceo(self):
        return self.role == "CEO"

    @property
    def is_sysadmin(self):
        return self.is_superuser or self.role == "SYSADMIN"

    @property
    def capabilities(self):
        if not self.is_active:
            return set()
        if self.is_client:
            return set(roles.CLIENT_CAPS)
        caps = roles.capabilities_for(self.role)
        if self.is_superuser:
            caps |= {"users.manage", "audit.view_trail", "audit.view_all", "system.settings"}
        return caps

    def has_cap(self, *caps):
        """True if the user holds ANY of the capabilities given."""
        mine = self.capabilities
        return any(c in mine for c in caps)

    def sees_all_departments(self):
        return self.is_ceo or self.has_cap("audit.view_all")

    def clean(self):
        if self.user_type == self.UserType.STAFF and self.role:
            expected = roles.role_department(self.role)
            if self.department and expected and self.department != expected:
                raise ValidationError({"role": f"The role '{self.role_label}' belongs to the {Department(expected).label} department."})
            self.department = expected or self.department
        if self.user_type == self.UserType.CLIENT:
            self.department = ""
            self.role = ""

    def save(self, *args, **kwargs):
        if self.user_type == self.UserType.STAFF and self.role and not self.department:
            self.department = roles.role_department(self.role) or ""
        super().save(*args, **kwargs)

    # ------------------------------------------------------------- lockout
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= self.MAX_FAILED_LOGINS:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=self.LOCKOUT_MINUTES)
            self.failed_login_attempts = 0
        User.objects.filter(pk=self.pk).update(
            failed_login_attempts=self.failed_login_attempts, locked_until=self.locked_until
        )

    def register_successful_login(self):
        if self.failed_login_attempts or self.locked_until:
            User.objects.filter(pk=self.pk).update(failed_login_attempts=0, locked_until=None)

    # ------------------------------------------------------------ navigation
    def nav_items(self):
        from .navigation import build_nav

        return build_nav(self)


def safe_reverse(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return "#"



from django.db.models.signals import pre_save  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(pre_save, sender=User)
def _sign_out_devices(sender, instance, **kwargs):
    """A new password, a deactivated account or a new role ends every app session (lost / stolen phone)."""
    if not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).values("password", "is_active", "role").first()
    if old and (old["password"] != instance.password or (old["is_active"] and not instance.is_active) or old["role"] != instance.role):
        now = timezone.now()
        instance.tokens_valid_after = now
        # also written directly, because callers often save with update_fields=["password", …]
        sender.objects.filter(pk=instance.pk).update(tokens_valid_after=now)
