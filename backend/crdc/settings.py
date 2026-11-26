"""
Chipinge Rural District Council - Council Management System (CRDC-CMS)
Django settings.

Configuration is read from environment variables (or a .env file) so the same
code runs in development (SQLite) and production (PostgreSQL / MySQL).
"""
from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY", default="dev-only-insecure-key-change-me")
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="*", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("DJANGO_CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework_simplejwt",
    # Council apps
    "core",
    "accounts",
    "finance",
    "workflow",
    "departments",
    "portal",
    "api",
]

MIDDLEWARE = [
    "core.middleware.SiteRoutingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.AuditContextMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware",
]

ROOT_URLCONF = "crdc.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.council",
            ],
        },
    },
]

WSGI_APPLICATION = "crdc.wsgi.application"

# SQL database. Default is SQLite for development; set DATABASE_URL for
# PostgreSQL in production, e.g. postgres://user:pass@host:5432/crdc
DATABASES = {
    "default": dj_database_url.parse(
        config("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.LockoutModelBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:home"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", default=60 * 60 * 8, cast=int)  # one working day
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "api.authentication.CouncilJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle", "rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "2000/hour", "anon": "60/minute"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=config("JWT_ACCESS_HOURS", default=8, cast=int)),
    # Long refresh lifetime so field officers can work offline for days and
    # still sync without having to log in again.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_DAYS", default=30, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "UPDATE_LAST_LOGIN": True,
}

# ---------------------------------------------------------------------------
# Two websites from one system
#   * public client site  (e.g. https://www.chipingerdc.gov.zw)  - residents, ratepayers, shop owners
#   * staff site          (e.g. https://staff.chipingerdc.gov.zw) - council employees only
# When the request's host is in neither list (development, localhost) both
# sites are served together: client pages at /, staff pages at /staff/.
# ---------------------------------------------------------------------------
CLIENT_HOSTS = config("CLIENT_HOSTS", default="", cast=Csv())
STAFF_HOSTS = config("STAFF_HOSTS", default="", cast=Csv())
PUBLIC_SITE_URL = config("PUBLIC_SITE_URL", default="")   # e.g. https://www.chipingerdc.gov.zw
STAFF_SITE_URL = config("STAFF_SITE_URL", default="")     # e.g. https://staff.chipingerdc.gov.zw

# SMS reminders / invitations: "console" (logged only) or "http" (generic HTTP SMS gateway)
SMS_BACKEND = config("SMS_BACKEND", default="console")
SMS_HTTP_URL = config("SMS_HTTP_URL", default="")
SMS_HTTP_TOKEN = config("SMS_HTTP_TOKEN", default="")
SMS_SENDER_ID = config("SMS_SENDER_ID", default="ChipingeRDC")

# ---------------------------------------------------------------------------
# Council business rules
# ---------------------------------------------------------------------------
COUNCIL = {
    "NAME": "Chipinge Rural District Council",
    "SHORT_NAME": "Chipinge RDC",
    "CHARTER": "Client Charter 2026-2030",
    "VISION": "A Provider of Responsive Quality Municipal Services by 2030.",
    "MISSION": "To provide municipal services that improve the quality of life of Chipinge District Residents.",
    "PLEDGE": (
        "We are committed to responsive, transparent, accountable and quality municipal service delivery "
        "for sustainable development and improved quality of life for all residents of Chipinge District."
    ),
    "ADDRESS": "858 E.D. Mnangagwa Street, P.O. Box 19, Chipinge",
    "PHONE": "+263 227 204 5631-5",
    "EMAIL": "info@chipingerdc.gov.zw",
    "FACEBOOK": "chipingerdc",
    "X": "@chipingerdc",
    "BASE_CURRENCY": "USD",
    "NUMBER_OF_WARDS": 30,
}
# Payment vouchers / requisitions at or above this amount (base currency)
# need the CEO's authorisation in addition to the Treasurer's approval.
CEO_APPROVAL_THRESHOLD = config("CEO_APPROVAL_THRESHOLD", default=5000, cast=float)

# Online payments: "simulated" (development/testing) or "paynow".
PAYMENT_GATEWAY = config("PAYMENT_GATEWAY", default="simulated")
PAYNOW_INTEGRATION_ID = config("PAYNOW_INTEGRATION_ID", default="")
PAYNOW_INTEGRATION_KEY = config("PAYNOW_INTEGRATION_KEY", default="")
PAYNOW_RESULT_URL = config("PAYNOW_RESULT_URL", default="")
PAYNOW_RETURN_URL = config("PAYNOW_RETURN_URL", default="")

EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="no-reply@chipingerdc.gov.zw")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
