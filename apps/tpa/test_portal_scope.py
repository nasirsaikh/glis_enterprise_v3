from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import BenefitPlanSetupForm, PolicyEnrollmentForm, QueryRaiseForm
from .models import InboundEmail, MemberAction, MemberTransaction, Policy, TPAOrganization
from .services.access import can_edit_tpa_intake, visible_inbound_emails, visible_policies, visible_transactions


class TPAPortalScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_user("tenant-configurator", is_staff=True)
        cls.peer = User.objects.create_user("tenant-peer")
        cls.outsider = User.objects.create_user("tenant-outside")
        cls.sponsor = TPAOrganization.objects.create(code="SCP-A", name_en="Scoped sponsor", organization_type="CORPORATE")
        cls.other_sponsor = TPAOrganization.objects.create(code="SCP-B", name_en="Other sponsor", organization_type="CORPORATE")
        cls.insurer = TPAOrganization.objects.create(code="SCP-IN", name_en="Scoped insurer", organization_type="INSURER")
        cls.actor.profile.organizations.add(cls.sponsor)
        cls.peer.profile.organizations.add(cls.sponsor)
        cls.outsider.profile.organizations.add(cls.other_sponsor)
        cls.actor.user_permissions.add(Permission.objects.get(codename="configure_tpa"))
        cls.policy = Policy.objects.create(sponsor=cls.sponsor, insurance_company=cls.insurer,
            policy_number="SCOPE-A", start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31))
        cls.other_policy = Policy.objects.create(sponsor=cls.other_sponsor, insurance_company=cls.insurer,
            policy_number="SCOPE-B", start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31))
        cls.tx = MemberTransaction.objects.create(sponsor=cls.sponsor, insurer=cls.insurer, policy=cls.policy,
            transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT, effective_date=date(2026, 1, 1),
            requester=cls.peer, requester_organization=cls.sponsor)
        cls.other_tx = MemberTransaction.objects.create(sponsor=cls.other_sponsor, insurer=cls.insurer,
            policy=cls.other_policy, transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT,
            effective_date=date(2026, 1, 1), requester=cls.outsider, requester_organization=cls.other_sponsor)
        cls.email = InboundEmail.objects.create(provider="test", provider_message_id="scope-a",
            sender="hr@example.com", recipient="intake@example.com", received_at=timezone.now(),
            subject="Own organization email", transaction=cls.tx)
        cls.other_email = InboundEmail.objects.create(provider="test", provider_message_id="scope-b",
            sender="other@example.com", recipient="intake@example.com", received_at=timezone.now(),
            subject="Other organization email", transaction=cls.other_tx)

    def setUp(self):
        self.client.force_login(self.actor)

    def policy_data(self, **values):
        return {"policy_number": "SCOPE-A-EDIT", "policy_name": "Updated policy", "start_date": "2026-02-01",
                "expiry_date": "2027-01-31", "currency": "usd", "allowed_backdating_days": 30, **values}

    def edit(self, tx=None, **data):
        return self.client.post(reverse("tpa:policy_details_edit", args=[(tx or self.tx).reference]),
                                self.policy_data(**data), HTTP_HX_REQUEST="true")

    def test_configuration_permission_remains_within_organization(self):
        self.assertIn(self.policy, visible_policies(self.actor))
        self.assertNotIn(self.other_policy, visible_policies(self.actor))
        self.assertNotIn(self.other_tx, visible_transactions(self.actor))
        self.assertFalse(can_edit_tpa_intake(self.actor, self.other_tx))
        self.assertEqual(self.edit(self.other_tx).status_code, 404)
        self.assertEqual(self.client.get(reverse("tpa:transaction_detail", args=[self.other_tx.reference])).status_code, 404)

    def test_email_lists_and_attachment_entry_points_use_same_scope(self):
        self.assertIn(self.email, visible_inbound_emails(self.actor))
        self.assertNotIn(self.other_email, visible_inbound_emails(self.actor))
        response = self.client.get(reverse("tpa:inbound_email_list"))
        self.assertContains(response, "Own organization email")
        self.assertNotContains(response, "Other organization email")
        self.assertEqual(self.client.get(reverse("tpa:inbound_email_detail", args=[self.other_email.pk])).status_code, 404)

    def test_create_sponsor_and_query_participants_are_scoped(self):
        form = PolicyEnrollmentForm(user=self.actor)
        self.assertIn(self.sponsor, form.fields["sponsor"].queryset)
        self.assertNotIn(self.other_sponsor, form.fields["sponsor"].queryset)
        form = QueryRaiseForm(transaction=self.tx, user=self.actor)
        self.assertIn(self.peer, form.fields["selected_participants"].queryset)
        self.assertNotIn(self.outsider, form.fields["selected_participants"].queryset)

    def test_plan_form_has_no_description(self):
        self.assertNotIn("description", BenefitPlanSetupForm(policy=self.policy).fields)

    def test_policy_edits_reset_validation_and_preserve_manual_member_fields(self):
        self.tx.status = self.tx.Status.PENDING_VALIDATION
        self.tx.validation_score = 100
        self.tx.validation_completed_at = timezone.now()
        self.tx.validation_bypassed = True
        self.tx.save()
        row = MemberAction.objects.create(transaction=self.tx, action=self.tx.transaction_type, row_number=1,
            corrected_data={"first_name": "Preserve", "effective_date": "2026-01-01"},
            validation_status=MemberAction.Result.VALID, calculated_premium=50)
        response = self.edit()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-current-step="policy_setup"')
        self.tx.refresh_from_db()
        self.policy.refresh_from_db()
        row.refresh_from_db()
        self.assertEqual(self.policy.policy_number, "SCOPE-A-EDIT")
        self.assertEqual(self.tx.effective_date, date(2026, 2, 1))
        self.assertEqual(self.tx.currency, "USD")
        self.assertEqual(self.tx.status, self.tx.Status.DRAFT)
        self.assertIsNone(self.tx.validation_completed_at)
        self.assertFalse(self.tx.validation_bypassed)
        self.assertEqual(row.corrected_data["first_name"], "Preserve")
        self.assertEqual(row.corrected_data["effective_date"], "2026-02-01")
        self.assertEqual(row.calculated_premium, 0)
        self.assertTrue(self.tx.events.filter(event_type="policy_details_updated").exists())

    def test_invalid_policy_dates_preserve_values_without_saving(self):
        response = self.edit(start_date="2026-12-31", expiry_date="2026-01-01")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Expiry date cannot be before start date")
        self.assertContains(response, "SCOPE-A-EDIT")
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.policy_number, "SCOPE-A")

    def test_completed_initial_enrollment_cannot_be_edited(self):
        self.policy.initial_enrollment_completed_at = timezone.now()
        self.policy.save()
        self.assertEqual(self.edit().status_code, 403)
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.policy_number, "SCOPE-A")

    def test_pagination_and_search_cover_rows_beyond_first_page(self):
        for number in range(25):
            MemberTransaction.objects.create(sponsor=self.sponsor, insurer=self.insurer, policy=self.policy,
                transaction_type=MemberTransaction.Type.MEMBER_ADD, effective_date=date(2026, 1, 1),
                requester=self.peer, requester_organization=self.sponsor, remarks=f"Batch {number}")
        response = self.client.get(reverse("tpa:transaction_list"))
        self.assertEqual(len(response.context["page_obj"]), 20)
        self.assertTrue(response.context["page_obj"].has_next())
        response = self.client.get(reverse("tpa:transaction_list"), {"page": 2})
        self.assertEqual(len(response.context["page_obj"]), 5)
        first = self.policy.transactions.filter(transaction_type=MemberTransaction.Type.MEMBER_ADD).order_by("pk").first()
        response = self.client.get(reverse("tpa:transaction_list"), {"q": first.reference})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertContains(response, first.reference)

    def test_global_mail_sync_does_not_grant_other_organization_email_access(self):
        self.other_email.provider = "office365_graph"
        self.other_email.created_by = self.actor
        self.other_email.save()
        self.assertNotIn(self.other_email, visible_inbound_emails(self.actor))
        self.assertEqual(self.client.post(reverse("tpa:inbound_email_sync_now")).status_code, 403)

    def test_vanna_policy_and_related_rows_use_portal_scope(self):
        from apps.orchestrator.local_vanna import SqlGovernor
        from apps.orchestrator.models import AIDomain, DataSource
        source = DataSource.objects.create(name="Policy analytics", engine="sqlite", is_read_only=True)
        domain = AIDomain.objects.create(name="Policy analytics", slug="policy-scope",
                                        allowed_tables=["tickets_ticket", "tpa_policy", "tpa_memberaction"])
        domain.data_sources.add(source)
        governor = SqlGovernor(domain=domain, user=self.actor)
        sql = governor.govern("SELECT policy_number FROM tpa_policy")
        self.assertIn(f'WHERE id IN ({self.policy.pk})', sql)
        self.assertNotIn(str(self.other_policy.pk), sql.split("WHERE id IN (", 1)[1].split(")", 1)[0])
        sql = governor.govern("SELECT row_number FROM tpa_memberaction")
        self.assertIn(f'WHERE transaction_id IN ({self.tx.pk})', sql)
        joined = governor.govern("SELECT p.policy_number FROM tpa_policy p JOIN tickets_ticket t ON t.id = p.id")
        self.assertEqual(joined.count("WITH "), 1)
        self.assertIn("tickets_ticket AS", joined)
        with self.assertRaises(ValueError):
            governor.govern("SELECT policy_number FROM main.tpa_policy")

    def test_vanna_parser_scopes_comma_joins_and_blocks_qualified_bypasses(self):
        from django.db import connection
        from apps.orchestrator.local_vanna import SqlGovernor
        from apps.orchestrator.models import AIDomain
        domain = AIDomain.objects.create(name="Join analytics", slug="join-scope",
                                        allowed_tables=["tickets_ticket", "tpa_policy", "tpa_memberaction"])
        governor = SqlGovernor(domain=domain, user=self.actor)
        sql = governor.govern("SELECT policy_number FROM tpa_policy")
        with connection.cursor() as cursor:
            cursor.execute(sql)
            self.assertEqual(cursor.fetchall(), [(self.policy.policy_number,)])
        comma = governor.govern("SELECT p.policy_number FROM tickets_ticket t, tpa_policy p")
        self.assertIn("tpa_policy AS", comma)
        self.assertIn("tickets_ticket AS", comma)
        with self.assertRaises(ValueError):
            governor.govern("SELECT p.policy_number FROM tickets_ticket t, main.tpa_policy p")
        with self.assertRaises(ValueError):
            governor.govern("SELECT p.policy_number FROM tickets_ticket t, auth_user p")
