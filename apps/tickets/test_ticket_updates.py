"""Regressions for ticket approval recovery, category rules and dashboard scope."""
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from services.access import TicketAccessPolicy
from services.ticket_lifecycle import close_ticket, reopen_ticket
from services.ticket_workflow import current_approval_sequence, decide_approval, initialize_approval_workflow, resubmit_approval
from .forms import TicketCommentForm
from .models import ApprovalStep, ApprovalWorkflow, Category, Product, Project, SupportGroup, Ticket, TicketComment, TicketEvent, TicketTaggedUser


class TicketUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.creator = User.objects.create_user('update-creator', email='creator@example.test')
        cls.peer = User.objects.create_user('update-peer')
        cls.agent = User.objects.create_user('update-agent')
        cls.approver1 = User.objects.create_user('update-approver-1')
        cls.approver2 = User.objects.create_user('update-approver-2')
        cls.observer = User.objects.create_user('update-observer')
        cls.admin = User.objects.create_superuser('update-admin', 'admin@example.test', 'test')
        cls.team = SupportGroup.objects.create(code='UPDATE-CREATOR', name='Creator team')
        cls.team.members.add(cls.creator, cls.peer)
        cls.work = SupportGroup.objects.create(code='UPDATE-AGENT', name='Handler team')
        cls.work.members.add(cls.agent)
        cls.project = Project.objects.create(code='UPDATE', name_en='Updates')
        cls.product = Product.objects.create(project=cls.project, code='UPDATE', name_en='Updates')
        cls.category = Category.objects.create(product=cls.product, code='UPDATE', name_en='Updates', send_initial_email=False, send_update_email=False)
        cls.workflow = ApprovalWorkflow.objects.create(name='Two step approval')
        cls.step1 = ApprovalStep.objects.create(workflow=cls.workflow, sequence=1, name='Review')
        cls.step2 = ApprovalStep.objects.create(workflow=cls.workflow, sequence=2, name='Authorize')
        cls.step1.approver_users.add(cls.approver1)
        cls.step2.approver_users.add(cls.approver2)

    def ticket(self, approval=True):
        self.category.approval_workflow = self.workflow if approval else None
        self.category.save()
        ticket = Ticket.objects.create(project=self.project, product=self.product, category=self.category, requester=self.creator,
            subject='Approval evidence', description='Original details', status=Ticket.Status.IN_PROGRESS)
        ticket.groups.add(self.work)
        TicketTaggedUser.objects.create(ticket=ticket, user=self.observer, tagged_by=self.creator)
        if approval:
            initialize_approval_workflow(ticket)
        return ticket

    def url(self, name, ticket):
        return reverse('portal:' + name, args=[ticket.reference])

    def test_pending_comments_hidden_and_rejected_for_other_participants(self):
        ticket = self.ticket()
        for user in (self.agent, self.approver1, self.observer):
            self.client.force_login(user)
            self.assertNotContains(self.client.get(self.url('ticket_detail', ticket)), 'id="ticket-comment-form"')
            self.assertEqual(self.client.post(self.url('add_comment', ticket), {'body': 'Forbidden update'}).status_code, 403)
            self.assertEqual(self.client.post(self.url('close_ticket', ticket)).status_code, 403)
        self.assertEqual(ticket.comments.count(), 0)

    def test_creator_team_can_comment_and_close_pending_ticket(self):
        ticket = self.ticket()
        for user in (self.creator, self.peer):
            self.client.force_login(user)
            self.assertContains(self.client.get(self.url('ticket_detail', ticket)), 'id="ticket-comment-form"')
            self.assertEqual(self.client.post(self.url('add_comment', ticket), {'body': 'Additional context', 'status': ''}).status_code, 302)
        self.client.force_login(self.peer)
        self.assertEqual(self.client.post(self.url('close_ticket', ticket)).status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.approval_state, ticket.resume_status), ('closed', 'pending', 'in_progress'))

    def test_close_and_reopen_preserve_completed_and_pending_steps(self):
        ticket = self.ticket()
        decide_approval(ticket.approvals.get(step=self.step1), approved=True, note='Accepted', actor=self.approver1)
        closed = close_ticket(ticket, self.creator)
        with self.assertRaises(ValueError):
            decide_approval(ticket.approvals.get(step=self.step2), approved=True, note='', actor=self.approver2)
        reopened = reopen_ticket(closed, self.peer)
        self.assertEqual(reopened.status, 'in_progress')
        self.assertEqual(current_approval_sequence(reopened), 2)
        self.assertEqual(reopened.approvals.get(step=self.step1).status, 'approved')
        self.assertEqual(reopened.approvals.get(step=self.step2).status, 'pending')
        decide_approval(reopened.approvals.get(step=self.step2), approved=True, note='Done', actor=self.approver2)
        reopened.refresh_from_db()
        self.assertEqual(reopened.approval_state, 'approved')

    def test_reopen_button_and_endpoint_follow_category_window(self):
        ticket = close_ticket(self.ticket(), self.creator)
        self.client.force_login(self.creator)
        self.assertContains(self.client.get(self.url('ticket_detail', ticket)), 'Reopen ticket')
        for days, age in ((0, 0), (2, 3)):
            ticket.category.reopen_allowed_days = days
            ticket.category.save()
            ticket.closed_at = timezone.now() - timedelta(days=age)
            ticket.save()
            self.assertNotContains(self.client.get(self.url('ticket_detail', ticket)), '>Reopen ticket</button>')
            self.assertEqual(self.client.post(self.url('reopen_ticket', ticket)).status_code, 409)
            self.assertEqual(self.client.post(self.url('add_comment', ticket), {'body': 'Bypass', 'status': 'open'}).status_code, 403)

    def test_query_response_resumes_same_step_and_keeps_decision_history(self):
        ticket = self.ticket()
        first = ticket.approvals.get(step=self.step1)
        second = ticket.approvals.get(step=self.step2)
        decide_approval(first, approved=True, note='First review passed', actor=self.approver1)
        decide_approval(second, decision='needs_info', note='Supply the effective date', actor=self.approver2)
        ticket.refresh_from_db()
        self.assertEqual(ticket.approval_state, 'needs_info')
        with self.assertRaises(ValueError):
            decide_approval(second, approved=True, note='', actor=self.approver2)
        with self.assertRaises(PermissionError):
            resubmit_approval(ticket, actor=self.agent, note='Attempted bypass')
        self.client.force_login(self.peer)
        self.assertContains(self.client.get(self.url('ticket_detail', ticket)), 'Supply the effective date')
        self.assertEqual(self.client.post(self.url('resubmit_ticket_approval', ticket), {'note': 'Effective date supplied in the evidence'}).status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.approval_state, 'pending')
        self.assertEqual(ticket.approvals.get(step=self.step1).status, 'approved')
        second.refresh_from_db()
        self.assertEqual(second.status, 'pending')
        self.assertTrue(ticket.events.filter(event_type='approval_resubmitted', details__previous_note='Supply the effective date').exists())
        decide_approval(second, approved=True, note='Date confirmed', actor=self.approver2)
        ticket.refresh_from_db()
        self.assertEqual(ticket.approval_state, 'approved')

    def test_rejected_step_cannot_be_bypassed_by_later_approver(self):
        ticket = self.ticket()
        decide_approval(ticket.approvals.get(step=self.step1), approved=False, note='Correct evidence', actor=self.approver1)
        with self.assertRaises(ValueError):
            decide_approval(ticket.approvals.get(step=self.step2), approved=True, note='', actor=self.approver2)
        ticket.refresh_from_db()
        resubmit_approval(ticket, actor=self.creator, note='Evidence corrected')
        self.assertEqual(current_approval_sequence(ticket), 1)
        self.assertEqual(ticket.approvals.get(step=self.step2).status, 'pending')

    def test_comment_status_never_offers_new_or_advances_pending_workflow(self):
        ticket = self.ticket()
        self.assertNotIn('new', dict(TicketCommentForm(ticket=ticket, user=self.creator).fields['status'].choices))
        self.client.force_login(self.creator)
        for status in ('new', 'resolved', 'open'):
            self.assertIn(self.client.post(self.url('add_comment', ticket), {'body': 'Attempt', 'status': status}).status_code, [302, 403])
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'in_progress')
        self.assertFalse(ticket.comments.exists())

    def test_creation_and_comment_attachment_requirements_are_independent(self):
        ticket = self.ticket(approval=False)
        ticket.category.creation_attachment_required = True
        ticket.category.comment_attachment_required = False
        ticket.category.save()
        self.client.force_login(self.creator)
        self.assertEqual(self.client.post(self.url('add_comment', ticket), {'body': 'No comment attachment required'}).status_code, 302)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            file = SimpleUploadedFile('evidence.pdf', b'%PDF-1.4 test', content_type='application/pdf')
            self.assertEqual(self.client.post(self.url('add_comment', ticket), {'body': 'Optional attachment', 'attachments': file}).status_code, 302)
        self.assertEqual(ticket.attachments.count(), 1)
        ticket.category.comment_attachment_required = True
        ticket.category.save()
        self.client.post(self.url('add_comment', ticket), {'body': 'Missing required attachment'}, HTTP_HX_REQUEST='true')
        self.assertEqual(ticket.comments.count(), 2)

    def test_required_creation_attachment_is_validated_before_creating_ticket(self):
        self.category.creation_attachment_required = True
        self.category.approval_workflow = None
        self.category.save()
        self.client.force_login(self.creator)
        session = self.client.session
        session['ticket_wizard'] = {'selection': {'project': self.project.pk, 'product': self.product.pk, 'category': self.category.pk},
            'dynamic': {}, 'analysis': {}, 'answers': {}}
        session.save()
        data = {'subject': 'New request', 'description': 'Evidence required', 'priority': 'medium', 'acknowledgment': 'on'}
        response = self.client.post(reverse('portal:create_ticket', args=[4]), data)
        self.assertContains(response, 'Please attach at least one document')
        self.assertFalse(Ticket.objects.filter(subject='New request').exists())
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            data['creation_attachments'] = SimpleUploadedFile('creation.pdf', b'%PDF-1.4 example', content_type='application/pdf')
            self.assertEqual(self.client.post(reverse('portal:create_ticket', args=[4]), data).status_code, 302)
        self.assertEqual(Ticket.objects.get(subject='New request').attachments.count(), 1)

    def test_conversation_contains_activity_and_preserves_internal_visibility(self):
        ticket = self.ticket(approval=False)
        TicketEvent.objects.create(ticket=ticket, actor=self.creator, event_type='assignment', summary='Assigned to operations')
        TicketEvent.objects.create(ticket=ticket, actor=self.creator, event_type='edited', summary='Secret internal activity', details={'is_internal': True})
        TicketComment.objects.create(ticket=ticket, author=self.creator, body='Private message', is_internal=True)
        self.client.force_login(self.creator)
        response = self.client.get(self.url('ticket_detail', ticket))
        self.assertContains(response, 'data-ticket-event="assignment"')
        self.assertNotContains(response, 'Secret internal activity')
        self.assertNotContains(response, 'Private message')

    def test_dashboard_filters_all_counts_charts_and_lists(self):
        ticket = self.ticket(approval=False)
        other = self.ticket(approval=False)
        other.status = 'closed'
        other.save()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('portal:dashboard'), {'q': ticket.reference, 'status': 'in_progress', 'group': self.work.pk})
        self.assertEqual(response.context['metrics']['open'], 1)
        self.assertEqual(list(response.context['recent_tickets']), [ticket])
        self.assertEqual(response.context['chart_data']['status'], [{'status': 'in_progress', 'total': 1}])
        ticket.assignee = self.peer
        ticket.save(update_fields=['assignee'])
        ticket.assignees.add(self.peer, self.agent)
        assigned = self.client.get(reverse('portal:dashboard'), {'assignee': self.peer.pk})
        self.assertEqual(assigned.context['metrics']['open'], 1)
        self.assertEqual(assigned.context['chart_data']['status'], [{'status': 'in_progress', 'total': 1}])
        invalid = self.client.get(reverse('portal:dashboard'), {'date_from': '2026-10-02', 'date_to': '2026-09-01'})
        self.assertContains(invalid, 'The end date must be on or after')
        self.assertEqual(invalid.context['metrics']['open'], 0)
        self.client.force_login(self.observer)
        untagged = Ticket.objects.create(project=self.project, product=self.product, category=self.category, requester=self.agent, subject='Private outsider request', description='Private')
        visible = self.client.get(reverse('portal:dashboard'), {'q': untagged.reference})
        self.assertEqual(visible.context['metrics']['open'], 0)

    def test_profile_photo_used_in_requester_comment_and_activity_avatars(self):
        ticket = self.ticket(approval=False)
        self.creator.profile.avatar = 'avatars/profile.png'
        self.creator.profile.save()
        TicketComment.objects.create(ticket=ticket, author=self.creator, body='Photo update')
        TicketEvent.objects.create(ticket=ticket, actor=self.creator, event_type='edited', summary='Photo activity')
        self.client.force_login(self.creator)
        self.assertContains(self.client.get(self.url('ticket_detail', ticket)), 'src="/media/avatars/profile.png"', count=5)
        ticket.assignees.add(self.creator)
        self.assertContains(self.client.get(reverse('portal:ticket_list')), 'src="/media/avatars/profile.png"', count=2)


class LinkedApprovalRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_unified_workflow import UnifiedWorkflowTests
        UnifiedWorkflowTests.setUpTestData.__func__(cls)

    def tx(self, **kwargs):
        from .test_unified_workflow import UnifiedWorkflowTests
        return UnifiedWorkflowTests.tx(self, **kwargs)

    def test_linked_rejection_can_reopen_resubmit_and_continue_approval(self):
        from services.ticket_participants import request_approval
        tx = self.tx(status='pending_approval')
        approval = request_approval(tx.ticket, self.agent, self.insurer_user)
        decide_approval(approval, approved=False, note='Correct the supporting evidence', actor=self.insurer_user)
        tx.refresh_from_db()
        tx.ticket.refresh_from_db()
        self.assertEqual(tx.status, 'rejected')
        self.assertEqual(tx.ticket.status, 'closed')
        ticket = reopen_ticket(tx.ticket, self.agent)
        resubmit_approval(ticket, actor=self.agent, note='Evidence corrected')
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'pending_approval')
        approval.refresh_from_db()
        decide_approval(approval, approved=True, note='Evidence accepted', actor=self.insurer_user)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'sent_to_tpa')

    def test_linked_information_request_blocks_business_approval(self):
        from apps.tpa.services.stp import evaluate_stp
        from apps.tpa.services.workflow import approve_transaction
        from services.ticket_participants import request_approval
        tx = self.tx(status='pending_approval')
        approval = request_approval(tx.ticket, self.agent, self.insurer_user)
        decide_approval(approval, decision='needs_info', note='Supply the effective date', actor=self.insurer_user)
        tx.refresh_from_db()
        tx.ticket.refresh_from_db()
        self.assertIn('APPROVAL_REQUIRED', evaluate_stp(tx)[1])
        with self.assertRaises(ValueError):
            approve_transaction(tx, self.admin)
        self.assertEqual(tx.status, 'pending_approval')

    def test_closed_linked_ticket_holds_its_business_step_until_reopened(self):
        from apps.tpa.services.workflow import start_tpa_processing
        tx = self.tx(status='sent_to_tpa')
        ticket = close_ticket(tx.ticket, self.agent)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('portal:ticket_detail', args=[ticket.reference]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_tpa_process'])
        with self.assertRaises(ValueError):
            start_tpa_processing(tx, self.admin)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'sent_to_tpa')
        reopen_ticket(ticket, self.agent)
        start_tpa_processing(tx, self.admin)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'tpa_in_progress')
