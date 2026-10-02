from django.db import transaction
from django.http import HttpResponse
from django.urls import Resolver404, resolve

from services.access import TicketAccessPolicy
from .models import Ticket


class TicketRevisionMiddleware:
    """Serialize portal mutations and reject an outdated browser revision."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != 'POST' or not request.user.is_authenticated:
            return self.get_response(request)
        try:
            match = resolve(request.path_info, urlconf=getattr(request, 'urlconf', None))
        except Resolver404:
            return self.get_response(request)
        module = match.func.__module__
        if not module.startswith(('apps.tickets.', 'apps.tpa.', 'apps.tasks.', 'apps.core.document_views')):
            return self.get_response(request)
        reference = match.kwargs.get('reference')
        ticket_id = Ticket.objects.filter(reference=reference).values_list('pk', flat=True).first() if reference else None
        if not ticket_id and reference:
            from apps.tpa.models import MemberTransaction
            ticket_id = MemberTransaction.objects.filter(reference=reference).values_list('ticket_id', flat=True).first()
        if not ticket_id and module.startswith('apps.tasks.') and match.kwargs.get('pk'):
            from apps.tasks.models import Task
            ticket_id = Task.objects.filter(pk=match.kwargs['pk']).values_list('ticket_id', flat=True).first()
        if not ticket_id:
            return self.get_response(request)
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().get(pk=ticket_id)
            if not TicketAccessPolicy.can_view(request.user, ticket):
                return self.get_response(request)
            expected = request.POST.get('ticket_revision', request.headers.get('X-Ticket-Revision'))
            if expected is not None and (not expected.isdecimal() or int(expected) != ticket.revision):
                response = HttpResponse('This request was updated by another user. Reload the latest record before submitting your changes.', status=409)
                response['X-Ticket-Stale'] = 'true'
            else:
                # Use Django's normal dispatch so CSRF checks and exception
                # middleware (including inline TPA errors) still run.
                response = self.get_response(request)
            response['X-Ticket-Reference'] = ticket.reference
            if response.status_code >= 400 or transaction.get_rollback():
                transaction.set_rollback(True)
                revision = ticket.revision
            else:
                revision = Ticket.objects.filter(pk=ticket_id).values_list('revision', flat=True).first()
            if revision is not None:
                response['X-Ticket-Revision'] = str(revision)
            return response
