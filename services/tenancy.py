"""Shared portal organization boundary, including explicitly joined support teams.

Django permissions grant actions; they do not grant access to another tenant.
Superusers retain the system administrator view.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.tickets.models import SupportGroup


def organization_ids(user):
    if not user or not user.is_authenticated:
        return []
    profile = getattr(user, "profile", None)
    assigned = list(profile.organizations.filter(is_active=True).values_list("pk", flat=True)) if profile else []
    if assigned:
        return assigned
    # PolicyAccess is the legacy explicit organization membership mechanism.
    grants = getattr(user, "tpa_policy_access", None)
    return list(grants.filter(active=True, organization__is_active=True).values_list("organization_id", flat=True).distinct()) if grants is not None else []


def membership_group_ids(user):
    if not user or not user.is_authenticated:
        return []
    return list(SupportGroup.objects.filter(
        Q(members=user) | Q(managers=user), is_active=True,
    ).values_list("pk", flat=True).distinct())


def visible_support_groups(user):
    qs = SupportGroup.objects.filter(is_active=True)
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs
    return qs.filter(
        Q(pk__in=membership_group_ids(user))
        | Q(organizations__pk__in=organization_ids(user))
    ).distinct()


def visible_users(user):
    qs = get_user_model().objects.filter(is_active=True).select_related("profile")
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs
    groups = membership_group_ids(user)
    return qs.filter(
        Q(pk=user.pk)
        | Q(profile__organizations__pk__in=organization_ids(user))
        | Q(support_groups__pk__in=groups)
        | Q(managed_support_groups__pk__in=groups)
    ).distinct()


def scope_tickets(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    return queryset.filter(
        Q(requester=user)
        | Q(requester__profile__organizations__pk__in=organization_ids(user))
        | Q(groups__in=visible_support_groups(user))
    ).distinct()


def scope_policies(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    organizations = organization_ids(user)
    scope = (
        Q(sponsor_id__in=organizations)
        | Q(insurance_company_id__in=organizations)
        | Q(tpa_organization_id__in=organizations)
    )
    # A PolicyAccess grant is an explicit organization assignment for legacy
    # accounts without profile organizations. It must not override newer
    # profile organization restrictions.
    grants = Q(access_entries__user=user, access_entries__active=True)
    if organizations:
        grants &= Q(access_entries__organization_id__in=organizations)
    return queryset.filter(scope | grants).distinct()
