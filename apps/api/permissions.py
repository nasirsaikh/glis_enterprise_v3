from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS


def visible_tickets_for_user(queryset, user):
    """Apply the same organization and ticket permissions as the portal."""

    if not user or not user.is_authenticated:
        return queryset.none()

    if user.is_superuser:
        return queryset

    from services.access import TicketAccessPolicy
    return queryset.filter(pk__in=TicketAccessPolicy.visible_queryset(user).values("pk"))



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