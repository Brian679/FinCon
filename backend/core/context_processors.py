from django.conf import settings


def council(request):
    kind = getattr(request, "site_kind", "client")
    ctx = {
        "COUNCIL": settings.COUNCIL,
        "SITE_KIND": kind,
        "STAFF_LOGIN_URL": (settings.STAFF_SITE_URL.rstrip("/") + "/staff/login/") if settings.STAFF_SITE_URL else "/staff/login/",
        "PUBLIC_URL": settings.PUBLIC_SITE_URL.rstrip("/") + "/" if settings.PUBLIC_SITE_URL else "/",
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_notifications"] = user.notifications.filter(is_read=False, is_deleted=False).count()
        if hasattr(user, "nav_items"):
            ctx["nav_items"] = user.nav_items()
    return ctx
