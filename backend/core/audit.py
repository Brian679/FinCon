"""Audit trail helpers.

``AuditContextMiddleware`` stores the current request in a context variable so
that model signals can attribute every change to a user, IP address and
channel (web / api / mobile) without each view having to pass it around.
"""
import contextvars
from decimal import Decimal

from django.db.models.signals import post_save, pre_save
from django.db.models.fields.files import FieldFile

from .models import AuditLog

_request = contextvars.ContextVar("audit_request", default=None)
_actor = contextvars.ContextVar("audit_actor", default=None)


def set_request(request):
    return _request.set(request)


def reset_request(token):
    _request.reset(token)


def set_actor(user):
    """Attribute changes to ``user`` when there is no HTTP request (API/mobile sync, commands)."""
    return _actor.set(user)


def current_request():
    return _request.get()


def current_user():
    actor = _actor.get()
    if actor is not None:
        return actor
    req = _request.get()
    user = getattr(req, "user", None) if req is not None else None
    return user if (user is not None and user.is_authenticated) else None


def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log(action, obj=None, *, message="", changes=None, user=None, request=None, model_label=None):
    request = request or current_request()
    user = user or current_user()
    channel = "web"
    if request is not None:
        path = request.path or ""
        if path.startswith("/api/"):
            channel = "mobile" if "sync" in path or request.META.get("HTTP_X_CLIENT_APP") else "api"
    entry = AuditLog(
        user=user if (user is not None and getattr(user, "pk", None)) else None,
        username=getattr(user, "username", "") or "",
        department=getattr(user, "department", "") or "",
        action=action,
        model=model_label or (obj._meta.label if obj is not None else ""),
        object_id=str(getattr(obj, "pk", "") or "") if obj is not None else "",
        object_repr=(str(obj)[:255] if obj is not None else ""),
        changes=changes or {},
        message=message,
        ip_address=_client_ip(request) if request is not None else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request is not None else ""),
        channel=channel,
    )
    entry.save()
    return entry


def _value(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, FieldFile):
        return v.name or ""
    return v


def _snapshot(instance):
    data = {}
    for f in instance._meta.concrete_fields:
        if f.name in ("updated_at", "password", "last_login"):
            continue
        data[f.attname] = _value(getattr(instance, f.attname))
    return data


_AUDITED = set()


def _pre_save(sender, instance, **kwargs):
    if instance._state.adding or not instance.pk:
        instance._audit_before = None
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        instance._audit_before = _snapshot(old)
    except sender.DoesNotExist:
        instance._audit_before = None


def _post_save(sender, instance, created, **kwargs):
    after = _snapshot(instance)
    if created:
        log(AuditLog.Action.CREATE, instance, changes={k: [None, v] for k, v in after.items() if v not in (None, "")})
        return
    before = getattr(instance, "_audit_before", None) or {}
    diff = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    if not diff:
        return
    action = AuditLog.Action.DELETE if diff.get("is_deleted") == [False, True] else AuditLog.Action.UPDATE
    log(action, instance, changes=diff)


def register(*models):
    """Record every create / update / soft-delete of ``models`` in the audit trail."""
    for model in models:
        if model in _AUDITED:
            continue
        _AUDITED.add(model)
        pre_save.connect(_pre_save, sender=model, weak=False, dispatch_uid=f"audit_pre_{model._meta.label}")
        post_save.connect(_post_save, sender=model, weak=False, dispatch_uid=f"audit_post_{model._meta.label}")
