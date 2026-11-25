from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from core import audit
from core.models import AuditLog


class LockoutModelBackend(ModelBackend):
    """Username/password authentication with brute-force lockout and auditing.

    Used by both the web login and the mobile app's token endpoint.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            User().set_password(password)  # equalise timing
            audit.log(AuditLog.Action.LOGIN_FAILED, message=f"Unknown username '{username}'", request=request)
            return None
        if user.is_locked:
            audit.log(AuditLog.Action.LOGIN_FAILED, user, user=user, message="Account temporarily locked", request=request)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            user.register_successful_login()
            audit.log(AuditLog.Action.LOGIN, user, user=user, message="Successful login", request=request)
            return user
        user.register_failed_login()
        audit.log(AuditLog.Action.LOGIN_FAILED, user, user=user, message="Wrong password", request=request)
        return None
