from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from apps.tickets.models import Notification, Ticket, TicketApproval, TicketEvent
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
    # Ticket activity is mailed once through its durable audit event. Existing
    # callers retain their in-app notifications without a second email.
    if ticket and ticket.events.exists(): return
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
    if created:
        TicketEvent.objects.create(ticket=ticket, actor=ticket.requester, event_type="approval_started", summary=f"Approval workflow started: {workflow.name}", details={"workflow": workflow.pk, "approvals": [item.pk for item in created]})
    first_sequence = min((item.step.sequence for item in created), default=None)
    first_users = [item.approver for item in created if item.step.sequence == first_sequence]
    notify_users(first_users, ticket=ticket, kind="approval", title=f"Approval required: {ticket.reference}", body=ticket.subject, send_email_message=ticket.category.send_initial_email)
    return created


def current_approval_sequence(ticket):
    pending = ticket.approvals.filter(status__in=["pending", "rejected", "needs_info"], step__isnull=False).select_related("step").order_by("step__sequence")
    return pending.first().step.sequence if pending.exists() else None


@transaction.atomic
def decide_approval(approval, *, approved=None, decision=None, note, actor):
    ticket = Ticket.objects.select_for_update().get(pk=approval.ticket_id)
    approval = TicketApproval.objects.select_for_update().select_related('step').get(pk=approval.pk)
    from services.access import TicketAccessPolicy
    if not TicketAccessPolicy.can_view(actor, ticket):
        raise PermissionError('You cannot access this ticket.')
    if approval.approver_id != actor.pk:
        raise PermissionError("This approval is assigned to another user.")
    decision = decision or ("approve" if approved else "reject")
    if decision not in {"approve", "reject", "needs_info"}:
        raise ValueError("Select a valid approval decision.")
    if ticket.status == Ticket.Status.CLOSED:
        raise ValueError("Reopen this ticket before acting on its approval.")
    if ticket.approval_state != "pending":
        raise ValueError("The creator must resubmit the outstanding query or rejection first.")
    if decision == "needs_info" and not note.strip():
        raise ValueError("Explain the additional information required.")
    status = {"approve": "approved", "reject": "rejected", "needs_info": "needs_info"}[decision]
    if approval.step_id is None:
        if approval.status != 'pending':
            raise ValueError('This approval has already been decided.')
        approval.status = status
        approval.note, approval.decided_at = note, timezone.now()
        approval.save(update_fields=['status','note','decided_at','updated_at'])
        statuses = set(ticket.approvals.values_list('status',flat=True))
        ticket.approval_state = 'rejected' if 'rejected' in statuses else 'needs_info' if 'needs_info' in statuses else 'pending' if 'pending' in statuses else 'approved'
        ticket.save(update_fields=['approval_state','updated_at'])
        TicketEvent.objects.create(ticket=ticket,actor=actor,event_type='approval_decided',summary=f'Approval {approval.status}',details={'approval':approval.pk,'before':'pending','after':approval.status,'note':note})
        recipients = [approval.requested_by, *requester_team_users(ticket)] if decision != 'approve' else [approval.requested_by, ticket.requester]
        notify_users(recipients,ticket=ticket,kind='approval',title=f'Approval {approval.get_status_display()}: {ticket.reference}',body=note,send_email_message=ticket.category.send_update_email)
        sync_domain_approval(ticket,actor)
        return approval
    current = current_approval_sequence(ticket)
    if current is None or approval.step.sequence != current or approval.status != "pending":
        raise ValueError("This approval step is not currently actionable.")
    approval.status = status
    approval.note, approval.decided_at = note, timezone.now()
    approval.save(update_fields=["status", "note", "decided_at", "updated_at"])
    TicketEvent.objects.create(ticket=ticket, actor=actor, event_type="approval", summary=f"{approval.step.name}: {approval.get_status_display()}", details={"approval": approval.pk, "step": approval.step.sequence, "before": "pending", "after": status, "note": note})
    if decision != "approve":
        ticket.approval_state = status
        ticket.save(update_fields=["approval_state", "updated_at"])
        notify_users(requester_team_users(ticket), ticket=ticket, kind="approval", title=f"Approval {approval.get_status_display()}: {ticket.reference}", body=note, send_email_message=ticket.category.send_update_email)
        sync_domain_approval(ticket,actor)
        return approval
    step_items = ticket.approvals.filter(step=approval.step)
    approved_count = step_items.filter(status="approved").count()
    if approved_count >= approval.step.approvals_required:
        step_items.filter(status="pending").update(status="skipped")
        next_item = ticket.approvals.filter(status="pending", step__sequence__gt=current).select_related("step").order_by("step__sequence").first()
        if next_item:
            next_users = [item.approver for item in ticket.approvals.filter(status="pending", step__sequence=next_item.step.sequence).select_related("approver")]
            notify_users(next_users, ticket=ticket, kind="approval", title=f"Approval required: {ticket.reference}", body=next_item.step.name)
        else:
            ticket.approval_state = "pending" if ticket.approvals.filter(status="pending").exists() else "approved"
            ticket.save(update_fields=["approval_state", "updated_at"])
            notify_users([ticket.requester], ticket=ticket, kind="approval", title=f"Approval completed: {ticket.reference}", body=ticket.subject)

    sync_domain_approval(ticket,actor)
    return approval


