"""Atomic, per-prefix annual reference allocation through project configuration."""
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from apps.tickets.models import TicketSequence

@transaction.atomic
def allocate_reference(project):
    prefix, year = (project.ticket_prefix or project.code).upper(), timezone.localdate().year
    counter, _ = TicketSequence.objects.get_or_create(prefix=prefix, year=year)
    counter = TicketSequence.objects.select_for_update().get(pk=counter.pk)
    TicketSequence.objects.filter(pk=counter.pk).update(value=F('value') + 1)
    counter.refresh_from_db()
    reference = project.reference_format.format(prefix=prefix, year=year, sequence=counter.value)
    if len(reference) > 80:
        raise ValueError('Configured ticket reference exceeds 80 characters.')
    return reference
