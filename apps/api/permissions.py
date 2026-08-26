from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS


def visible_tickets_for_user(queryset, user):
    """
    Central REST API ticket visibility rule.

    Superusers:
        All tickets.

    Normal users:
        - tickets submitted by user
        - directly assigned tickets
        - tickets where user is one of assignees
        - tickets belonging to user's support groups
        - tickets belonging to projects where user is member
        - tickets belonging to projects associated with user's Django groups
    """

    if not user or not user.is_authenticated:
        return queryset.none()

    if user.is_superuser:
        return queryset

    filters = (
        Q(requester=user)
        | Q(assignee=user)
        | Q(assignees=user)
        | Q(groups__members=user)
        | Q(project__members=user)
        | Q(project__groups__in=user.groups.all())
    )

    return queryset.filter(filters).distinct()


class IsAuthenticatedAndActive(BasePermission):

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.is_active
        )


class IsAdminOrReadOnly(BasePermission):

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated

        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.is_staff
                or request.user.is_superuser
            )
        )


class TicketObjectPermission(BasePermission):

    def has_object_permission(self, request, view, obj):

        user = request.user

        if user.is_superuser:
            return True

        queryset = visible_tickets_for_user(
            obj.__class__.objects.filter(pk=obj.pk),
            user,
        )

        if not queryset.exists():
            return False

        # Reading is allowed if ticket is visible.
        if request.method in SAFE_METHODS:
            return True

        # requester may update own ticket
        if getattr(obj, "requester_id", None) == user.id:
            return True

        # directly assigned
        if getattr(obj, "assignee_id", None) == user.id:
            return True

        # staff
        if user.is_staff:
            return True

        # support-group edit permissions
        groups = getattr(obj, "groups", None)

        if groups is not None:
            return groups.filter(
                members=user,
                can_edit_group_tickets=True,
            ).exists()

        return False