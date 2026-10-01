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
    organization_ids = {
        policy.organization_id,
        policy.insurance_company_id,

    }
    organization_ids.update(policy.workflow_organizations.filter(is_active=True).values_list("pk", flat=True))
    organization_ids.discard(None)

    qs = (
        TPAEmailAuthority.objects.select_related("user", "organization", "policy")
        .filter(
            email_address__iexact=address,
            active=True,
        )
        .filter(
            Q(policy=policy)
            | Q(
                policy__isnull=True,
                organization_id__in=organization_ids,
            )
        )
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
    if authority and authority.organization.is_active and authority.organization.organization_type.is_active and (not authority.user_id or authority.user.is_active):
        return True, authority, ""

    # Manual/test intake is an explicit recovery path. It can proceed when the
    # operator already has server-side authority for the policy.
    if email.provider in {"manual", "test"} and actor and actor.is_authenticated:
        if actor.is_superuser or actor.has_perm("tpa.configure_tpa"):
            return True, None, "Manual/recovery intake authorized by privileged operator."
        from .access import visible_policies
        if not visible_policies(actor).filter(pk=policy.pk).exists():
            return False, None, "The policy is outside your organization scope."
        if transaction_type == "CLAIM" and not actor.has_perm("tickets.add_ticket"):
            return False, None, "Claim creation permission is required."
        if policy.access_entries.filter(
            user=actor,
            active=True,
            **{"can_create_enrollment" if transaction_type == MemberTransaction.Type.NEW_POLICY_ENROLLMENT else "can_view" if transaction_type == "CLAIM" else "can_create_endorsement": True},
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
