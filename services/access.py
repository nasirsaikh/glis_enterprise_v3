from django.db.models import Q
from django.utils import timezone
from apps.accounts.models import UserProfile
from apps.tickets.models import Ticket
from services.tenancy import scope_tickets


class TicketAccessPolicy:
    @staticmethod
    def visible_queryset(user):
        qs = Ticket.objects.select_related("requester", "assignee", "project", "product", "category", "sla_policy").prefetch_related("groups", "assignees")
        if not user.is_authenticated:
            return qs.none()
        return scope_tickets(qs, user)

    @staticmethod
    def can_view(user, ticket):
        return bool(user and user.is_authenticated and TicketAccessPolicy.visible_queryset(user).filter(pk=ticket.pk).exists())

    @staticmethod
    def can_edit(user, ticket):
        if not TicketAccessPolicy.can_view(user, ticket):
            return False
        if user.is_superuser or user.has_perm("tickets.change_ticket"):
            return True
        if ticket.assignee_id == user.id or ticket.assignees.filter(pk=user.pk).exists():
            return True
        if ticket.groups.filter(members=user, is_active=True, can_edit_group_tickets=True).exists():
            return True
        return ticket.requester_id == user.id and ticket.status == Ticket.Status.NEW

    @staticmethod
    def can_take_over(user, ticket):
        if not TicketAccessPolicy.can_view(user, ticket) or ticket.status in {Ticket.Status.CLOSED, Ticket.Status.RESOLVED}:
            return False
        return not ticket.assignee_id and not ticket.assignees.exists() and ticket.groups.filter(members=user, is_active=True, can_edit_group_tickets=True).exists()

    @staticmethod
    def can_release(user, ticket):
        return TicketAccessPolicy.can_view(user, ticket) and (ticket.assignee_id == user.pk or ticket.assignees.filter(pk=user.pk).exists())

    @staticmethod
    def can_assign(user, ticket):
        if not TicketAccessPolicy.can_view(user, ticket):
            return False
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
        if not TicketAccessPolicy.can_view(user, ticket):
            return False
        return user.is_superuser or user.has_perm("tickets.view_sensitive") or ticket.groups.filter(members=user, can_view_sensitive=True).exists()

    @staticmethod
    def can_view_internal_notes(user, ticket):
        if not TicketAccessPolicy.can_view(user, ticket):
            return False
        return user.is_superuser or user.has_perm("tickets.view_internal_notes") or ticket.groups.filter(members=user, can_view_internal_notes=True).exists()

    @staticmethod
    def can_download_attachment(user, attachment):
        if not TicketAccessPolicy.visible_queryset(user).filter(pk=attachment.ticket_id).exists():
            return False
        if not attachment.is_restricted:
            return True
        return user.is_superuser or attachment.ticket.groups.filter(members=user, can_view_restricted_attachments=True).exists()
