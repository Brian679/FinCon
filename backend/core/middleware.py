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
