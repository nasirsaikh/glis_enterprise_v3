"""Behavioral coverage for global organizations and the shared request engine."""
from datetime import date
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Organization, OrganizationType
from apps.tpa.models import InboundEmail, MemberTransaction, Policy, PolicyAccess, TransactionQuery
from apps.tpa.services.ai_intake import process_inbound_email
from services.access import TicketAccessPolicy
from services.business_requests import create_business_request
from services.tenancy import organization_ids
from services.ticket_participants import cancel_approval, release_ticket, request_approval, tag_user, take_over_ticket
from services.ticket_workflow import decide_approval, initialize_approval_workflow
from .forms import TicketAssignmentForm, TicketCreateStep1Form, UnifiedRequestForm
from .models import ApprovalStep, ApprovalWorkflow, Product, Project, SupportGroup, Ticket, TicketApproval, TicketOrganization, TicketSequence


class UnifiedWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser('unified-admin', 'admin@example.test', 'test')
        cls.agent = User.objects.create_user('unified-agent', is_staff=True)
        cls.peer = User.objects.create_user('unified-peer')
        cls.insurer_user = User.objects.create_user('unified-insurer')
        cls.outsider = User.objects.create_user('unified-outsider')
        cls.org = Organization.objects.create(code='UNI-A', name_en='Organization A', organization_type_id='CORPORATE')
        cls.other_org = Organization.objects.create(code='UNI-B', name_en='Organization B', organization_type_id='CORPORATE')
        cls.insurer = Organization.objects.create(code='UNI-I', name_en='Insurer', organization_type_id='INSURER')
        cls.processor = Organization.objects.create(code='UNI-P', name_en='Processor', organization_type_id='SERVICE_PROVIDER')
        cls.agent.profile.organizations.add(cls.org)
        cls.peer.profile.organizations.add(cls.org)
        cls.insurer_user.profile.organizations.add(cls.insurer)
        cls.outsider.profile.organizations.add(cls.other_org)
        cls.agent.user_permissions.add(*Permission.objects.filter(content_type__app_label='tickets', codename__in=['assign', 'change_ticket', 'view_all', 'add_ticket']))
        cls.agent.user_permissions.add(Permission.objects.get(content_type__app_label='tpa', codename='create_endorsement'))
        cls.policy = Policy.objects.create(organization=cls.org, insurance_company=cls.insurer,
            product=Product.objects.get(project__code='POL', code='MEDICAL'), policy_number='UNIFIED-1',
            start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), status='active',
            initial_enrollment_completed_at=timezone.now())
        cls.policy.workflow_organizations.add(cls.processor)
        cls.other_policy = Policy.objects.create(organization=cls.other_org, insurance_company=cls.insurer,
            policy_number='UNIFIED-2', start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), status='active')
        cls.group = SupportGroup.objects.create(code='uni-work', name='Unified team', can_assign_group_tickets=True)
        cls.group.organizations.add(cls.org)
        cls.group.members.add(cls.agent)
        cls.project = Project.objects.get(code='ADD')
        cls.project.groups.add(cls.group)

    def tx(self, kind='MEMBER_ADD', **kwargs):
        return MemberTransaction.objects.create(policy=self.policy, organization=self.org, insurer=self.insurer,
            requester=self.agent, requester_organization=self.org, transaction_type=kind,
            effective_date=date(2026, 7, 1), **kwargs)

    def test_global_master_accepts_custom_type_and_multiple_memberships(self):
        kind = OrganizationType.objects.create(code='CUSTOM_TEAM', name='Custom team')
        organization = Organization.objects.create(code='UNI-CUSTOM', name_en='Custom', organization_type=kind)
        self.peer.profile.organizations.add(organization)
        self.assertEqual(set(organization_ids(self.peer)), {self.org.pk, organization.pk})
        kind.is_active = False
        kind.save(update_fields=['is_active'])
        self.assertEqual(organization_ids(self.peer), [self.org.pk])

    def test_organization_hierarchy_rejects_cycles(self):
        self.org.parent_organization = self.other_org
        self.org.save()
        self.other_org.parent_organization = self.org
        with self.assertRaises(ValidationError):
            self.other_org.full_clean()

    def test_all_registered_domain_requests_have_one_required_parent(self):
        mapping = {'NEW_POLICY_ENROLLMENT':'POL', 'MEMBER_ADD':'ADD', 'MEMBER_DELETE':'DEL',
            'MEMBER_TERMINATE':'TRM', 'MEMBER_UPDATE':'CHG', 'MEMBER_SUSPEND':'SUS',
            'MEMBER_REACTIVATE':'REA', 'POLICY_CANCEL':'CAN'}
        for kind, prefix in mapping.items():
            with self.subTest(kind=kind):
                tx = self.tx(kind)
                self.assertTrue(tx.ticket.reference.startswith(prefix+'-'))
                self.assertEqual(tx.reference, tx.ticket.reference)
                self.assertEqual(tx.ticket.policy, self.policy)
                self.assertIsNotNone(tx.ticket.sla_policy)
                self.assertTrue(tx.ticket.organization_participants.filter(organization=self.processor, relationship_type='processing').exists())
                tx.save()
                self.assertEqual(Ticket.objects.filter(tpa_transaction=tx).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MemberTransaction.objects.filter(pk=tx.pk).update(ticket=None)

    def test_failed_domain_insert_does_not_leave_orphan_parent(self):
        before = Ticket.objects.count()
        with self.assertRaises(IntegrityError):
            self.tx(reference='duplicate-reference')
            self.tx(reference='duplicate-reference')
        self.assertEqual(Ticket.objects.count(), before+1)

    def test_configured_prefix_and_format_use_shared_annual_counter(self):
        self.project.ticket_prefix = 'CUSTOM'
        self.project.reference_format = '{prefix}/{year}/{sequence:04d}'
        self.project.full_clean()
        self.project.save()
        first, second = self.tx(), self.tx()
        self.assertEqual(first.reference, f'CUSTOM/{timezone.localdate().year}/0001')
        self.assertEqual(second.reference, f'CUSTOM/{timezone.localdate().year}/0002')
        self.assertEqual(TicketSequence.objects.get(prefix='CUSTOM', year=timezone.localdate().year).value, 2)
        self.project.reference_format = '{prefix}-{year}'
        with self.assertRaises(ValidationError):
            self.project.full_clean()

    def test_missing_configuration_fails_without_creating_a_parallel_workflow(self):
        self.project.is_active = False
        self.project.save()
        before = Ticket.objects.count()
        with self.assertRaisesRegex(ValueError, 'Configure'):
            self.tx()
        self.assertEqual(Ticket.objects.count(), before)

    def test_tagging_gives_visibility_without_mutation_permissions(self):
        tx = self.tx(status='pending_approval')
        self.assertFalse(TicketAccessPolicy.can_view(self.peer, tx.ticket))
        tag_user(tx.ticket, self.agent, self.peer)
        self.assertTrue(TicketAccessPolicy.can_view(self.peer, tx.ticket))
        self.assertFalse(TicketAccessPolicy.can_edit(self.peer, tx.ticket))
        self.assertFalse(TicketAccessPolicy.can_assign(self.peer, tx.ticket))
        self.client.force_login(self.peer)
        url = reverse('portal:ticket_detail', args=[tx.reference])
        self.assertContains(self.client.get(url), tx.reference)
        self.assertEqual(self.client.post(reverse('portal:assign_ticket', args=[tx.reference]), {'users':[self.peer.pk]}).status_code, 403)
        self.assertEqual(self.client.post(reverse('portal:add_comment', args=[tx.reference]), {'body':'Forge status', 'status':'closed'}).status_code, 403)
        tag_user(tx.ticket, self.agent, self.peer, active=False)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_forged_organization_and_approver_are_rejected(self):
        ticket = self.tx().ticket
        self.client.force_login(self.agent)
        response = self.client.post(reverse('portal:assign_ticket', args=[ticket.reference]),
            {'organization':self.other_org.pk, 'users':[self.outsider.pk], 'replace_existing':'on'})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(reverse('portal:request_ticket_approval', args=[ticket.reference]), {'approver':self.outsider.pk})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ticket.approvals.exists())

    def test_assignment_candidates_follow_actual_participants_and_group_filter(self):
        ticket = self.tx().ticket
        self.project.organizations.add(self.org, self.other_org)
        form = TicketAssignmentForm(user=self.agent, ticket=ticket)
        self.assertIn(self.insurer_user, form.fields['users'].queryset)
        self.assertNotIn(self.outsider, form.fields['users'].queryset)
        form = TicketAssignmentForm({'support_group':self.group.pk}, user=self.agent, ticket=ticket)
        self.assertIn(self.agent, form.fields['users'].queryset)
        self.assertNotIn(self.insurer_user, form.fields['users'].queryset)
        self.client.force_login(self.agent)
        response = self.client.get(reverse('portal:assignment_options', args=[ticket.reference]),
            {'organization':self.org.pk, 'support_group':self.group.pk}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['assignment_form'].fields['users'].queryset), [self.agent])

    def test_release_preserves_groups_and_other_assignees_then_takeover_conflicts(self):
        ticket = self.tx().ticket
        ticket.groups.add(self.group)
        ticket.assignees.add(self.agent, self.peer)
        ticket.assignee = self.agent
        ticket.save()
        released = release_ticket(ticket, self.agent)
        self.assertEqual(released.assignee, self.peer)
        self.assertTrue(released.groups.filter(pk=self.group.pk).exists())
        with self.assertRaises(ValueError):
            take_over_ticket(released, self.agent)
        release_ticket(released, self.peer)
        taken = take_over_ticket(released, self.agent)
        self.assertEqual(taken.assignee, self.agent)
        with self.assertRaises(ValueError):
            take_over_ticket(taken, self.agent)
        self.assertEqual(taken.events.filter(event_type='takeover').count(), 1)

    def test_read_only_group_can_view_but_cannot_take_over(self):
        ticket = self.tx().ticket
        self.group.can_edit_group_tickets = False
        self.group.save()
        self.group.members.add(self.peer)
        ticket.groups.add(self.group)
        self.assertTrue(TicketAccessPolicy.can_view(self.peer, ticket))
        with self.assertRaises(PermissionError):
            take_over_ticket(ticket, self.peer)

    def test_individual_approval_is_idempotent_audited_and_advances_domain(self):
        tx = self.tx(status='pending_approval')
        approval = request_approval(tx.ticket, self.agent, self.insurer_user, 'Review evidence')
        self.assertEqual(request_approval(tx.ticket, self.agent, self.insurer_user).pk, approval.pk)
        with self.assertRaises(PermissionError):
            decide_approval(approval, approved=True, note='', actor=self.peer)
        decided = decide_approval(approval, approved=True, note='Accepted', actor=self.insurer_user)
        self.assertEqual(decided.status, 'approved')
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.SENT_TO_TPA)
        self.assertEqual(tx.approved_by, self.insurer_user)
        self.assertEqual(tx.ticket.approval_state, 'approved')
        self.assertEqual(tx.ticket.approvals.count(), 1)
        with self.assertRaises(ValueError):
            decide_approval(decided, approved=True, note='', actor=self.insurer_user)

    def test_approval_cancellation_is_limited_to_requester(self):
        ticket = self.tx().ticket
        approval = request_approval(ticket, self.agent, self.insurer_user)
        with self.assertRaises(PermissionError):
            cancel_approval(approval, self.insurer_user)
        cancel_approval(approval, self.agent)
        ticket.refresh_from_db()
        self.assertEqual(ticket.approval_state, 'not_required')
        self.assertTrue(ticket.events.filter(event_type='approval_cancelled').exists())
        self.assertFalse(TicketAccessPolicy.can_view(self.insurer_user, ticket))
        self.client.force_login(self.agent)
        self.assertContains(self.client.get(reverse('portal:ticket_detail', args=[ticket.reference])), 'id="approval-panel"')

    def test_approval_query_blocks_dispatch_after_ticket_decision(self):
        tx = self.tx(status='pending_approval')
        TransactionQuery.objects.create(transaction=tx, purpose='APPROVAL', audience='CLIENT_VISIBLE',
            subject='Clarify', raised_by=self.admin, status='OPEN')
        approval = request_approval(tx.ticket, self.agent, self.insurer_user)
        decide_approval(approval, approved=True, note='', actor=self.insurer_user)
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.PENDING_APPROVAL)

    def test_configured_sequence_and_individual_request_share_approval_state(self):
        ticket = self.tx().ticket
        workflow = ApprovalWorkflow.objects.create(name='Unified approval')
        step = ApprovalStep.objects.create(workflow=workflow, sequence=1, name='First')
        step.approver_users.add(self.insurer_user)
        ticket.category.approval_workflow = workflow
        ticket.category.save()
        initialize_approval_workflow(ticket)
        individual = request_approval(ticket, self.agent, self.peer)
        decide_approval(ticket.approvals.get(step=step), approved=True, note='', actor=self.insurer_user)
        ticket.refresh_from_db()
        self.assertEqual(ticket.approval_state, 'pending')
        decide_approval(individual, approved=True, note='', actor=self.peer)
        ticket.refresh_from_db()
        self.assertEqual(ticket.approval_state, 'approved')

    def test_canonical_detail_and_htmx_have_one_workspace(self):
        tx = self.tx()
        self.client.force_login(self.agent)
        url = reverse('portal:ticket_detail', args=[tx.reference])
        response = self.client.get(url)
        self.assertContains(response, 'id="transaction-workspace"', count=1)
        response = self.client.get(url, {'step':'intake'}, HTTP_HX_REQUEST='true')
        self.assertNotContains(response, '<!doctype html>')
        self.assertContains(response, 'id="transaction-workspace"', count=1)
        self.assertEqual(response['HX-Push-Url'], url+'?step=intake')
        response = self.client.get(url, HTTP_HX_REQUEST='true', HTTP_HX_HISTORY_RESTORE_REQUEST='true')
        self.assertContains(response, '<!doctype html>')

    def test_tabs_and_counts_apply_identical_scope(self):
        self.tx()
        self.tx('NEW_POLICY_ENROLLMENT')
        create_business_request(workflow_type='CLAIM', policy=self.policy, requester=self.agent)
        MemberTransaction.objects.create(policy=self.other_policy, organization=self.other_org, insurer=self.insurer,
            requester=self.outsider, requester_organization=self.other_org, transaction_type='MEMBER_ADD', effective_date=date(2026,7,1))
        self.client.force_login(self.agent)
        response = self.client.get(reverse('portal:ticket_list'))
        counts = {tab['key']:tab['count'] for tab in response.context['workflow_tabs']}
        self.assertEqual(counts['all'], 3)
        self.assertEqual(counts['policy'], 1)
        self.assertEqual(counts['endorsement'], 1)
        self.assertEqual(counts['claim'], 1)
        response = self.client.get(reverse('portal:ticket_list'), {'tab':'claim'})
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_create_request_endorsement_routes_to_ticket_and_uses_selected_project(self):
        product = Product.objects.get(project=self.project, code='MEDICAL')
        category = product.categories.get(code='MEMBER_ADD')
        self.client.force_login(self.agent)
        response = self.client.post(reverse('portal:create_request'), {'request_type':'endorsement',
            'policy':self.policy.pk, 'project':self.project.pk, 'product':product.pk, 'category':category.pk,
            'effective_date':'2026-07-01'})
        tx = MemberTransaction.objects.get(policy=self.policy)
        self.assertRedirects(response, reverse('portal:ticket_detail', args=[tx.reference]))
        self.assertEqual(tx.ticket.project, self.project)

    def test_policy_driven_request_choices_and_forged_product(self):
        form = UnifiedRequestForm(user=self.agent, initial={'request_type':'endorsement', 'project':self.project.pk, 'policy':self.policy.pk})
        self.assertEqual(form.fields['category'].queryset.count(), 1)
        wrong = Product.objects.create(project=self.project, code='WRONG', name_en='Wrong product')
        form = UnifiedRequestForm({'request_type':'endorsement', 'policy':self.policy.pk, 'project':self.project.pk,
            'product':wrong.pk, 'category':form.fields['category'].queryset.first().pk, 'effective_date':'2026-07-01'}, user=self.agent)
        self.assertFalse(form.is_valid())

    def test_global_permission_does_not_open_other_organization_admin_urls(self):
        request = RequestFactory().get('/admin/')
        request.user = self.agent
        self.assertNotIn(self.other_policy, admin.site._registry[Policy].get_queryset(request))
        self.assertNotIn(self.other_org, admin.site._registry[Organization].get_queryset(request))

    def test_legacy_service_form_cannot_bypass_business_request_permissions(self):
        claim_project = Project.objects.get(code='CLM')
        self.assertNotIn(claim_project, TicketCreateStep1Form(user=self.agent).fields['project'].queryset)
        self.assertIn(claim_project, UnifiedRequestForm(user=self.agent, initial={'request_type':'claim'}).fields['project'].queryset)

    def test_creation_grant_for_another_policy_does_not_authorize_this_policy(self):
        from apps.tpa.forms import TransactionForm
        PolicyAccess.objects.create(user=self.peer, policy=self.policy, organization=self.org, can_view=True)
        PolicyAccess.objects.create(user=self.peer, policy=self.other_policy, organization=self.other_org,
            can_view=True, can_create_endorsement=True)
        product = Product.objects.get(project=self.project, code='MEDICAL')
        self.client.force_login(self.peer)
        response = self.client.post(reverse('portal:create_request'), {'request_type':'endorsement',
            'policy':self.policy.pk, 'project':self.project.pk, 'product':product.pk,
            'category':product.categories.get(code='MEMBER_ADD').pk, 'effective_date':'2026-07-01'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MemberTransaction.objects.exists())
        form = TransactionForm({'policy':self.policy.pk, 'transaction_type':'MEMBER_ADD',
            'effective_date':'2026-07-01'}, user=self.peer)
        self.assertFalse(form.is_valid())
        self.assertIn('Creation permission', str(form.errors['policy']))

    def test_organization_participation_limits_global_mutation_permissions(self):
        ticket = self.tx().ticket
        ticket.status = Ticket.Status.IN_PROGRESS
        ticket.save()
        self.group.can_edit_group_tickets = False
        self.group.can_assign_group_tickets = False
        self.group.save()
        TicketOrganization.objects.filter(ticket=ticket, organization=self.org).update(can_edit=False, can_assign=False)
        self.assertTrue(TicketAccessPolicy.can_view(self.agent, ticket))
        self.assertFalse(TicketAccessPolicy.can_edit(self.agent, ticket))
        self.assertFalse(TicketAccessPolicy.can_assign(self.agent, ticket))
        self.client.force_login(self.agent)
        self.assertEqual(self.client.post(reverse('portal:assign_ticket', args=[ticket.reference]), {}).status_code, 403)

    def test_support_group_organization_mapping_scopes_policy_visibility(self):
        from apps.tpa.services.access import visible_policies, can_create_for_policy
        member = get_user_model().objects.create_user('unified-group-only')
        member.user_permissions.add(Permission.objects.get(content_type__app_label='tpa', codename='view_tpa_dashboard'))
        self.group.members.add(member)
        self.assertIn(self.policy, visible_policies(member))
        self.assertNotIn(self.other_policy, visible_policies(member))
        self.assertFalse(can_create_for_policy(member, self.policy, 'MEMBER_ADD'))

    def test_user_admin_selectors_share_the_organization_boundary(self):
        other_group = SupportGroup.objects.create(code='uni-private', name='Private group')
        other_group.organizations.add(self.other_org)
        request = RequestFactory().get('/admin/auth/user/')
        request.user = self.agent
        form = admin.site._registry[get_user_model()].get_form(request, self.peer)(instance=self.peer)
        self.assertIn(self.org, form.fields['organizations'].queryset)
        self.assertNotIn(self.other_org, form.fields['organizations'].queryset)
        self.assertIn(self.group, form.fields['support_groups'].queryset)
        self.assertNotIn(other_group, form.fields['support_groups'].queryset)

    @patch('apps.tickets.views.notify_users')
    def test_tagged_user_receives_public_update_notification(self, notify):
        ticket = self.tx().ticket
        tag_user(ticket, self.agent, self.peer)
        self.client.force_login(self.agent)
        response = self.client.post(reverse('portal:add_comment', args=[ticket.reference]),
            {'body':'Evidence updated', 'status':ticket.status})
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.peer, notify.call_args.args[0])

    def test_arabic_dynamic_selectors_keep_the_localized_endpoint(self):
        self.client.force_login(self.agent)
        response = self.client.get('/ar/portal/requests/new/', {'request_type':'endorsement'})
        self.assertContains(response, 'hx-get="/ar/portal/requests/new/"')
        self.assertEqual(response.context['form'].fields['policy'].widget.attrs['hx-get'], '/ar/portal/requests/new/')

    def test_approval_admin_cannot_bypass_the_decision_ledger(self):
        request = RequestFactory().get('/admin/tickets/ticketapproval/')
        request.user = self.admin
        approval_admin = admin.site._registry[TicketApproval]
        self.assertFalse(approval_admin.has_add_permission(request))
        self.assertFalse(approval_admin.has_change_permission(request))
        self.assertFalse(approval_admin.has_delete_permission(request))

    @patch('apps.tpa.services.ai_intake.extract_email_payload')
    def test_email_claim_routes_idempotently_to_same_engine(self, extract):
        from apps.ai.models import AIProviderConfig
        provider = AIProviderConfig.objects.create(name='Claim extractor', model_name='fixture', provider='demo')
        payload = {'classification':'CLAIM', 'transaction_type':'CLAIM', 'is_endorsement_request':False,
            'confidence':1, 'policy_number':self.policy.policy_number, 'summary':'Claim evidence', 'members':[]}
        extract.return_value = (payload, provider, None, payload)
        email = InboundEmail.objects.create(provider='manual', provider_message_id='uni-claim', sender='hr@example.test',
            subject='Claim request', received_at=timezone.now(), created_by=self.admin)
        ticket = process_inbound_email(email, self.admin)
        email.refresh_from_db()
        self.assertEqual(email.ticket, ticket)
        self.assertIsNone(email.transaction_id)
        self.assertTrue(ticket.reference.startswith('CLM-'))
        before = Ticket.objects.count()
        self.assertEqual(process_inbound_email(email, self.admin).pk, ticket.pk)
        self.assertEqual(Ticket.objects.count(), before)
