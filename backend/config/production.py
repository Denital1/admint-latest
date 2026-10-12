"""Validated public deployment settings. Development uses settings.py."""
import os
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

def require(condition, message):
    if not condition:
        raise ImproperlyConfigured(message)

require(os.environ.get("DJANGO_DEBUG") == "0", "Production requires DJANGO_DEBUG=0.")
require(len(SECRET_KEY) >= 50 and len(set(SECRET_KEY)) >= 5 and not SECRET_KEY.lower().startswith(("replace", "change", "dev-only")), "Generate a unique random DJANGO_SECRET_KEY with at least 50 characters.")
require(DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql", "Production requires a PostgreSQL DATABASE_URL.")
database_password = DATABASES["default"].get("PASSWORD", "")
require(len(database_password) >= 20 and not database_password.lower().startswith(("replace", "change")), "Set a private strong PostgreSQL password.")
require(CACHE_URL.startswith(("redis://", "rediss://")), "Production requires a shared Redis CACHE_URL.")
require(bool(os.environ.get("DJANGO_ALLOWED_HOSTS")) and bool(ALLOWED_HOSTS) and "*" not in ALLOWED_HOSTS, "Set explicit DJANGO_ALLOWED_HOSTS for production.")
frontend = urlsplit(FRONTEND_URL)
require(frontend.scheme == "https" and bool(frontend.hostname) and not frontend.username and frontend.path in {"", "/"} and not frontend.query and not frontend.fragment, "FRONTEND_URL must be the public HTTPS origin.")
require(frontend.hostname in ALLOWED_HOSTS, "The frontend hostname must appear in DJANGO_ALLOWED_HOSTS.")
require(FRONTEND_URL in CSRF_TRUSTED_ORIGINS and all(urlsplit(origin).scheme == "https" for origin in CSRF_TRUSTED_ORIGINS + CORS_ALLOWED_ORIGINS), "Production CSRF/CORS origins must use HTTPS and include the frontend CSRF origin.")

DEBUG = False
TRUST_PROXY_CLIENT_IP = True
# The supplied Caddy proxy overwrites the client IP header; backend has no public port.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
STATIC_ROOT = os.environ.get("DJANGO_STATIC_ROOT", str(BASE_DIR / "staticfiles"))
