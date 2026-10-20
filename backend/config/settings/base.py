import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,api").split(",")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "apps.accounts",
    "apps.characters",
    "apps.spatial",
    "apps.encounters",
    "apps.collection",
    "apps.community",
    "apps.news",
    "apps.batch",
]
MIDDLEWARE = [
    "config.middleware.RequestLogMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
APPEND_SLASH = False
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.environ.get("POSTGRES_DB", "chii_world"),
        "USER": os.environ.get("POSTGRES_USER", "chii_world"),
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    }
}
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "config.api.Pagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "config.api.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "SIGNING_KEY": os.environ["JWT_SIGNING_KEY"],
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.LoginSerializer",
    "TOKEN_REFRESH_SERIALIZER": "apps.accounts.serializers.RefreshSerializer",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "CHII WORLD API",
    "DESCRIPTION": "Phase 0–10: core MVP, community, reviewed news and batch operations.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "CategoryEnum": "apps.community.models.Post.Category",
        "NewsCategoryEnum": "apps.news.models.Category.choices",
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "config.schema.add_error_responses",
    ],
}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "chii.errors": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "chii.requests": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # RequestLogMiddleware records sanitized paths. Avoid dev-server query/body logs.
        "django.server": {"handlers": ["console"], "level": "CRITICAL", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "CRITICAL", "propagate": False},
    },
}

ENCOUNTER_TTL_SECONDS = 180

# Broker connectivity is needed only when publishing or running a worker.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or (
    "amqp://"
    + quote(os.environ.get("RABBITMQ_USER", ""), safe="")
    + ":"
    + quote(os.environ.get("RABBITMQ_PASSWORD", ""), safe="")
    + "@"
    + os.environ.get("RABBITMQ_HOST", "localhost")
    + ":5672/"
    + quote(os.environ.get("RABBITMQ_VHOST", "chii"), safe="")
)
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = False
CELERY_TASK_DEFAULT_QUEUE = "batch.execute"
CELERY_TASK_DEFAULT_EXCHANGE = "batch.execute"
CELERY_TASK_DEFAULT_EXCHANGE_TYPE = "direct"
CELERY_TASK_DEFAULT_ROUTING_KEY = "batch.execute"
CELERY_TASK_QUEUES = {
    "batch.execute": {
        "exchange": "batch.execute",
        "routing_key": "batch.execute",
        "durable": True,
        "queue_arguments": {"x-queue-type": "classic"},
    },
}
CELERY_TASK_ROUTES = {"batch.execute": {"queue": "batch.execute"}}
CELERY_TASK_CREATE_MISSING_QUEUES = False
CELERY_TASK_DEFAULT_DELIVERY_MODE = "persistent"
CELERY_BROKER_TRANSPORT_OPTIONS = {"confirm_publish": True}
CELERY_BROKER_CONNECTION_TIMEOUT = 5
CELERY_TASK_PUBLISH_RETRY = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_TIMEZONE = "UTC"
LOGGING["loggers"]["chii.tasks"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}

# RabbitMQ 4.3 rejects non-durable, non-exclusive control/event queues.
CELERY_CONTROL_QUEUE_EXCLUSIVE = True
CELERY_EVENT_QUEUE_EXCLUSIVE = True
