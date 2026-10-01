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
    assigned = list(profile.organizations.filter(is_active=True, organization_type__is_active=True).values_list("pk", flat=True)) if profile else []
    if profile and profile.organizations.exists():
        return assigned
    # PolicyAccess is the legacy explicit organization membership mechanism.
    grants = getattr(user, "tpa_policy_access", None)
    return list(grants.filter(active=True, organization__is_active=True, organization__organization_type__is_active=True).values_list("organization_id", flat=True).distinct()) if grants is not None else []


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
    from django.utils import timezone
    from apps.tpa.models import Policy
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    orgs = organization_ids(user)
    scope = (Q(requester=user) | Q(assignee=user) | Q(assignees=user)
        | Q(tagged_participants__user=user, tagged_participants__is_active=True)
        | Q(approvals__approver=user, approvals__status__in=['pending','approved','rejected'])
        | Q(task_item__tagged_users=user, task_item__is_deleted=False)
        | Q(shares__recipient=user, shares__is_active=True, shares__expires_at__gt=timezone.now())
        | Q(groups__members=user, groups__is_active=True, groups__can_view_all_group_tickets=True)
        | Q(groups__managers=user, groups__is_active=True))
    if user.has_perm('tickets.view_ticket') or user.has_perm('tickets.view_all') or user.has_perm('tpa.configure_tpa'):
        scope |= (Q(organization_id__in=orgs) | Q(organization_participants__organization_id__in=orgs, organization_participants__can_view=True)
                  | Q(organization__isnull=True, requester__profile__organizations__pk__in=orgs))
    scope |= Q(policy_id__in=scope_policies(Policy.objects.all(), user).filter(access_entries__user=user,access_entries__active=True,access_entries__can_view=True).values('pk'))
    return queryset.filter(scope).distinct()


def scope_policies(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    organizations = set(organization_ids(user))
    organizations.update(SupportGroup.objects.filter(pk__in=membership_group_ids(user),can_view_all_group_tickets=True,
        organizations__is_active=True,organizations__organization_type__is_active=True).values_list('organizations__pk',flat=True))
    scope = (
        Q(organization_id__in=organizations)
        | Q(insurance_company_id__in=organizations)
        | Q(workflow_organizations__pk__in=organizations)
    )
    # A PolicyAccess grant is an explicit organization assignment for legacy
    # accounts without profile organizations. It must not override newer
    # profile organization restrictions.
    grants = Q(access_entries__user=user, access_entries__active=True, access_entries__can_view=True, access_entries__organization__is_active=True, access_entries__organization__organization_type__is_active=True)
    if organization_ids(user) or (getattr(user, "profile", None) and user.profile.organizations.exists()):
        grants &= Q(access_entries__organization_id__in=organization_ids(user))
    return queryset.filter(scope | grants).distinct()


def visible_notifications(user):
    from apps.tickets.models import Notification
    from services.access import TicketAccessPolicy

    qs = Notification.objects.filter(user=user)
    return qs.filter(
        Q(ticket__isnull=True)
        | Q(ticket_id__in=TicketAccessPolicy.visible_queryset(user).values("pk"))
    ).distinct()


def visible_organizations(user, ticket=None):
    from apps.accounts.models import Organization
    qs = Organization.objects.filter(is_active=True, organization_type__is_active=True)
    if not user or not user.is_authenticated:
        return qs.none()
    if ticket is None:
        return qs if user.is_superuser else qs.filter(pk__in=organization_ids(user))
    ids = set(ticket.organization_participants.values_list('organization_id',flat=True))
    if ticket.organization_id:
        ids.add(ticket.organization_id)
    if not ids:
        ids.update(organization_ids(user) or organization_ids(ticket.requester))
    return qs.filter(pk__in=ids)


def assignable_groups(user, ticket, organization=None):
    groups = SupportGroup.objects.filter(is_active=True)
    scope = Q(organizations__in=visible_organizations(user,ticket)) | Q(pk__in=ticket.groups.values('pk'))
    if ticket.organization_id is None and not ticket.organization_participants.exists():
        scope |= Q(pk__in=membership_group_ids(user))
    groups = groups.filter(scope)
    if ticket.project.groups.exists():
        groups = groups.filter(Q(projects=ticket.project) | Q(pk__in=ticket.groups.values('pk')))
    if organization:
        groups = groups.filter(organizations=organization)
    return groups.distinct()


def assignable_users(user, ticket, group=None, organization=None):
    qs = get_user_model().objects.filter(is_active=True).select_related('profile')
    orgs, groups = visible_organizations(user,ticket), assignable_groups(user,ticket,organization)
    if organization:
        orgs = orgs.filter(pk=organization.pk)
    if group:
        groups = groups.filter(pk=group.pk)
        qs = qs.filter(Q(support_groups__in=groups) | Q(managed_support_groups__in=groups))
    else:
        qs = qs.filter(Q(profile__organizations__in=orgs) | Q(support_groups__in=groups) | Q(managed_support_groups__in=groups))
    return qs.distinct()


def taggable_users(user,ticket):
    return assignable_users(user,ticket)


def available_approvers(user,ticket):
    return assignable_users(user,ticket).exclude(pk=user.pk)
