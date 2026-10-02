from django.db import transaction
from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ticket, TicketApproval, TicketAttachment, TicketComment, TicketEvent


def bump_revision(ticket_id):
    Ticket.objects.filter(pk=ticket_id).update(revision=F('revision') + 1)


@receiver(post_save, sender=Ticket)
def ticket_saved(sender, instance, created, raw=False, **kwargs):
    if not raw and not created:
        bump_revision(instance.pk)
        instance.revision = Ticket.objects.values_list('revision', flat=True).get(pk=instance.pk)


@receiver(post_save, sender=TicketEvent)
@receiver(post_save, sender=TicketComment)
@receiver(post_save, sender=TicketAttachment)
@receiver(post_save, sender=TicketApproval)
def activity_saved(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    bump_revision(instance.ticket_id)
    if sender is TicketEvent and created:
        from services.ticket_notifications import enqueue_activity
        transaction.on_commit(lambda pk=instance.pk: enqueue_activity(pk))
