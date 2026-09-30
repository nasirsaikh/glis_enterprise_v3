from django.db import OperationalError, ProgrammingError

from .services.access import (
    can_access_tpa,
    can_create_endorsement,
    can_create_policy_enrollment,
    can_create_tpa_transaction,
)


def tpa_access_context(request):
    """Expose TPA navigation/action visibility without exposing TPA records."""
    try:
        allowed = can_access_tpa(request.user)
        can_create = can_create_tpa_transaction(request.user) if allowed else False
        can_enroll = can_create_policy_enrollment(request.user) if allowed else False
        can_endorse = can_create_endorsement(request.user) if allowed else False
    except (OperationalError, ProgrammingError):
        allowed = False
        can_create = False
        can_enroll = False
        can_endorse = False
    return {
        "can_configure_tpa_ai": request.user.is_authenticated and (
            request.user.is_superuser or request.user.has_perm("tpa.configure_tpa") or request.user.has_perm("ai.configure_ai")
        ),
        "can_access_tpa": allowed,
        "can_create_tpa_transaction": can_create,
        "can_create_policy_enrollment": can_enroll,
        "can_create_endorsement": can_endorse,
    }
