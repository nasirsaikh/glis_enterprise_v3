from pathlib import Path
import environ
import dj_database_url
import os

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DJANGO_DEBUG=(bool, True), SECURE_SSL_REDIRECT=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-development-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # django CMS
    "cms",
    "menus",
    "treebeard",
    "sekizai",
    "parler",
    "taggit",


    "filer",
    "easy_thumbnails",
    "djangocms_text",
    "djangocms_text_ckeditor5",
    "djangocms_link",
    "djangocms_picture",
    "djangocms_file",
    "djangocms_video",
    "djangocms_audio",
    "djangocms_snippet",    
    "djangocms_icon",
    "djangocms_frontend",
    "djangocms_frontend.contrib.accordion",
    "djangocms_frontend.contrib.alert",
    "djangocms_frontend.contrib.badge",
    "djangocms_frontend.contrib.card",
    "djangocms_frontend.contrib.carousel",
    "djangocms_frontend.contrib.collapse",
    "djangocms_frontend.contrib.content",
    "djangocms_frontend.contrib.grid",
    "djangocms_frontend.contrib.image",
    "djangocms_frontend.contrib.jumbotron",
    "djangocms_frontend.contrib.link",
    "djangocms_frontend.contrib.listgroup",
    "djangocms_frontend.contrib.media",
    "djangocms_frontend.contrib.tabs",
    "djangocms_frontend.contrib.utilities",
    "djangocms_versioning",
    "djangocms_alias",
    "djangocms_moderation",
    "djangocms_history",
    #"djangocms_attribute_fields",
    "djangocms_transfer",

    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",

    "django_htmx",
    "widget_tweaks",

    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "drf_spectacular",

    "django_summernote",

    "apps.core",
    "apps.accounts",
    "apps.tickets",
    "apps.knowledge",
    "apps.ai",
    "apps.orchestrator",

    "django_json_widget",
    "django_ckeditor_5",
    "location_field",
    "django_visitor_tracker",
    "apps.job_center.apps.JobCenterConfig",
]

MIDDLEWARE = [
    "cms.middleware.utils.ApphookReloadMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",

    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django_visitor_tracker.middleware.RequestLoggingMiddleware",

    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    "cms.middleware.user.CurrentUserMiddleware",
    "cms.middleware.page.CurrentPageMiddleware",
    "cms.middleware.toolbar.ToolbarMiddleware",
    "cms.middleware.language.LanguageCookieMiddleware",

    "django_htmx.middleware.HtmxMiddleware",
    "csp.middleware.CSPMiddleware",
]

ROOT_URLCONF = "glis.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.template.context_processors.i18n",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "sekizai.context_processors.sekizai",
            "cms.context_processors.cms_settings",
            "apps.accounts.context_processors.auth_provider_context",
            "apps.tickets.context_processors.notification_context",
        ],
    },
}]

WSGI_APPLICATION = "glis.wsgi.application"
ASGI_APPLICATION = "glis.asgi.application"

db_engine = env("DATABASE_ENGINE", default="sqlite").lower()
if db_engine == "mssql":
    DATABASES = {"default": {
        "ENGINE": "mssql", "NAME": env("DATABASE_NAME"), "HOST": env("DATABASE_HOST"),
        "PORT": env("DATABASE_PORT", default="1433"), "USER": env("DATABASE_USER"),
        "PASSWORD": env("DATABASE_PASSWORD"),
        "OPTIONS": {
            "driver": env("DATABASE_DRIVER", default="ODBC Driver 18 for SQL Server"),
            "extra_params": env("DATABASE_EXTRA_PARAMS", default="TrustServerCertificate=yes"),
        },
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / env("DATABASE_NAME", default="db.sqlite3")}}



