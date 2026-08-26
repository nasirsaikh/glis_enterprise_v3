from django.db.models import Q
from django.utils import timezone
from apps.accounts.models import UserProfile
from apps.tickets.models import Ticket


class TicketAccessPolicy:
    @staticmethod
    def visible_queryset(user):
        qs = Ticket.objects.select_related("requester", "assignee", "project", "product", "category", "sla_policy").prefetch_related("groups", "assignees")
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser or user.has_perm("tickets.view_all"):
            return qs
        profile = getattr(user, "profile", None)
        if profile and profile.role == UserProfile.Role.GUEST:
            return qs.filter(requester=user)
        group_ids = user.support_groups.values_list("pk", flat=True)
        project_ids = user.ticket_projects.values_list("pk", flat=True)
        return qs.filter(
            Q(requester=user) | Q(assignee=user) | Q(assignees=user) | Q(groups__in=group_ids) |
            Q(project_id__in=project_ids) | Q(approvals__approver=user) |
            Q(shares__recipient=user, shares__is_active=True, shares__expires_at__gt=timezone.now())
        ).distinct()

    @staticmethod
    def can_edit(user, ticket):
        if user.is_superuser or user.has_perm("tickets.change_ticket"):
            return True
        if ticket.assignee_id == user.id or ticket.assignees.filter(pk=user.pk).exists():
            return True
        return ticket.requester_id == user.id and ticket.status == Ticket.Status.NEW

    @staticmethod
    def can_take_over(user, ticket):
        if not user.is_authenticated or TicketAccessPolicy.can_edit(user, ticket):
            return False
        return ticket.groups.filter(members=user, can_edit_group_tickets=True).exists()

    @staticmethod
    def can_assign(user, ticket):
        return (
            user.is_superuser or user.has_perm("tickets.assign") or
            ticket.groups.filter(managers=user).exists() or
            ticket.groups.filter(members=user, can_assign_group_tickets=True).exists()
        )

    @staticmethod
    def can_share(user, ticket):
        return TicketAccessPolicy.can_edit(user, ticket) or TicketAccessPolicy.can_assign(user, ticket)

    @staticmethod
    def can_view_sensitive(user, ticket):
        return user.is_superuser or user.has_perm("tickets.view_sensitive") or ticket.groups.filter(members=user, can_view_sensitive=True).exists()

    @staticmethod
    def can_view_internal_notes(user, ticket):
        return user.is_superuser or user.has_perm("tickets.view_internal_notes") or ticket.groups.filter(members=user, can_view_internal_notes=True).exists()

    @staticmethod
    def can_download_attachment(user, attachment):
        if not TicketAccessPolicy.visible_queryset(user).filter(pk=attachment.ticket_id).exists():
            return False
        if not attachment.is_restricted:
            return True
        return user.is_superuser or attachment.ticket.groups.filter(members=user, can_view_restricted_attachments=True).exists()