def sync_domain_approval(ticket, actor):
    from apps.tpa.models import MemberTransaction
    from apps.tpa.services.workflow import sync_from_ticket_approval
    tx = MemberTransaction.objects.filter(ticket=ticket,status=MemberTransaction.Status.PENDING_APPROVAL).first()
    if tx:
        sync_from_ticket_approval(tx,actor=actor)


def requester_team_users(ticket):
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from apps.tickets.models import SupportGroup
    from services.access import TicketAccessPolicy
    groups = SupportGroup.objects.filter(Q(members=ticket.requester) | Q(managers=ticket.requester), is_active=True)
    users = get_user_model().objects.filter(Q(pk=ticket.requester_id) | Q(support_groups__in=groups) | Q(managed_support_groups__in=groups), is_active=True).distinct()
    return [user for user in users if TicketAccessPolicy.can_view(user, ticket)]


@transaction.atomic
def resubmit_approval(ticket, *, actor, note):
    from services.access import TicketAccessPolicy
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if not TicketAccessPolicy.can_resubmit_approval(actor, ticket):
        raise PermissionError("Only the creator and their team can resubmit an open approval query or rejection.")
    if not note.strip():
        raise ValueError("Describe how the query or rejection has been addressed.")
    blocked = list(ticket.approvals.select_for_update().filter(status__in=["rejected", "needs_info"]).select_related("step", "approver"))
    if not blocked:
        raise ValueError("There is no outstanding approval query or rejection.")
    for approval in blocked:
        TicketEvent.objects.create(ticket=ticket, actor=actor, event_type="approval_resubmitted", summary=f"Approval resubmitted to {approval.approver.get_full_name() or approval.approver.username}",
            details={"approval": approval.pk, "step": approval.step.sequence if approval.step_id else None, "before": approval.status, "after": "pending", "previous_note": approval.note, "note": note})
        approval.status, approval.note, approval.decided_at = "pending", "", None
        approval.save(update_fields=["status", "note", "decided_at", "updated_at"])
    ticket.approval_state = "pending"
    ticket.save(update_fields=["approval_state", "updated_at"])
    # A linked endorsement rejected by the ticket approver resumes approval.
    from apps.tpa.models import MemberTransaction
    tx = MemberTransaction.objects.filter(ticket=ticket, status=MemberTransaction.Status.REJECTED, rejection_reason="Linked GLIS ticket approval was rejected.").first()
    if tx:
        tx.status, tx.rejection_reason = MemberTransaction.Status.PENDING_APPROVAL, ""
        tx.save(update_fields=["status", "rejection_reason", "updated_at"])
    notify_users([approval.approver for approval in blocked], ticket=ticket, kind="approval", title=f"Approval resubmitted: {ticket.reference}", body=note, send_email_message=ticket.category.send_update_email)
    return ticket


@transaction.atomic
def record_business_approval(ticket, *, actor, approved, note=''):
    from apps.tpa.models import MemberTransaction
    from apps.tpa.services.access import can_approve_tpa_transaction
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    tx = MemberTransaction.objects.get(ticket=ticket)
    if not can_approve_tpa_transaction(actor,tx):
        raise PermissionError('Business approval permission is required.')
    if approved and ticket.approvals.filter(status='pending').exists():
        raise ValueError('Complete the pending ticket approval first.')
    if not approved:
        ticket.approvals.filter(status='pending').update(status='cancelled',decided_at=timezone.now())
    approval = TicketApproval.objects.create(ticket=ticket,step=None,approver=actor,requested_by=ticket.requester,
        status='approved' if approved else 'rejected',note=note,decided_at=timezone.now())
    ticket.approval_state = approval.status
    ticket.save(update_fields=['approval_state','updated_at'])
    TicketEvent.objects.create(ticket=ticket,actor=actor,event_type='approval_decided',summary=f'Business approval {approval.status}',details={'approval':approval.pk,'after':approval.status,'note':note})
    notify_users([ticket.requester],ticket=ticket,kind='approval',title=f'Approval {approval.status}: {ticket.reference}',body=note,send_email_message=ticket.category.send_update_email)
    return approval
