from django.db import OperationalError, ProgrammingError

from .models import SiteSettings
from apps.accounts.models import UserProfile


def glis_site_context(request):
    """Expose CMS-controlled branding to the public and portal shells."""
    theme_choices = UserProfile.Theme.choices
    try:
        return {"glis_site": SiteSettings.load(), "daisyui_theme_choices": theme_choices}
    except (OperationalError, ProgrammingError):
        return {"glis_site": None, "daisyui_theme_choices": theme_choices}