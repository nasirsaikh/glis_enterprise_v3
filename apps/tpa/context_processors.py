from django.db import OperationalError, ProgrammingError

from .services.access import can_access_tpa


def tpa_access_context(request):
    """Expose TPA workspace visibility without leaking TPA data into templates."""
    try:
        allowed = can_access_tpa(request.user)
    except (OperationalError, ProgrammingError):
        allowed = False
    return {"can_access_tpa": allowed}
