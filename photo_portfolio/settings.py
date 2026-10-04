"""Django settings for the photo portfolio project."""
from pathlib import Path
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def env_list(name, default=""):
    raw_value = os.environ.get(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


RUNNING_ON_RAILWAY = bool(
    os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
)
DEBUG = env_bool("DEBUG", default=not RUNNING_ON_RAILWAY)
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("SECRET_KEY is required when DEBUG=False.")
    SECRET_KEY = "django-insecure-local-development-key-change-before-production"

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost" if DEBUG else "",
)

railway_public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if RUNNING_ON_RAILWAY:
    ALLOWED_HOSTS.append("healthcheck.railway.app")
if railway_public_domain:
    ALLOWED_HOSTS.append(railway_public_domain)

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if railway_public_domain:
    CSRF_TRUSTED_ORIGINS.append(f"https://{railway_public_domain}")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "portfolio",
    "inquiries",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "portfolio.middleware.IndexingMiddleware",
]

ROOT_URLCONF = "photo_portfolio.urls"

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
                "django.template.context_processors.i18n",
                "portfolio.context_processors.site_identity",
            ],
        },
    },
]

WSGI_APPLICATION = "photo_portfolio.wsgi.application"


DATABASES = {"default": dj_database_url.parse(
    os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    conn_max_age=60,
    conn_health_checks=True,
)}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["OPTIONS"] = {"timeout": 20}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("fr", "Fran\u00e7ais")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = os.environ.get("TIME_ZONE", "America/Toronto")
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_URL = "/media/"
railway_volume_mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
media_base = Path(railway_volume_mount) if railway_volume_mount else BASE_DIR
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT") or media_base / "media")
PRIVATE_MEDIA_ROOT = Path(os.environ.get("PRIVATE_MEDIA_ROOT") or media_base / ("private" if railway_volume_mount else "private_media"))
STORAGES["default"] = {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": MEDIA_ROOT, "base_url": MEDIA_URL},
}
STORAGES["originals"] = {
    "BACKEND": "portfolio.storage.PrivateFileSystemStorage",
    "OPTIONS": {"location": PRIVATE_MEDIA_ROOT},
}
USE_S3 = env_bool("USE_S3")
if USE_S3:
    s3_options = {
        "access_key": os.environ["AWS_ACCESS_KEY_ID"],
        "secret_key": os.environ["AWS_SECRET_ACCESS_KEY"],
        "endpoint_url": os.environ.get("AWS_S3_ENDPOINT_URL") or None,
        "region_name": os.environ.get("AWS_S3_REGION_NAME", "auto"),
        "default_acl": None,
        "file_overwrite": False,
    }
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {**s3_options, "bucket_name": os.environ["PUBLIC_MEDIA_BUCKET"],
                    "querystring_auth": False,
                    "custom_domain": os.environ.get("PUBLIC_MEDIA_DOMAIN") or None,
                    "object_parameters": {"CacheControl": "public, max-age=31536000, immutable"}},
    }
    STORAGES["originals"] = {
        "BACKEND": "portfolio.storage.PrivateS3Storage",
        "OPTIONS": {**s3_options, "bucket_name": os.environ["PRIVATE_MEDIA_BUCKET"]},
    }
PHOTO_MAX_BYTES = int(os.environ.get("PHOTO_MAX_BYTES", str(40 * 1024 * 1024)))
PHOTO_MAX_PIXELS = int(os.environ.get("PHOTO_MAX_PIXELS", "60000000"))
PHOTO_RENDITION_EDGES = (480, 768, 1280, 1600, 1920, 2560, 3840, 5120)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


SITE_NAME = "MrSaintJ Photography"
PHOTOGRAPHER_NAME = "Justin St-Laurent"
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "").rstrip("/")
INDEXING_ENABLED = env_bool("INDEXING_ENABLED", False)
LLMS_TXT_ENABLED = env_bool("LLMS_TXT_ENABLED", True)
PIXEL_CAMERA_TRANSITIONS_ENABLED = env_bool("PIXEL_CAMERA_TRANSITIONS_ENABLED", True)
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
BING_SITE_VERIFICATION = os.environ.get("BING_SITE_VERIFICATION", "")
INDEXNOW_ENABLED = env_bool("INDEXNOW_ENABLED", False)
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
CONTACT_FROM_EMAIL = os.environ.get("CONTACT_FROM_EMAIL", "")
CONTACT_TO_EMAIL = os.environ.get("CONTACT_TO_EMAIL", "")
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "inquiries.backends.ResendBackend" if RESEND_API_KEY
                               else "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = CONTACT_FROM_EMAIL or "portfolio@localhost"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = 10
INQUIRY_RATE_LIMIT = int(os.environ.get("INQUIRY_RATE_LIMIT", "5"))
INQUIRY_RATE_WINDOW = int(os.environ.get("INQUIRY_RATE_WINDOW", "3600"))
TRUSTED_PROXY_CIDRS = env_list("TRUSTED_PROXY_CIDRS")
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "INFO"}}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
