"""Collaboration and ownership operations on the existing Ticket engine."""
from django.db import transaction
from django.utils import timezone
from apps.tickets.models import Ticket, TicketApproval, TicketEvent, TicketTaggedUser
from services.access import TicketAccessPolicy
from services.tenancy import available_approvers, taggable_users
from services.ticket_workflow import notify_users

def event(ticket,actor,kind,summary,before=None,after=None):
    TicketEvent.objects.create(ticket=ticket,actor=actor,event_type=kind,summary=summary,details={'before':before or {},'after':after or {}})

@transaction.atomic
def release_ticket(ticket,actor):
    ticket=Ticket.objects.select_for_update().get(pk=ticket.pk)
    if not TicketAccessPolicy.can_release(actor,ticket):raise PermissionError('Only a current assignee can release their assignment.')
    before={'primary':ticket.assignee_id,'users':list(ticket.assignees.values_list('pk',flat=True))}
    ticket.assignees.remove(actor)
    if ticket.assignee_id==actor.pk:
        ticket.assignee=ticket.assignees.order_by('pk').first();ticket.save(update_fields=['assignee','updated_at'])
    event(ticket,actor,'assignment_released','Assignment released',before,{'primary':ticket.assignee_id,'users':list(ticket.assignees.values_list('pk',flat=True))})
    users={u.pk:u for g in ticket.groups.filter(is_active=True) for u in g.members.filter(is_active=True)}
    notify_users(users.values(),ticket=ticket,kind='assignment',title=f'Ticket available: {ticket.reference}',send_email_message=ticket.category.send_update_email)
    return ticket

@transaction.atomic
def take_over_ticket(ticket,actor):
    ticket=Ticket.objects.select_for_update().get(pk=ticket.pk)
    if ticket.assignee_id or ticket.assignees.exists():raise ValueError('This ticket has already been assigned. Refresh the page.')
    if not TicketAccessPolicy.can_take_over(actor,ticket):raise PermissionError('You cannot take over this ticket.')
    values={'assignee_id':actor.pk,'updated_at':timezone.now()}
    if ticket.status in {Ticket.Status.NEW,Ticket.Status.OPEN}:values['status']=Ticket.Status.IN_PROGRESS
    if Ticket.objects.filter(pk=ticket.pk,assignee__isnull=True).update(**values)!=1:raise ValueError('Another user has taken over this ticket.')
    ticket.assignees.add(actor);ticket.refresh_from_db()
    event(ticket,actor,'takeover','Ticket taken over',{}, {'assignee':actor.pk,'taken_over_at':timezone.now().isoformat()})
    notify_users([ticket.requester,actor],ticket=ticket,kind='assignment',title=f'Ticket taken over: {ticket.reference}',send_email_message=ticket.category.send_update_email)
    return ticket

@transaction.atomic
def tag_user(ticket,actor,user,*,active=True):
    ticket=Ticket.objects.select_for_update().get(pk=ticket.pk)
    if not TicketAccessPolicy.can_share(actor,ticket):raise PermissionError('Participant management permission is required.')
    if active and not taggable_users(actor,ticket).filter(pk=user.pk).exists():raise PermissionError('Select an authorized user.')
    if active:
        tag,created=TicketTaggedUser.objects.get_or_create(ticket=ticket,user=user,defaults={'tagged_by':actor})
        if not created and tag.is_active:return tag
        tag.is_active,tag.tagged_by=True,actor;tag.save(update_fields=['is_active','tagged_by','updated_at'])
        notify_users([user],ticket=ticket,title=f'You were tagged: {ticket.reference}',send_email_message=ticket.category.send_update_email)
    else:
        tag=TicketTaggedUser.objects.filter(ticket=ticket,user=user,is_active=True).first()
        if not tag:raise ValueError('This user is not an active tagged participant.')
        tag.is_active=False;tag.save(update_fields=['is_active','updated_at'])
    event(ticket,actor,'user_tagged' if active else 'user_untagged','Ticket participants updated',{'active':not active},{'user':user.pk,'active':active})
    return tag

@transaction.atomic
def request_approval(ticket,actor,approver,note=''):
    ticket=Ticket.objects.select_for_update().get(pk=ticket.pk)
    if not TicketAccessPolicy.can_share(actor,ticket):raise PermissionError('Approval request permission is required.')
    if ticket.status in {Ticket.Status.CLOSED,Ticket.Status.RESOLVED}:raise ValueError('A completed request cannot request approval.')
    if not available_approvers(actor,ticket).filter(pk=approver.pk).exists():raise PermissionError('Select an authorized approver.')
    approval,created=TicketApproval.objects.get_or_create(ticket=ticket,step=None,approver=approver,status='pending',defaults={'requested_by':actor,'note':note})
    if created:
        ticket.approval_state='pending';ticket.save(update_fields=['approval_state','updated_at'])
        event(ticket,actor,'approval_requested','Approval requested',{}, {'approval':approval.pk,'approver':approver.pk,'note':note})
        notify_users([approver],ticket=ticket,kind='approval',title=f'Approval required: {ticket.reference}',body=note,send_email_message=ticket.category.send_update_email)
    return approval

@transaction.atomic
def cancel_approval(approval,actor):
    ticket=Ticket.objects.select_for_update().get(pk=approval.ticket_id)
    approval=TicketApproval.objects.select_for_update().get(pk=approval.pk)
    if approval.step_id or approval.status!='pending':raise ValueError('Only a pending individual request can be cancelled.')
    if not TicketAccessPolicy.can_view(actor,ticket) or (approval.requested_by_id!=actor.pk and not actor.is_superuser):raise PermissionError('Only the requester can cancel this approval.')
    approval.status,approval.decided_at='cancelled',timezone.now();approval.save(update_fields=['status','decided_at','updated_at'])
    statuses=set(ticket.approvals.values_list('status',flat=True))
    ticket.approval_state='rejected' if 'rejected' in statuses else 'pending' if 'pending' in statuses else 'approved' if 'approved' in statuses else 'not_required'
    ticket.save(update_fields=['approval_state','updated_at'])
    event(ticket,actor,'approval_cancelled','Approval cancelled',{'status':'pending'},{'approval':approval.pk,'status':'cancelled'})
    notify_users([approval.approver],ticket=ticket,kind='approval',title=f'Approval cancelled: {ticket.reference}')