# DATABASE_URL="postgresql://postgres.djqaqvcsjfgauraibflk:Takaful%40Oman%401@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
# db_engine = "postgresql"
# if DATABASE_URL:
#     DATABASES = {
#         "default": dj_database_url.parse(
#             DATABASE_URL,
#             conn_max_age=600,
#             conn_health_checks=True,
#         )
#     }
# else:
#     DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.sqlite3",
#             "NAME": BASE_DIR / "db.sqlite3",
#         }
#     }


THUMBNAIL_PROCESSORS = [
    'easy_thumbnails.processors.scale_and_crop',
    'easy_thumbnails.processors.autocrop',
    'easy_thumbnails.processors.colorspace',
    'easy_thumbnails.processors.filters',
    #'filer.thumbnail_processors.scale_and_crop_with_image_subject',
    "filer.thumbnail_processors.scale_and_crop_with_subject_location",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("ar", "العربية")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Muscat"
USE_I18N = True
USE_TZ = True
LANGUAGE_COOKIE_NAME = "django_language"
LANGUAGE_COOKIE_AGE = 365 * 24 * 60 * 60
LANGUAGE_COOKIE_PATH = "/"
LANGUAGE_COOKIE_SAMESITE = "Lax"
LANGUAGE_COOKIE_SECURE = not DEBUG
LANGUAGE_COOKIE_HTTPONLY = False

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SITE_ID = 1

CMS_TEMPLATES = [
    ("cms/glis_page.html", "GLIS content Page"),
    ("cms/glis_home.html", "GLIS home Page"),
    ("cms/glis_about.html", "GLIS about Page"),
    ("cms/glis_contact.html", "GLIS Contact Page"),
    ("cms/glis_download.html", "GLIS Download Page"),
    ("cms/glis_portal_page.html", "GLIS portal Page"),
]

CMS_PERMISSION = True
CMS_TREE_BACKEND = "mptree"
CMS_PAGE_CACHE = not DEBUG
CMS_PLACEHOLDER_CACHE = not DEBUG
CMS_PLUGIN_CACHE = not DEBUG
CMS_LANGUAGES = {
    1: [
        {"code": "en", "name": "English", "fallbacks": ["ar"], "public": True},
        {"code": "ar", "name": "العربية", "fallbacks": ["en"], "public": True},
    ],
    "default": {"fallbacks": ["en"], "redirect_on_fallback": True, "public": True},
}


CSP_FORM_ACTION = (
    "'self'",
    "http://127.0.0.1:8000",
    "https://google.com",
)


LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "portal:dashboard"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = env("ALLAUTH_EMAIL_VERIFICATION", default="optional")
ACCOUNT_UNIQUE_EMAIL = True
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend", "allauth.account.auth_backends.AuthenticationBackend"]
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.GLISSocialAccountAdapter"
# SOCIALACCOUNT_PROVIDERS = {
#     "google": {
#         "SCOPE" : ["profile","email"],
#         "AUTH_PARAMS" : {"access_type" : "online"}
#     }
# }
# if env("GOOGLE_CLIENT_ID", default=""):
#     SOCIALACCOUNT_PROVIDERS["google"] = {"APP": {"client_id": env("GOOGLE_CLIENT_ID"), "secret": env("GOOGLE_CLIENT_SECRET", default=""), "key": ""}, "SCOPE": ["profile", "email"], "AUTH_PARAMS": {"access_type": "online"}}
# if env("MICROSOFT_CLIENT_ID", default=""):
#     SOCIALACCOUNT_PROVIDERS["microsoft"] = {"APP": {"client_id": env("MICROSOFT_CLIENT_ID"), "secret": env("MICROSOFT_CLIENT_SECRET", default=""), "key": ""}, "TENANT": env("MICROSOFT_TENANT", default="common")}

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "OAUTH_PKCE_ENABLED": True,
    },

    "microsoft": {
        "SCOPE": [
            "openid",
            "profile",
            "email",
            "User.Read",
        ],
        "SETTINGS": {
            "tenant": env(
                "MICROSOFT_TENANT",
                default="common",
            ),
        },
    },
}

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
# django CMS frontend editing uses same-origin frames/sideframes.
X_FRAME_OPTIONS = "SAMEORIGIN"
SECURE_REFERRER_POLICY = "same-origin"

