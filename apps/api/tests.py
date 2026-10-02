"""API mutations share the ticket activity ledger and workflow restrictions."""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.tickets import test_ticket_updates as ticket_regressions


class TicketApiActivityTests(TestCase):
    setUpTestData = classmethod(ticket_regressions.TicketUpdateTests.setUpTestData.__func__)
    ticket = ticket_regressions.TicketUpdateTests.ticket

    def test_api_comment_records_activity_and_honors_pending_approval(self):
        ticket = self.ticket()
        self.client.force_login(self.observer)
        url = reverse('api-ticket-comments', args=[ticket.pk])
        self.assertEqual(self.client.post(url, {'body': 'Unauthorized update'}).status_code, 403)
        self.client.force_login(self.creator)
        self.category.send_update_email = True; self.category.save()
        with patch('apps.job_center.queue.enqueue') as enqueue, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {'body': 'Creator context'})
        self.assertEqual(response.status_code, 201)
        event = ticket.events.get(event_type='comment')
        self.assertEqual(event.details['comment_id'], response.json()['data']['id'])
        enqueue.assert_called_once_with('email.ticket_activity', {'event_id': event.pk}, priority=3)

    def test_api_status_and_patch_cannot_skip_approval_or_reopen_window(self):
        ticket = self.ticket()
        self.client.force_login(self.creator)
        url = reverse('api-ticket-status', args=[ticket.pk])
        self.assertEqual(self.client.post(url, {'status': 'resolved'}).status_code, 403)
        self.assertEqual(self.client.patch(reverse('api-ticket-detail', args=[ticket.pk]),
            {'status': 'resolved'}, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post(url, {'status': 'closed'}).status_code, 200)
        ticket.refresh_from_db(); self.assertIsNotNone(ticket.closed_at)
        self.assertTrue(ticket.events.filter(event_type='closed').exists())
        self.assertEqual(self.client.post(url, {'status': 'open'}).status_code, 409)

    def test_api_edit_and_assignment_are_in_activity_history(self):
        ticket = self.ticket(approval=False)
        self.client.force_login(self.admin)
        response = self.client.patch(reverse('api-ticket-detail', args=[ticket.pk]),
            {'subject': 'Updated API request'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(response.json()['data']['revision'], ticket.revision)
        self.assertTrue(ticket.events.filter(event_type='edited', details__changed_fields=['subject']).exists())
        response = self.client.post(reverse('api-ticket-assign', args=[ticket.pk]), {'user_id': self.agent.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ticket.events.filter(event_type='assignment').exists())

    def test_api_activity_hides_private_events_and_exposes_action_labels(self):
        from apps.tickets.models import TicketEvent
        ticket = self.ticket(approval=False)
        TicketEvent.objects.create(ticket=ticket, actor=self.creator, event_type='edited', summary='Visible change')
        TicketEvent.objects.create(ticket=ticket, actor=self.agent, event_type='private', summary='Hidden investigation', details={'is_internal': True})
        self.client.force_login(self.creator)
        response = self.client.get(reverse('api-ticket-events', args=[ticket.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['description'] for item in response.json()['data']], ['Visible change'])
