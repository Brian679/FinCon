from django.conf import settings


def council(request):
    ctx = {"COUNCIL": settings.COUNCIL}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_notifications"] = user.notifications.filter(is_read=False, is_deleted=False).count()
        if hasattr(user, "nav_items"):
            ctx["nav_items"] = user.nav_items()
    return ctx