# CONTENT_SECURITY_POLICY = {
#     "DIRECTIVES": {
#         "default-src": ["'self'"],
#         "script-src": [
#             "'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net",
#             "https://unpkg.com", "https://cdn.plot.ly",
#         ],
#         "worker-src": ["'self'", "blob:"],
#         "style-src": [
#             "'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net",
#             "https://fonts.googleapis.com",
#         ],
#         "font-src": [
#             "'self'", "data:", "https://cdn.jsdelivr.net", "https://fonts.gstatic.com",
#         ],
#         "img-src": ["'self'", "data:", "blob:"],
#         "connect-src": ["'self'", "https://cdn.jsdelivr.net"],
#         "frame-src": ["'self'"],
#         "frame-ancestors": ["'self'"],
#         "base-uri": ["'self'"],
#         "form-action": ["'self'"],
#     }
# }

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],

        "script-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.jsdelivr.net",
            "https://unpkg.com",
            "https://cdn.plot.ly",
        ],

        "worker-src": [
            "'self'",
            "blob:",
        ],

        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.jsdelivr.net",
            "https://fonts.googleapis.com",
        ],

        "font-src": [
            "'self'",
            "data:",
            "https://cdn.jsdelivr.net",
            "https://fonts.gstatic.com",
        ],

        "img-src": [
            "'self'",
            "data:",
            "blob:",
            "https://tile.openstreetmap.org",
            "https://*.tile.openstreetmap.org",                
        ],

        "connect-src": [
            "'self'",
            "https://cdn.jsdelivr.net",
            "https://accounts.google.com",
            "https://login.microsoftonline.com",
            "https://graph.microsoft.com",
        ],

        "frame-src": [
            "'self'",
            "https://accounts.google.com",
            "https://login.microsoftonline.com",
        ],

        "frame-ancestors": [
            "'self'",
        ],

        "base-uri": [
            "'self'",
        ],

        "form-action": [
            "'self'",
            "https://accounts.google.com",
            "https://login.microsoftonline.com",
        ],
    }
}

AI_PROVIDER = env("AI_PROVIDER", default="mock")
AI_ENDPOINT = env("AI_ENDPOINT", default="")
AI_MODEL = env("AI_MODEL", default="")
AI_API_KEY = env("AI_API_KEY", default="")
OLLAMA_HOST = env("OLLAMA_HOST", default="http://127.0.0.1:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="qwen2.5-coder:7b")
OLLAMA_EMBED_MODEL = env("OLLAMA_EMBED_MODEL", default="nomic-embed-text")
OLLAMA_CONTEXT_WINDOW = env.int("OLLAMA_CONTEXT_WINDOW", default=8192)
OLLAMA_TEMPERATURE = env.float("OLLAMA_TEMPERATURE", default=0.1)

if db_engine == "mssql":
    default_schema = "dbo"
elif db_engine == "postgresql":
    default_schema = "public"
else:
    default_schema = "main"

VANNA_DB_SCHEMA = env("VANNA_DB_SCHEMA", default=default_schema)
CHROMA_PERSIST_DIRECTORY = env("CHROMA_PERSIST_DIRECTORY", default=str(BASE_DIR / "data" / "chroma"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@glis.local")
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.office365.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "30"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.GLISPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.api.exceptions.glis_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "GLIS Enterprise Platform API",
    "DESCRIPTION": "REST API for GLIS Enterprise Platform",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"jwtAuth": []}],
}


JOB_CENTER_ENABLED = True
JOB_CENTER_MAX_WORKERS = 10
JOB_CENTER_LOCK_TTL_SECONDS = 90
JOB_CENTER_HEARTBEAT_SECONDS = 30