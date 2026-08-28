from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from apps.tickets.models import Notification, TicketApproval, TicketEvent
from apps.job_center.queue import enqueue


# def notify_users(users, *, ticket=None, kind="info", title, body="", send_email_message=False):
#     unique = {user.pk: user for user in users if user and user.is_active}
#     link = reverse("portal:ticket_detail", args=[ticket.reference]) if ticket else ""
#     notifications = [Notification(user=user, ticket=ticket, kind=kind, title=title, body=body[:500], link=link) for user in unique.values()]
#     if notifications:
#         Notification.objects.bulk_create(notifications)
#     if send_email_message:
#         for user in unique.values():
#             profile = getattr(user, "profile", None)
#             if user.email and (profile is None or profile.email_notifications):
#                 send_mail(title, body, getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@glis.local"), [user.email], fail_silently=True)


def notify_users(users, *, ticket=None, kind="info", title, body="", send_email_message=False):
    unique = {user.pk: user for user in users if user and user.is_active}
    link = reverse("portal:ticket_detail", args=[ticket.reference]) if ticket else ""
    notifications = [Notification(user=user, ticket=ticket, kind=kind, title=title, body=body[:500], link=link) for user in unique.values()]
    if notifications: Notification.objects.bulk_create(notifications)
    if not send_email_message: return
    recipient_ids = [user.pk for user in unique.values() if user.email and (getattr(user, "profile", None) is None or user.profile.email_notifications)]
    if not recipient_ids: return
    payload = {"recipient_ids": recipient_ids, "ticket_id": ticket.pk if ticket else None, "title": title, "body": body, "kind": kind, "link": link}
    transaction.on_commit(lambda: enqueue("email.ticket_notification", payload, priority=3, max_attempts=3, retry_delay_seconds=60))

@transaction.atomic
def initialize_approval_workflow(ticket):
    workflow = ticket.category.approval_workflow
    if not workflow or not workflow.is_active:
        ticket.approval_state = "not_required"
        ticket.save(update_fields=["approval_state", "updated_at"])
        return []
    created = []
    for step in workflow.steps.prefetch_related("approver_users", "approver_groups__members"):
        approvers = {user.pk: user for user in step.approver_users.filter(is_active=True)}
        for group in step.approver_groups.all():
            approvers.update({user.pk: user for user in group.members.filter(is_active=True)})
        for approver in approvers.values():
            approval, _ = TicketApproval.objects.get_or_create(ticket=ticket, step=step, approver=approver)
            created.append(approval)
    ticket.approval_state = "pending" if created else "not_required"
    ticket.save(update_fields=["approval_state", "updated_at"])
    first_sequence = min((item.step.sequence for item in created), default=None)
    first_users = [item.approver for item in created if item.step.sequence == first_sequence]
    notify_users(first_users, ticket=ticket, kind="approval", title=f"Approval required: {ticket.reference}", body=ticket.subject, send_email_message=ticket.category.send_initial_email)
    return created


def current_approval_sequence(ticket):
    pending = ticket.approvals.filter(status="pending").select_related("step").order_by("step__sequence")
    return pending.first().step.sequence if pending.exists() else None


@transaction.atomic
def decide_approval(approval, *, approved, note, actor):
    ticket = approval.ticket
    if approval.approver_id != actor.pk:
        raise PermissionError("This approval is assigned to another user.")
    current = current_approval_sequence(ticket)
    if current is None or approval.step.sequence != current or approval.status != "pending":
        raise ValueError("This approval step is not currently actionable.")
    approval.status = "approved" if approved else "rejected"
    approval.note, approval.decided_at = note, timezone.now()
    approval.save(update_fields=["status", "note", "decided_at", "updated_at"])
    TicketEvent.objects.create(ticket=ticket, actor=actor, event_type="approval", summary=f"{approval.step.name}: {approval.get_status_display()}")
    if not approved and approval.step.rejection_ends_workflow:
        ticket.approval_state = "rejected"
        ticket.save(update_fields=["approval_state", "updated_at"])
        notify_users([ticket.requester], ticket=ticket, kind="approval", title=f"Approval rejected: {ticket.reference}", body=note)
        return
    step_items = ticket.approvals.filter(step=approval.step)
    approved_count = step_items.filter(status="approved").count()
    if approved_count >= approval.step.approvals_required:
        step_items.filter(status="pending").update(status="skipped")
        next_item = ticket.approvals.filter(status="pending", step__sequence__gt=current).select_related("step").order_by("step__sequence").first()
        if next_item:
            next_users = [item.approver for item in ticket.approvals.filter(status="pending", step__sequence=next_item.step.sequence).select_related("approver")]
            notify_users(next_users, ticket=ticket, kind="approval", title=f"Approval required: {ticket.reference}", body=next_item.step.name)
        else:
            ticket.approval_state = "approved"
            ticket.save(update_fields=["approval_state", "updated_at"])
            notify_users([ticket.requester], ticket=ticket, kind="approval", title=f"Approval completed: {ticket.reference}", body=ticket.subject)
