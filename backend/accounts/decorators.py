from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from core import audit
from core.models import AuditLog


def _deny(request, caps):
    audit.log(AuditLog.Action.ACCESS_DENIED, message=f"{request.method} {request.path} needs {', '.join(caps)}", request=request)
    raise PermissionDenied("You do not have permission to perform this action.")


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff_member:
            _deny(request, ["staff"])
        return view(request, *args, **kwargs)

    return wrapper


def cap_required(*caps):
    """Allow access if the user holds any of ``caps``."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_staff_member or not request.user.has_cap(*caps):
                _deny(request, caps)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


class CapRequiredMixin(LoginRequiredMixin):
    required_caps: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff_member or (self.required_caps and not request.user.has_cap(*self.required_caps)):
            _deny(request, self.required_caps or ("staff",))
        return super().dispatch(request, *args, **kwargs)
