from django.db import OperationalError, ProgrammingError

from .models import SiteSettings


def glis_site_context(request):
    """Expose CMS-controlled branding to the public and portal shells."""
    try:
        return {"glis_site": SiteSettings.load()}
    except (OperationalError, ProgrammingError):
        return {"glis_site": None}