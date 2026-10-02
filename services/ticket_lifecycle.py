"""Ticket closure pauses approvals; reopening restores the previous stage."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.tickets.models import Ticket, TicketEvent
from services.access import TicketAccessPolicy
from services.ticket_workflow import notify_users


def reopen_deadline(ticket):
    if ticket.closed_at and ticket.category.reopen_allowed_days > 0:
        return ticket.closed_at + timedelta(days=ticket.category.reopen_allowed_days)
    return None


def within_reopen_period(ticket):
    deadline = reopen_deadline(ticket)
    return ticket.status == Ticket.Status.CLOSED and deadline is not None and timezone.now() <= deadline


def update_status(ticket, status, actor):
    """Called inside a transaction with the ticket row locked."""
    if status == ticket.status:
        return
    if ticket.status == Ticket.Status.CLOSED:
        raise ValueError("Use Reopen ticket within the category's allowed period.")
    if status == Ticket.Status.NEW or status not in Ticket.Status.values:
        raise ValueError("Select a valid update status.")
    if status == Ticket.Status.CLOSED:
        if not TicketAccessPolicy.can_close(actor, ticket):
            raise PermissionError("Only the creator and their team can close a ticket awaiting approval.")
    elif ticket.approval_state in {"pending", "rejected", "needs_info"} or hasattr(ticket, "tpa_transaction"):
        raise PermissionError("Use the approval or business workflow to advance this ticket.")
    elif not TicketAccessPolicy.can_edit(actor, ticket):
        raise PermissionError("Status change permission is required.")
    before = ticket.status
    ticket.status = status
    if status == Ticket.Status.CLOSED:
        ticket.resume_status = before if before != Ticket.Status.RESOLVED else Ticket.Status.OPEN
        ticket.closed_at = timezone.now()
        ticket.resolved_at = ticket.resolved_at or ticket.closed_at
    elif status == Ticket.Status.RESOLVED:
        ticket.resolved_at = timezone.now()
        ticket.closed_at = None
    else:
        ticket.closed_at = ticket.resolved_at = None
    ticket.save(update_fields=["status", "resume_status", "closed_at", "resolved_at", "updated_at"])
    TicketEvent.objects.create(ticket=ticket, actor=actor, event_type="closed" if status == Ticket.Status.CLOSED else "status_changed",
        summary=f"Status changed: {Ticket.Status(before).label} → {Ticket.Status(status).label}",
        details={"before": before, "after": status, "approval_state": ticket.approval_state})


@transaction.atomic
def close_ticket(ticket, actor):
    ticket = Ticket.objects.select_for_update().select_related("category").get(pk=ticket.pk)
    if not TicketAccessPolicy.can_close(actor, ticket):
        raise PermissionError("You cannot close this ticket.")
    update_status(ticket, Ticket.Status.CLOSED, actor)
    notify_users([ticket.requester, *ticket.assignees.all()], ticket=ticket, kind="update",
        title=f"Ticket closed: {ticket.reference}", send_email_message=ticket.category.send_update_email)
    return ticket


@transaction.atomic
def reopen_ticket(ticket, actor):
    ticket = Ticket.objects.select_for_update().select_related("category").get(pk=ticket.pk)
    if not within_reopen_period(ticket):
        raise ValueError("Reopening is disabled or the category's reopen period has expired.")
    if not TicketAccessPolicy.can_reopen(actor, ticket):
        raise PermissionError("You cannot reopen this ticket.")
    ticket.status = ticket.resume_status or (Ticket.Status.PENDING_CUSTOMER if ticket.approval_state == "needs_info" else Ticket.Status.OPEN)
    ticket.closed_at = ticket.resolved_at = None
    ticket.resume_status = ""
    ticket.save(update_fields=["status", "resume_status", "closed_at", "resolved_at", "updated_at"])
    TicketEvent.objects.create(ticket=ticket, actor=actor, event_type="reopened", summary="Ticket reopened at its previous workflow step",
        details={"before": "closed", "after": ticket.status, "approval_state": ticket.approval_state})
    from services.ticket_workflow import current_approval_sequence
    sequence = current_approval_sequence(ticket)
    approvers = ticket.approvals.filter(status="pending").filter(step__isnull=True) | ticket.approvals.filter(status="pending", step__sequence=sequence)
    notify_users([ticket.requester, *ticket.assignees.all(), *(item.approver for item in approvers.select_related("approver"))],
        ticket=ticket, kind="update", title=f"Ticket reopened: {ticket.reference}", send_email_message=ticket.category.send_update_email)
    return ticket
