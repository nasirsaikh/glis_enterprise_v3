"""Category-controlled, recipient-specific ticket activity email context."""
import json

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags

from services.access import TicketAccessPolicy

INITIAL_EVENT_TYPES = {'created', 'task_created', 'domain_linked', 'approval_started',
                       'tpa_transaction_created', 'tpa_policy_enrollment_created'}


def event_visible(event, user):
    if event.details.get('is_internal') and not TicketAccessPolicy.can_view_internal_notes(user, event.ticket):
        return False
    if event.details.get('query_id'):
        from apps.tpa.models import TransactionQuery, TransactionQueryMessage
        from apps.tpa.services.access import can_view_query_message, can_view_transaction_query
        messages = TransactionQueryMessage.objects.select_related('query__transaction')
        message = None
        if event.details.get('message_id'):
            message = messages.filter(pk=event.details['message_id']).first()
        elif event.details.get('ticket_comment_id'):
            message = messages.filter(ticket_comment_id=event.details['ticket_comment_id']).first()
        if message:
            return can_view_query_message(user, message)
        query = TransactionQuery.objects.select_related('transaction').filter(pk=event.details['query_id']).first()
        return bool(query and can_view_transaction_query(user, query))
    return True


def activity_details(event, user):
    safe_keys = {'note', 'previous_note', 'step', 'approval_state', 'status_from', 'status_to', 'changed_fields', 'attachment_count',
                 'status', 'method', 'score', 'stp_eligible', 'stp_blockers', 'effective_date', 'due_date', 'transaction_reference'}
    if TicketAccessPolicy.can_view_sensitive(user, event.ticket):
        safe_keys.update({'before', 'after'})
    else:
        safe_keys.update(key for key in ('before', 'after') if isinstance(event.details.get(key), str))
    details = {key: value for key, value in event.details.items() if key in safe_keys}
    return json.dumps(details, ensure_ascii=False) if details else ''


def account_enabled(user):
    if not user or not user.is_active:
        return False
    profile = getattr(user, 'profile', None)
    for obj in (user, profile):
        if obj and (getattr(obj, 'is_locked', False) or getattr(obj, 'is_disabled', False)):
            return False
    if profile:
        if not profile.is_approved:
            return False
        if profile.guest_access_expires_at and profile.guest_access_expires_at <= timezone.now():
            return False
    return True


def email_enabled(user):
    return account_enabled(user) and bool(user.email) and getattr(getattr(user, 'profile', None), 'email_notifications', True)


def activity_recipients(ticket, internal=False):
    from services.ticket_workflow import requester_team_users
    creator_team = [user.pk for user in requester_team_users(ticket)]
    users = get_user_model().objects.filter(
        Q(pk__in=creator_team) | Q(pk=ticket.assignee_id) | Q(multi_assigned_tickets=ticket)
        | Q(ticket_tags__ticket=ticket, ticket_tags__is_active=True)
        | Q(tagged_tasks__ticket=ticket, tagged_tasks__is_deleted=False)
        | Q(support_groups__tickets=ticket, support_groups__is_active=True)
        | Q(managed_support_groups__tickets=ticket, managed_support_groups__is_active=True)
        | Q(ticket_approvals__ticket=ticket)
        | Q(received_ticket_shares__ticket=ticket, received_ticket_shares__is_active=True, received_ticket_shares__expires_at__gt=timezone.now())
    ).select_related('profile').distinct()
    return [user for user in users if email_enabled(user) and TicketAccessPolicy.can_view(user, ticket)
            and (not internal or TicketAccessPolicy.can_view_internal_notes(user, ticket))]


def history_and_flow(ticket, user, through=None):
    internal = TicketAccessPolicy.can_view_internal_notes(user, ticket)
    history = []
    comments = ticket.comments.select_related('author').order_by('created_at', 'pk')
    events = ticket.events.select_related('actor').exclude(event_type='comment').order_by('created_at', 'pk')
    if through:
        comments = comments.filter(created_at__lte=through.created_at)
        events = events.filter(created_at__lte=through.created_at, pk__lte=through.pk)
    for comment in comments:
        if comment.is_internal and not internal:
            continue
        history.append({'at': comment.created_at, 'actor': comment.author.get_full_name() or comment.author.username,
                        'action': 'Internal note' if comment.is_internal else 'Comment', 'detail': strip_tags(comment.body)})
    for event in events:
        if not event_visible(event, user):
            continue
        history.append({'at': event.created_at, 'actor': (event.actor.get_full_name() or event.actor.username) if event.actor else 'System',
                        'action': event.summary, 'detail': activity_details(event, user)})
    history.sort(key=lambda row: row['at'])
    flow = []
    for approval in ticket.approvals.select_related('step', 'approver').order_by('step__sequence', 'pk'):
        flow.append({'name': approval.step.name if approval.step_id else 'Approval', 'status': approval.get_status_display(),
                     'by': approval.approver.get_full_name() or approval.approver.username})
    tx = getattr(ticket, 'tpa_transaction', None)
    if tx is None:
        from apps.tpa.models import MemberTransaction
        tx = MemberTransaction.objects.filter(ticket=ticket).first()
    if tx:
        from apps.tpa.services.wizard import get_transaction_steps
        flow = [{'name': step['label'], 'status': 'Complete' if step['completed'] else tx.get_status_display() if step['current'] else 'Upcoming',
                 'by': 'Auto approved by System' if step['key'] == 'approval' and tx.approved_at and not tx.approved_by_id else ''}
                for step in get_transaction_steps(tx, user)] + flow
    return {'activity_history': history, 'process_flow': flow}


def enqueue_activity(event_id):
    from apps.tickets.models import TicketEvent
    from apps.job_center.queue import enqueue
    event = TicketEvent.objects.select_related('ticket__category').filter(pk=event_id).first()
    if not event:
        return
    initial = event.event_type in INITIAL_EVENT_TYPES
    category = event.ticket.category
    if category.send_initial_email if initial else category.send_update_email:
        enqueue('email.ticket_activity', {'event_id': event.pk}, priority=3)
