from django.db.models import Q

from ..models import MemberTransaction, Policy, PolicyAccess


TPA_ENTRY_PERMISSIONS = (
    "tpa.view_tpa_dashboard",
    "tpa.configure_tpa",
    "tpa.create_enrollment",
    "tpa.create_endorsement",
    "tpa.approve_endorsement",
    "tpa.process_endorsement",
)


def can_access_tpa(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or any(user.has_perm(code) for code in TPA_ENTRY_PERMISSIONS):
        return True
    if PolicyAccess.objects.filter(user=user, active=True, can_view=True).exists():
        return True
    return MemberTransaction.objects.filter(requester=user).exists()


def can_create_policy_enrollment(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("tpa.configure_tpa"):
        return True
    if user.has_perm("tpa.create_enrollment"):
        return True
    return PolicyAccess.objects.filter(
        user=user,
        active=True,
        can_create_enrollment=True,
    ).exists()


def can_create_endorsement(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("tpa.configure_tpa"):
        return True
    if user.has_perm("tpa.create_endorsement"):
        return True
    return PolicyAccess.objects.filter(
        user=user,
        active=True,
        can_create_endorsement=True,
    ).exists()


def can_create_tpa_transaction(user):
    return can_create_policy_enrollment(user) or can_create_endorsement(user)


def can_approve_tpa_transaction(user, tx):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("tpa.configure_tpa") or user.has_perm("tpa.approve_endorsement"):
        return True
    return PolicyAccess.objects.filter(
        user=user, policy=tx.policy, active=True, can_approve=True
    ).exists()


def can_process_tpa_transaction(user, tx):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("tpa.configure_tpa") or user.has_perm("tpa.process_endorsement"):
        return True
    return PolicyAccess.objects.filter(
        user=user, policy=tx.policy, active=True, can_process=True
    ).exists()


def visible_policies(user):
    qs = Policy.objects.select_related("sponsor", "insurance_company")
    if not user.is_authenticated:
        return qs.none()
    if user.is_superuser or user.has_perm("tpa.configure_tpa"):
        return qs
    return qs.filter(
        access_entries__user=user,
        access_entries__active=True,
        access_entries__can_view=True,
    ).distinct()


def visible_transactions(user):
    qs = MemberTransaction.objects.select_related(
        "policy", "sponsor", "insurer", "ticket"
    )
    if not user.is_authenticated:
        return qs.none()
    if user.is_superuser or user.has_perm("tpa.configure_tpa"):
        return qs
    return qs.filter(
        Q(requester=user)
        | Q(
            policy__access_entries__user=user,
            policy__access_entries__active=True,
            policy__access_entries__can_view=True,
        )
    ).distinct()
