from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import MemberTransaction


@receiver(post_save, sender=MemberTransaction)
def close_ticket_on_completion(sender, instance, raw=False, **kwargs):
    if not raw and instance.ticket_id and instance.status in {instance.Status.COMPLETED, instance.Status.PROCESSED}:
        from .services.ticketing import close_transaction_ticket
        close_transaction_ticket(instance, getattr(instance, "_completion_actor", None) or instance.approved_by)
