from django.db import OperationalError, ProgrammingError

from .services.access import can_access_tpa, can_create_tpa_transaction


def tpa_access_context(request):
    """Expose TPA navigation/action visibility without exposing TPA records."""
    try:
        allowed = can_access_tpa(request.user)
        can_create = can_create_tpa_transaction(request.user) if allowed else False
    except (OperationalError, ProgrammingError):
        allowed = False
        can_create = False
    return {
        "can_access_tpa": allowed,
        "can_create_tpa_transaction": can_create,
    }
