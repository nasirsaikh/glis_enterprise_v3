from django.db import OperationalError, ProgrammingError

from .models import SiteSettings


def glis_site_context(request):
    """Expose CMS-controlled branding to the public and portal shells."""
    profile = getattr(request.user, "profile", None) if getattr(request.user, "is_authenticated", False) else None
    theme_choices = profile._meta.get_field("theme").choices if profile is not None else ()
    try:
        return {"glis_site": SiteSettings.load(), "daisyui_theme_choices": theme_choices}
    except (OperationalError, ProgrammingError):
        return {"glis_site": None, "daisyui_theme_choices": theme_choices}