from django.db import OperationalError, connection
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from ipaddress import ip_address


class TrustedProxyIPMiddleware(MiddlewareMixin):
    """Private Caddy proxy overwrites this header with the socket client IP."""

    def process_request(self, request):
        if not getattr(settings, "TRUST_PROXY_CLIENT_IP", False):
            return
        try:
            request.META["REMOTE_ADDR"] = str(ip_address(request.META.get("HTTP_X_ADMINT_CLIENT_IP", "")))
        except ValueError:
            pass


class SQLiteBusyMiddleware(MiddlewareMixin):
    """Give a retryable response when local SQLite cannot accept concurrent writes."""

    def process_exception(self, request, exception):
        if connection.vendor != "sqlite" or not isinstance(exception, OperationalError):
            return None
        if "locked" not in str(exception).lower():
            return None
        response = JsonResponse({"detail": "The database is busy. Please try again in a moment."}, status=503)
        response["Retry-After"] = "1"
        response["Cache-Control"] = "no-store"
        return response
