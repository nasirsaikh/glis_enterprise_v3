from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CardDispatch, MemberAction, MemberTransaction, SourceDocument, TransactionEvent


@receiver(post_save, sender=MemberTransaction)
@receiver(post_save, sender=MemberAction)
@receiver(post_save, sender=SourceDocument)
@receiver(post_save, sender=CardDispatch)
def update_ticket_revision(sender, instance, raw=False, **kwargs):
    if not raw:
        ticket_id = instance.ticket_id if sender is MemberTransaction else instance.transaction.ticket_id
        if ticket_id:
            from apps.tickets.signals import bump_revision
            bump_revision(ticket_id)


@receiver(post_save, sender=TransactionEvent)
def record_ticket_activity(sender, instance, created, raw=False, **kwargs):
    if raw or not created or instance.event_type == 'ticket_closed':
        return
    tx = instance.transaction
    if tx.ticket_id:
        from apps.tickets.models import TicketEvent
        TicketEvent.objects.create(ticket_id=tx.ticket_id, actor_id=instance.actor_id,
            event_type=f'tpa_{instance.event_type}', summary=instance.summary,
            details={'transaction_reference': tx.reference, **instance.details})


@receiver(post_save, sender=MemberTransaction)
def close_ticket_on_completion(sender, instance, raw=False, **kwargs):
    if not raw and instance.ticket_id and instance.status in {instance.Status.COMPLETED, instance.Status.PROCESSED}:
        from .services.ticketing import close_transaction_ticket
        close_transaction_ticket(instance, getattr(instance, "_completion_actor", None) or instance.approved_by)
