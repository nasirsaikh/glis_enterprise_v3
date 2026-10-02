"""Policy domains plug into the existing Ticket workflow and its configuration."""
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.tickets.models import Project, SLAPolicy, Ticket, TicketDynamicData, TicketEvent, TicketOrganization
from services.ticket_workflow import initialize_approval_workflow, notify_users

@transaction.atomic
def create_business_request(*, workflow_type, policy, requester, organization=None, subject='', description='', payload=None, project_id=None, initialize=True):
    organization = organization or policy.organization
    projects = Project.objects.filter(is_active=True, workflow_type=workflow_type).filter(
        Q(organizations__isnull=True) | Q(organizations=organization) | Q(organizations__in=policy.workflow_organizations.all())
    ).filter(Q(organization_types__isnull=True) | Q(organization_types__code=organization.organization_type_id)).distinct()
    if project_id:
        projects = projects.filter(pk=project_id)
    project = projects.first()
    if project is None:
        raise ValueError(f'Configure an authorized active workflow project for {workflow_type}.')
    code = policy.product.code if policy.product_id else policy.product_type
    product = project.products.filter(code=code, is_active=True).first()
    category = product.categories.filter(code=workflow_type, is_active=True).first() if product else None
    if category is None:
        raise ValueError('Configure an active product and category for this workflow.')
    sla = SLAPolicy.objects.filter(category=category, priority=category.default_priority, is_active=True).first()
    sla = sla or SLAPolicy.objects.filter(project=project, category__isnull=True, priority=category.default_priority, is_active=True).first()
    now = timezone.now()
    ticket = Ticket.objects.create(project=project, product=product, category=category, requester=requester,
        organization=organization, policy=policy, subject=(subject or f'{project.name_en} · {policy.policy_number}')[:240],
        description=description, is_sensitive=True, priority=category.default_priority, sla_policy=sla,
        first_response_due_at=now + timedelta(minutes=sla.first_response_minutes) if sla else None,
        resolution_due_at=now + timedelta(minutes=sla.resolution_minutes) if sla else None)
    ticket.groups.add(*category.default_groups.filter(is_active=True))
    if category.default_group_id and category.default_group.is_active:
        ticket.groups.add(category.default_group)
    attach_organizations(ticket)
    TicketDynamicData.objects.create(ticket=ticket, values=payload or {}, reporting_values={'workflow_type':workflow_type,'policy_number':policy.policy_number})
    TicketEvent.objects.create(ticket=ticket, actor=requester, event_type='created', summary=f'{project.name_en} request created', details={'policy':policy.pk,'organization':organization.pk})
    if initialize:
        initialize_approval_workflow(ticket)
        notify_users([requester], ticket=ticket, kind='info', title=f'Request created: {ticket.reference}')
    return ticket


def attach_organizations(ticket):
    """Reuse the same participation records for portal, email and domain intake."""
    if ticket.organization_id:
        TicketOrganization.objects.get_or_create(ticket=ticket,organization=ticket.organization,relationship_type='owner',defaults={'is_primary':True,'can_edit':True,'can_assign':True})
    if ticket.policy_id:
        for organization in ticket.policy.workflow_organizations.filter(is_active=True,organization_type__is_active=True):
            TicketOrganization.objects.get_or_create(ticket=ticket,organization=organization,relationship_type='processing',defaults={'can_edit':True,'can_assign':True})
