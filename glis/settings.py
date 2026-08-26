from pathlib import Path
import environ
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(DJANGO_DEBUG=(bool, True), SECURE_SSL_REDIRECT=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-development-key-change-me")
# A clean source extraction is a local-development checkout. Deployments must
# explicitly set DJANGO_DEBUG=False (see the production checklist in README.md).
DEBUG = env.bool("DJANGO_DEBUG", default=True)
#ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost", "testserver"])
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
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",

    "django_htmx",
    "widget_tweaks",

    "apps.core",
    "apps.accounts",
    "apps.cms",
    "apps.tickets",
    "apps.knowledge",
    "apps.ai",
    "apps.orchestrator",

    "django_json_widget",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "allauth.account.middleware.AccountMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    "django_htmx.middleware.HtmxMiddleware",

    "csp.middleware.CSPMiddleware",
]

ROOT_URLCONF = "glis.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages", "apps.cms.context_processors.site_context",
        "apps.accounts.context_processors.auth_provider_context", "apps.tickets.context_processors.notification_context",
    ]},
}]
WSGI_APPLICATION = "glis.wsgi.application"
ASGI_APPLICATION = "glis.asgi.application"

# db_engine = env("DATABASE_ENGINE", default="sqlite").lower()
# if db_engine == "mssql":
#     DATABASES = {"default": {
#         "ENGINE": "mssql", "NAME": env("DATABASE_NAME"), "HOST": env("DATABASE_HOST"),
#         "PORT": env("DATABASE_PORT", default="1433"), "USER": env("DATABASE_USER"),
#         "PASSWORD": env("DATABASE_PASSWORD"),
#         "OPTIONS": {
#             "driver": env("DATABASE_DRIVER", default="ODBC Driver 18 for SQL Server"),
#             "extra_params": env("DATABASE_EXTRA_PARAMS", default="TrustServerCertificate=yes"),
#         },
#     }}
# else:
#     DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / env("DATABASE_NAME", default="db.sqlite3")}}


DATABASE_URL="postgresql://postgres.rrbytxusjypzaqviqcrr:mHIIS7Iy1tLmlI48@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"
db_engine = "postgresql"
if DATABASE_URL:
    # Production / Vercel
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Local development
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

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

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Manifest storage intentionally fails when collectstatic has not produced a
    # manifest, so use it only for production. Django's runserver can then serve
    # source assets directly during local development on Windows, Linux or macOS.
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
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "portal:dashboard"
LOGOUT_REDIRECT_URL = "public:home"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = env("ALLAUTH_EMAIL_VERIFICATION", default="optional")
ACCOUNT_UNIQUE_EMAIL = True
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend", "allauth.account.auth_backends.AuthenticationBackend"]
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.GLISSocialAccountAdapter"
SOCIALACCOUNT_PROVIDERS = {}
if env("GOOGLE_CLIENT_ID", default=""):
    SOCIALACCOUNT_PROVIDERS["google"] = {"APP": {"client_id": env("GOOGLE_CLIENT_ID"), "secret": env("GOOGLE_CLIENT_SECRET", default=""), "key": ""}, "SCOPE": ["profile", "email"], "AUTH_PARAMS": {"access_type": "online"}}
if env("MICROSOFT_CLIENT_ID", default=""):
    SOCIALACCOUNT_PROVIDERS["microsoft"] = {"APP": {"client_id": env("MICROSOFT_CLIENT_ID"), "secret": env("MICROSOFT_CLIENT_SECRET", default=""), "key": ""}, "TENANT": env("MICROSOFT_TENANT", default="common")}

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# CONTENT_SECURITY_POLICY = {"DIRECTIVES": {
#     "default-src": ["'self'"],
#     "script-src": ["'self'", "https://cdn.jsdelivr.net", "https://unpkg.com", "https://cdn.plot.ly"],
#     "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://fonts.googleapis.com"],
#     "font-src": ["'self'", "https://cdn.jsdelivr.net", "https://fonts.gstatic.com", "data:"],
#     "img-src": ["'self'", "data:", "blob:"],
#     "connect-src": ["'self'"], "frame-ancestors": ["'none'"],
#     "base-uri": ["'self'"], "form-action": ["'self'"],
# }}


CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {

        "default-src": [
            "'self'",
        ],

        # Required for Django admin + JSON widget initialization.
        #
        # Do NOT add data: here.
        # We avoid JSONEditor's Ace/code mode instead.
        "script-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.jsdelivr.net",
            "https://unpkg.com",
            "https://cdn.plot.ly",
        ],

        # Kept for libraries that legitimately use blob workers.
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
        ],

        "connect-src": [
            "'self'",
        ],

        "frame-ancestors": [
            "'none'",
        ],

        "base-uri": [
            "'self'",
        ],

        "form-action": [
            "'self'",
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
#VANNA_DB_SCHEMA = env("VANNA_DB_SCHEMA", default="dbo" if db_engine == "mssql" else "main")

if db_engine == "mssql":
    default_schema = "dbo"
elif db_engine == "postgresql":
    default_schema = "public"
else:
    default_schema = "main"
VANNA_DB_SCHEMA = env("VANNA_DB_SCHEMA",default=default_schema,)

CHROMA_PERSIST_DIRECTORY = env(
    "CHROMA_PERSIST_DIRECTORY", default=str(BASE_DIR / "data" / "chroma")
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@glis.local")
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "INFO"}}