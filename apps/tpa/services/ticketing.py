from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from apps.tickets.models import Category, Product, Project, SLAPolicy, Ticket, TicketDynamicData, TicketEvent
from services.ticket_workflow import initialize_approval_workflow
from ..models import TransactionEvent

CATEGORY_CODES={
    "NEW_POLICY_ENROLLMENT":"new-policy-enrollment","MEMBER_ADD":"member-addition","MEMBER_TERMINATE":"member-termination",
    "MEMBER_DELETE":"member-deletion","POLICY_CANCEL":"policy-cancellation",
}
@transaction.atomic
def create_ticket_for_transaction(tx, actor=None):
    if tx.ticket_id: return tx.ticket
    project,_=Project.objects.get_or_create(code="TPA",defaults={"name_en":"TPA Member Management","name_ar":"إدارة أعضاء TPA"})
    product,_=Product.objects.get_or_create(project=project,code="ENROLL-ENDORSE",defaults={"name_en":"Enrollment & Endorsements","name_ar":"التسجيل والتعديلات"})
    category,_=Category.objects.get_or_create(product=product,code=CATEGORY_CODES[tx.transaction_type],defaults={"name_en":tx.get_transaction_type_display(),"name_ar":"","default_priority":"medium"})
    sla=SLAPolicy.objects.filter(category=category,priority=category.default_priority,is_active=True).first()
    now=timezone.now()
    ticket=Ticket.objects.create(
        subject=f"{tx.get_transaction_type_display()} · {tx.policy.policy_number} · {tx.sponsor.name_en}",
        description=f"TPA transaction {tx.reference}. Effective date: {tx.effective_date:%d-%b-%Y}.",
        requester=tx.requester,project=project,product=product,category=category,priority=category.default_priority,
        tags=["tpa","member-management",tx.transaction_type.lower().replace("_","-"),"stp" if tx.stp_eligible else "manual-review"],
        is_sensitive=True,sla_policy=sla,
        first_response_due_at=now+timedelta(minutes=sla.first_response_minutes) if sla else None,
        resolution_due_at=now+timedelta(minutes=sla.resolution_minutes) if sla else None,
    )
    groups=list(category.default_groups.filter(is_active=True))
    if category.default_group and category.default_group not in groups: groups.append(category.default_group)
    if groups: ticket.groups.add(*groups)
    tx.ticket=ticket; tx.save(update_fields=["ticket","updated_at"])
    TicketDynamicData.objects.update_or_create(ticket=ticket,defaults={"reporting_values":{
        "tpa_transaction_reference":tx.reference,"sponsor":tx.sponsor.name_en,"insurer":tx.insurer.name_en,
        "policy_number":tx.policy.policy_number,"transaction_type":tx.transaction_type,"effective_date":tx.effective_date.isoformat(),
        "ai_used":bool(tx.ai_extraction_status),"stp_eligible":tx.stp_eligible,
    }})
    TicketEvent.objects.create(ticket=ticket,actor=actor,event_type="tpa_transaction",summary=f"TPA transaction linked: {tx.reference}",details={"transaction_reference":tx.reference})
    TransactionEvent.objects.create(transaction=tx,actor=actor,event_type="ticket_created",summary=f"GLIS ticket {ticket.reference} created")
    initialize_approval_workflow(ticket)
    return ticket
