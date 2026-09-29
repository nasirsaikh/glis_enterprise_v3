from django.db.models import Q
from django.utils import timezone

from ..models import MemberTransaction, Policy, TPAEmailAuthority


def resolve_email_authority(email_address, policy, transaction_type, *, as_of=None):
    """
    Resolve deterministic sender authority for an inbound endorsement.
    AI output is never used to grant authority.
    """
    address = str(email_address or "").strip().lower()
    if not address or not policy:
        return None

    day = as_of or timezone.localdate()
    qs = (
        TPAEmailAuthority.objects.select_related("user", "organization", "policy")
        .filter(
            email_address__iexact=address,
            active=True,
        )
        .filter(Q(policy=policy) | Q(policy__isnull=True, organization=policy.sponsor))
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=day))
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=day))
        .order_by("-policy_id", "pk")
    )

    for authority in qs:
        permitted = {
            str(value).strip().upper()
            for value in (authority.permitted_transaction_types or [])
            if str(value).strip()
        }
        if not permitted or str(transaction_type or "").upper() in permitted:
            return authority
    return None


def sender_is_authorized(email, policy, transaction_type, *, actor=None):
    authority = resolve_email_authority(
        email.sender,
        policy,
        transaction_type,
        as_of=email.received_at.date() if email.received_at else None,
    )
    if authority:
        return True, authority, ""

    # Manual/test intake is an explicit recovery path. It can proceed when the
    # operator already has server-side authority for the policy.
    if email.provider in {"manual", "test"} and actor and actor.is_authenticated:
        if actor.is_superuser or actor.has_perm("tpa.configure_tpa"):
            return True, None, "Manual/recovery intake authorized by privileged operator."
        if policy.access_entries.filter(
            user=actor,
            active=True,
            can_create_endorsement=True,
        ).exists():
            return True, None, "Manual/recovery intake authorized by policy access."

    return (
        False,
        None,
        "Sender is not authorized for this policy and endorsement type.",
    )


def authority_user(authority, fallback=None):
    if authority and authority.user_id:
        return authority.user
    return fallback
