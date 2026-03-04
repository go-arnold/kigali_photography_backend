from pathlib import Path
import environ
from celery.schedules import crontab


BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
)


DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
]
LOCAL_APPS = [
    "apps.webhook",
    "apps.clients",
    "apps.conversations",
    "apps.automation",
    "apps.rag",
    "apps.dashboard",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
# DATABASES["default"]["OPTIONS"] = {"options": "-c search_path=public"}

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "kigali.sqlite3",
#     }
# }


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = "django-db"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "Africa/Kigali"


CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": "none"}
CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": "none"}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "300/min",
    },
}
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Kigali"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

WHATSAPP = {
    "PHONE_NUMBER_ID": env("WA_PHONE_NUMBER_ID"),
    "ACCESS_TOKEN": env("WA_ACCESS_TOKEN"),
    "WEBHOOK_VERIFY_TOKEN": env("WA_WEBHOOK_VERIFY_TOKEN"),
    "APP_SECRET": env("WA_APP_SECRET"),
    "BASE_URL": "https://graph.facebook.com/v20.0",
}

CLAUDE = {
    "API_KEY": "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",
    "DEFAULT_MODEL": env("CLAUDE_DEFAULT_MODEL", default="claude-haiku-3-5-20251001"),
    "ESCALATION_MODEL": env("CLAUDE_ESCALATION_MODEL", default="claude-sonnet-4-6"),
    "MAX_INPUT_TOKENS": env.int("CLAUDE_MAX_INPUT_TOKENS", default=2000),
    "MAX_OUTPUT_TOKENS": env.int("CLAUDE_MAX_OUTPUT_TOKENS", default=500),
    "CONVERSATION_BUDGET": env.int("CLAUDE_CONVERSATION_BUDGET", default=20000),
}

STUDIO = {
    "NAME": env("STUDIO_NAME", default="Kigali Photography"),
    "WHATSAPP": env("STUDIO_WHATSAPP", default=""),
    "LOCATION": env("STUDIO_LOCATION", default="Kigali"),
    "HOURS": env("STUDIO_HOURS", default="Mon-Sat 9AM-6PM"),
    "BOOKING_FEE_RWF": env.int("BOOKING_FEE_RWF", default=20000),
}


CELERY_BEAT_SCHEDULE = {
    "send-scheduled-messages": {
        "task": "automation.send_scheduled_messages",
        "schedule": 300,
    },
    "expire-approval-items": {
        "task": "automation.expire_approval_items",
        "schedule": 1800,
    },
    "summarize-long-conversations": {
        "task": "automation.summarize_long_conversations",
        "schedule": 3600,
    },
    "schedule-birthday-messages": {
        "task": "automation.schedule_birthday_messages",
        "schedule": crontab(hour=7, minute=0),
    },
}


CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["https://senior-madeleine-matabar-93648cd5.koyeb.app/"],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[
        "https://senior-madeleine-matabar-93648cd5.koyeb.app/",
    ],
)
