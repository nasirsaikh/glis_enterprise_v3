from django.conf import settings
from django.db import OperationalError, ProgrammingError
from allauth.socialaccount.models import SocialApp
from .models import AccountPolicy


def auth_provider_context(request):
    try:
        policy = AccountPolicy.load()
        database_providers = set(SocialApp.objects.values_list("provider", flat=True))
    except (OperationalError, ProgrammingError):
        policy, database_providers = None, set()
    configured = set(getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).keys()) | database_providers
    return {
        "google_login_available": "google" in configured and (policy.google_login_enabled if policy else True),
        "microsoft_login_available": "microsoft" in configured and (policy.microsoft_login_enabled if policy else True),
    }
