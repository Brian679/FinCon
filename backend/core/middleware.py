from . import audit


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = audit.set_request(request)
        try:
            return self.get_response(request)
        finally:
            audit.reset_request(token)


class SiteRoutingMiddleware:
    """Serve the public client site and the staff site from different hosts."""

    STAFF_PREFIXES = ("/staff/", "/system-admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from django.urls import set_urlconf

        host = request.get_host().split(":")[0].lower()
        if host in [h.lower() for h in settings.STAFF_HOSTS]:
            request.urlconf = "crdc.urls_staff"
            request.site_kind = "staff"
        elif host in [h.lower() for h in settings.CLIENT_HOSTS]:
            request.urlconf = "crdc.urls_public"
            request.site_kind = "client"
        else:
            request.site_kind = "staff" if request.path.startswith(self.STAFF_PREFIXES) else "client"
        if getattr(request, "urlconf", None):
            set_urlconf(request.urlconf)
        return self.get_response(request)
