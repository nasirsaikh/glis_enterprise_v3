from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from apps.tickets.models import Category, Product, Project, RelatedTicket, SLAPolicy, Ticket, TicketDynamicData, TicketEvent
from services.ticket_workflow import initialize_approval_workflow
from ..models import TransactionEvent


@transaction.atomic
def close_transaction_ticket(tx, actor=None, *, reason=None):
    """Close a completed workflow's ticket once, including its SLA timestamps."""
    if not tx.ticket_id:
        return
    ticket = Ticket.objects.select_for_update().get(pk=tx.ticket_id)
    if ticket.status == Ticket.Status.CLOSED:
        return
    now = timezone.now()
    ticket.status = Ticket.Status.CLOSED
    ticket.resolved_at = ticket.resolved_at or tx.processed_at or now
    ticket.closed_at = now
    ticket.save(update_fields=["status", "resolved_at", "closed_at", "updated_at"])
    TicketEvent.objects.create(
        ticket=ticket, actor=actor, event_type="tpa_auto_closed",
        summary=reason or f"Automatically closed after {tx.reference} completed.",
        details={"transaction_reference": tx.reference, "policy_number": tx.policy.policy_number},
    )
    TransactionEvent.objects.create(
        transaction=tx, actor=actor, event_type="ticket_closed",
        summary=f"GLIS ticket {ticket.reference} automatically closed.",
    )
    tx.ticket = ticket

def create_parent_ticket(tx):
    from services.business_requests import create_business_request
    return create_business_request(workflow_type=tx.transaction_type, policy=tx.policy, requester=tx.requester,
        organization=tx.organization, description=tx.remarks or f'Effective date: {tx.effective_date}',
        project_id=(tx.metadata or {}).get('workflow_project_id'), initialize=False)


def record_transaction_link(tx):
    from apps.core.models import SiteSettings
    from apps.tickets.models import TicketOrganization
    ticket = tx.ticket
    TicketOrganization.objects.get_or_create(ticket=ticket, organization=tx.requester_organization, relationship_type='requester')
    processor = SiteSettings.load().default_processing_organization
    if processor and processor.is_active:
        TicketOrganization.objects.get_or_create(ticket=ticket, organization=processor, relationship_type='processing',defaults={'can_edit':True,'can_assign':True})
    TicketDynamicData.objects.update_or_create(ticket=ticket, defaults={'reporting_values': {
        'transaction_reference':tx.reference,'organization':tx.organization.name_en,'insurer':tx.insurer.name_en,
        'policy_number':tx.policy.policy_number,'transaction_type':tx.transaction_type,'effective_date':tx.effective_date.isoformat()}})
    TicketEvent.objects.create(ticket=ticket, actor=tx.requester, event_type='domain_linked', summary=f'Business workflow linked: {tx.reference}')
    initialize_approval_workflow(ticket)


@transaction.atomic
def create_ticket_for_transaction(tx, actor=None):
    return tx.ticket


@transaction.atomic
def create_query_ticket(tx, query, actor, message):
    if query.ticket_id:
        return query.ticket

    parent = create_ticket_for_transaction(tx, actor=actor)
    now = timezone.now()
    sla = parent.sla_policy
    ticket = Ticket.objects.create(
        subject=f"{query.get_purpose_display()} · {tx.reference} · {query.subject}",
        description=(
            f"{query.get_purpose_display()} for {tx.reference}.\n\n"
            f"{str(message or '').strip()}"
        ),
        requester=(
            actor
            if getattr(query, "audience", "") == "INSURER_TPA_INTERNAL"
            else tx.requester
        ),
        project=parent.project,
        product=parent.product,
        category=parent.category,
        status=Ticket.Status.PENDING_CUSTOMER,
        priority=parent.priority,
        visibility="restricted",
        is_sensitive=True,
        tags=[
            "tpa",
            "tpa-query",
            str(getattr(query, "purpose", "TPA")).lower(),
            str(getattr(query, "audience", "CLIENT_VISIBLE")).lower(),
            tx.reference.lower(),
            tx.transaction_type.lower().replace("_", "-"),
        ],
        sla_policy=sla,
        first_response_due_at=(
            now + timedelta(minutes=sla.first_response_minutes)
            if sla
            else None
        ),
        resolution_due_at=(
            now + timedelta(minutes=sla.resolution_minutes)
            if sla
            else None
        ),
    )
    groups = list(parent.groups.all())
    if groups:
        ticket.groups.add(*groups)

    query.ticket = ticket
    query.save(update_fields=["ticket", "updated_at"])

    RelatedTicket.objects.get_or_create(
        source=parent,
        target=ticket,
        defaults={"relationship": "tpa_query"},
    )
    TicketDynamicData.objects.update_or_create(
        ticket=ticket,
        defaults={
            "reporting_values": {
                "tpa_transaction_reference": tx.reference,
                "tpa_query_id": query.pk,
                "policy_number": tx.policy.policy_number,
                "transaction_type": tx.transaction_type,
                "query_subject": query.subject,
            }
        },
    )
    TicketEvent.objects.create(
        ticket=ticket,
        actor=actor,
        event_type="tpa_query_created",
        summary=f"TPA query raised for {tx.reference}",
        details={
            "transaction_reference": tx.reference,
            "query_id": query.pk,
            "parent_ticket": parent.reference,
        },
    )
    return ticket
