import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.ai.models import AIExtractionProfile, AIProviderConfig, AITrainingExample
from apps.core.models import AuditLog
from apps.tickets.models import Ticket, TicketEvent
from .models import BenefitPlan, InboundEmail, Member, MemberAction, MemberPolicyEnrollment, MemberTransaction, Policy, PolicyAccess, TPAOrganization
from .services.ai_intake import extract_email_payload, _profile_prompt
from .services.document_intake import _system_prompt
from .services.extraction import normalize_ai_payload, select_profile
from .services.policy_dashboard import policy_dashboard
from .services.ticketing import close_transaction_ticket, create_ticket_for_transaction
from .services.workflow import complete_tpa_transaction


class PolicyToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("policy-admin", "pa@example.com", "test")
        cls.reader = User.objects.create_user("policy-reader", password="test")
        cls.editor = User.objects.create_user("policy-editor", password="test")
        cls.sponsor = TPAOrganization.objects.create(code="TOOLS-SP", name_en="Sponsor", organization_type="CORPORATE")
        cls.insurer = TPAOrganization.objects.create(code="TOOLS-IN", name_en="Insurer", organization_type="INSURER")
        cls.policy = Policy.objects.create(sponsor=cls.sponsor, insurance_company=cls.insurer, policy_number="TOOLS-1",
            start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), status="active", allowed_backdating_days=3650,
            initial_enrollment_completed_at=timezone.now())
        cls.plan = BenefitPlan.objects.create(policy=cls.policy, code="GOLD", name="Gold")
        for user in [cls.reader, cls.editor]:
            PolicyAccess.objects.create(user=user, organization=cls.sponsor, policy=cls.policy, can_view=True, can_create_endorsement=user == cls.editor)

    def setUp(self):
        self.client.force_login(self.admin)

    def tx(self, status="draft", **kwargs):
        return MemberTransaction.objects.create(sponsor=self.sponsor, insurer=self.insurer, policy=self.policy,
            requester=self.editor, requester_organization=self.sponsor, effective_date=date(2026, 7, 1),
            transaction_type=kwargs.pop("transaction_type", "MEMBER_ADD"), status=status, **kwargs)

    def row(self, tx):
        return MemberAction.objects.create(transaction=tx, action=tx.transaction_type, row_number=1,
            corrected_data={"employee_id": "00101", "first_name": "Test", "last_name": "Member", "date_of_birth": "1990-01-01",
                            "gender": "Male", "relationship": "PRINCIPAL", "national_id": "00102", "plan_code": "GOLD", "effective_date": "2026-07-01"},
            validation_status="VALID", tpa_effective_date=date(2026, 7, 1), tpa_premium_amount=Decimal("10"), card_number="CARD-001")

    def member(self, status="active", employee="1"):
        member = Member.objects.create(sponsor=self.sponsor, employee_id=employee, first_name="Roster", last_name="Member",
                                       date_of_birth=date(1990, 1, 1), gender="Male", relationship="PRINCIPAL")
        return MemberPolicyEnrollment.objects.create(member=member, policy=self.policy, benefit_plan=self.plan,
                    coverage_start_date=date(2026, 1, 1), enrollment_status=status, premium_amount="25.000")

    def prompt_data(self, **overrides):
        data = {"name": "Mailbox instructions", "task": "EMAIL_EXTRACTION", "applicable_product": "MEDICAL",
                "applicable_transaction_type": "", "system_prompt": "Read all member rows.", "instructions": "Keep identifiers intact.",
                "field_aliases": json.dumps({"national_id": ["CPR"]}), "priority": "1", "is_active": "on"}
        data.update(overrides)
        return data

    def test_latest_enrollment_counts_and_premium_permissions(self):
        old = self.member("terminated")
        MemberPolicyEnrollment.objects.create(member=old.member, policy=self.policy, benefit_plan=self.plan,
            coverage_start_date=date(2026, 7, 1), enrollment_status="active", premium_amount="30.000")
        self.member("suspended", "2")
        self.member("pending", "3")
        data = policy_dashboard(self.policy, self.admin)
        self.assertEqual((data["total_members"], data["active_members"], data["inactive_members"]), (3, 1, 2))
        self.assertEqual(data["covered_members"], 1)
        self.assertEqual(data["active_premium"], Decimal("30.000"))
        self.assertIsNone(policy_dashboard(self.policy, self.reader)["active_premium"])

    def test_dashboard_has_all_endorsements_and_separate_enrollment_workflow(self):
        for i in range(30):
            self.tx()
        self.tx(transaction_type="NEW_POLICY_ENROLLMENT")
        response = self.client.get(reverse("tpa:policy_enrollment_detail", args=[self.policy.pk]))
        self.assertContains(response, "Active vs inactive")
        self.assertEqual(response.context["endorsements"].paginator.count, 30)
        self.assertEqual(len(response.context["endorsements"]), 25)
        self.assertContains(response, "Enrollment workflow")
        self.assertContains(response, 'id="policy-dashboard-data"')

    def test_other_policy_dashboard_is_inaccessible(self):
        other = Policy.objects.create(sponsor=self.sponsor, insurance_company=self.insurer, policy_number="TOOLS-PRIVATE",
                                     start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31))
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse("tpa:policy_enrollment_detail", args=[other.pk])).status_code, 404)

    def test_edit_invalidates_validation_and_updates_member_default_date(self):
        tx = self.tx("pending_validation", validation_score=100, stp_eligible=True, premium_adjustment="20.000")
        row = self.row(tx)
        self.client.force_login(self.editor)
        response = self.client.post(reverse("tpa:transaction_edit_details", args=[tx.reference]),
                                   {"effective_date": "2026-08-01", "refund_basis": "NONE", "remarks": "Corrected date"})
        self.assertEqual(response.status_code, 302)
        tx.refresh_from_db(); row.refresh_from_db()
        self.assertEqual(tx.status, "draft")
        self.assertFalse(tx.stp_eligible)
        self.assertEqual(tx.validation_score, 0)
        self.assertEqual(row.corrected_data["effective_date"], "2026-08-01")
        self.assertEqual(row.validation_status, "ERROR")
        self.assertTrue(tx.events.filter(event_type="details_updated").exists())

    def test_reader_cannot_edit_delete_or_configure_prompts(self):
        tx = self.tx()
        self.client.force_login(self.reader)
        for name in ["transaction_edit_details", "transaction_delete_draft"]:
            response = self.client.post(reverse(f"tpa:{name}", args=[tx.reference]), {"effective_date": "2026-08-01"})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(reverse("tpa:inbound_email_training")).status_code, 403)
        self.assertTrue(MemberTransaction.objects.filter(pk=tx.pk).exists())

    def test_approved_or_completed_requests_cannot_be_edited(self):
        for status in ["pending_approval", "approved", "tpa_in_progress", "completed"]:
            tx = self.tx(status)
            self.assertEqual(self.client.post(reverse("tpa:transaction_edit_details", args=[tx.reference]), {"effective_date": "2026-08-01"}).status_code, 403)

    def test_draft_delete_retains_audit_ticket_and_email(self):
        tx = self.tx(); self.row(tx)
        ticket = create_ticket_for_transaction(tx, self.admin)
        email = InboundEmail.objects.create(transaction=tx, provider_message_id="tools-draft", sender="sender@example.com",
                                          recipient="tpa@example.com", received_at=timezone.now(), processing_state="PROCESSED")
        reference = tx.reference
        response = self.client.post(reverse("tpa:transaction_delete_draft", args=[reference]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(MemberTransaction.objects.filter(pk=tx.pk).exists())
        self.assertEqual(MemberAction.objects.count(), 0)
        ticket.refresh_from_db(); email.refresh_from_db()
        self.assertEqual(ticket.status, "closed")
        self.assertIsNone(email.transaction_id)
        self.assertEqual(email.processing_state, "REVIEW")
        self.assertTrue(AuditLog.objects.filter(action="tpa.draft_deleted", changes__reference=reference).exists())

    def test_delete_requires_post_and_draft_status(self):
        tx = self.tx("pending_validation")
        url = reverse("tpa:transaction_delete_draft", args=[tx.reference])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(MemberTransaction.objects.filter(pk=tx.pk).exists())

    def test_completion_closes_ticket_once_with_sla_timestamps(self):
        tx = self.tx("tpa_in_progress"); self.row(tx)
        ticket = create_ticket_for_transaction(tx, self.admin)
        complete_tpa_transaction(tx, self.admin)
        ticket.refresh_from_db(); tx.refresh_from_db()
        self.assertEqual(tx.status, "completed")
        self.assertEqual(ticket.status, Ticket.Status.CLOSED)
        self.assertEqual(ticket.resolved_at, tx.processed_at)
        self.assertIsNotNone(ticket.closed_at)
        close_transaction_ticket(tx, self.admin)
        self.assertEqual(TicketEvent.objects.filter(ticket=ticket, event_type="tpa_auto_closed").count(), 1)

    def test_initial_enrollment_activates_policy_and_closes_ticket(self):
        self.policy.status = "draft"; self.policy.initial_enrollment_completed_at = None; self.policy.save()
        tx = self.tx("tpa_in_progress", transaction_type="NEW_POLICY_ENROLLMENT"); self.row(tx)
        ticket = create_ticket_for_transaction(tx, self.admin)
        complete_tpa_transaction(tx, self.admin)
        self.policy.refresh_from_db(); ticket.refresh_from_db()
        self.assertEqual(self.policy.status, "active")
        self.assertIsNotNone(self.policy.initial_enrollment_completed_at)
        self.assertEqual(ticket.status, "closed")

    def test_failed_processing_leaves_ticket_open(self):
        tx = self.tx("tpa_in_progress"); self.row(tx)
        ticket = create_ticket_for_transaction(tx, self.admin)
        with patch("apps.tpa.services.workflow._process_add", side_effect=ValueError("Cannot enroll")):
            complete_tpa_transaction(tx, self.admin)
        ticket.refresh_from_db(); tx.refresh_from_db()
        self.assertEqual(tx.status, "failed")
        self.assertNotEqual(ticket.status, "closed")

    def test_manual_completion_also_closes_ticket(self):
        tx = self.tx(); ticket = create_ticket_for_transaction(tx, self.admin)
        tx.status = "completed"; tx.save(update_fields=["status"])
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "closed")

    def test_save_profile_and_aliases_are_used_for_email_extraction(self):
        self.client.post(reverse("tpa:inbound_email_training"), self.prompt_data(action="save"))
        profile = AIExtractionProfile.objects.get(name="Mailbox instructions")
        AIProviderConfig.objects.create(name="Tools mock", provider="mock", task_capabilities=["email_extraction"], allow_sensitive_data=True)
        email = InboundEmail.objects.create(provider_message_id="tools-email", sender="s@example.com", recipient="t@example.com", received_at=timezone.now(), body_text="CPR: 00123")
        with patch("apps.tpa.services.ai_intake.generate_json", return_value=({"members": [{"CPR": "00123"}], "confidence": .9}, 5)) as generate:
            payload, _, selected, _ = extract_email_payload(email, self.admin)
        self.assertEqual(selected.pk, profile.pk)
        self.assertEqual(payload["members"][0]["national_id"], "00123")
        self.assertIn('"national_id": ["CPR"]', generate.call_args.kwargs["system_prompt"])

    def test_preview_uses_unsaved_prompt_without_creating_workflows(self):
        profile = AIExtractionProfile.objects.create(name="Preview", task="EMAIL_EXTRACTION", instructions="Original")
        AIProviderConfig.objects.create(name="Preview model", provider="mock", task_capabilities=["email_extraction"], allow_sensitive_data=True)
        with patch("apps.tpa.management_views.generate_json", return_value=({"members": [{"CPR": "00123"}], "policy_number": "TOOLS-1"}, 5)) as generate:
            response = self.client.post(reverse("tpa:inbound_email_training"), self.prompt_data(action="preview", profile_id=profile.pk, instructions="Updated", **{"preview-sample_text": "CPR: 00123"}), HTTP_HX_REQUEST="true")
        profile.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(profile.instructions, "Original")
        self.assertIn("Updated", generate.call_args.kwargs["system_prompt"])
        self.assertEqual(response.context["preview_result"]["members"][0]["national_id"], "00123")
        self.assertEqual(MemberTransaction.objects.count(), 0)

    def test_examples_use_valid_json_in_email_and_attachment_prompts(self):
        profile = AIExtractionProfile.objects.create(name="Examples", task="EMAIL_EXTRACTION")
        response = self.client.post(reverse("tpa:inbound_email_training"), {"action": "example", "profile_id": profile.pk,
            "example-name": "Sample", "example-input_text": "Add member", "example-expected_output": '{"members":[],"policy_number":null}',
            "example-sort_order": "0", "example-is_active": "on"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(profile.examples.count(), 1)
        self.assertIn('"policy_number": null', _profile_prompt(profile))
        self.assertIn('"policy_number": null', _system_prompt(profile))

    def test_transaction_specific_profile_and_common_aliases(self):
        generic = AIExtractionProfile.objects.create(name="Generic", task="EMAIL_EXTRACTION", priority=1)
        specific = AIExtractionProfile.objects.create(name="Deletion", task="EMAIL_EXTRACTION", applicable_transaction_type="MEMBER_DELETE", priority=50)
        self.assertEqual(select_profile("EMAIL_EXTRACTION", product="MEDICAL", transaction_type="MEMBER_DELETE"), specific)
        payload = normalize_ai_payload({"members": [{"national_id": None, "Civil ID": "00123", "DOB": "01/06/1990", "Gender": "F", "Full Name": "Jane Test"}]})
        row = payload["members"][0]
        self.assertEqual((row["national_id"], row["date_of_birth"], row["gender"], row["first_name"]), ("00123", "1990-06-01", "Female", "Jane"))

    def test_email_classification_applies_specialized_prompt_without_hints(self):
        AIExtractionProfile.objects.create(name="Generic", task="EMAIL_EXTRACTION", applicable_product="MEDICAL", priority=1)
        specialized = AIExtractionProfile.objects.create(name="Termination coaching", task="EMAIL_EXTRACTION", applicable_product="MEDICAL",
            applicable_transaction_type="MEMBER_TERMINATE", instructions="Read member and card identifiers.", priority=2)
        AIProviderConfig.objects.create(name="Classifier", provider="mock", task_capabilities=["email_extraction"], allow_sensitive_data=True)
        email = InboundEmail.objects.create(provider_message_id="scope-email", sender="s@example.com", recipient="t@example.com", received_at=timezone.now(), body_text="Terminate member on TOOLS-1")
        raw = {"members": [], "transaction_type": "MEMBER_TERMINATE", "classification": "MEMBER_TERMINATE", "confidence": .9}
        with patch("apps.tpa.services.ai_intake.generate_json", side_effect=[(raw, 5), ({**raw, "members": [{"member_id": "TPA-2026-000001"}]}, 5)]) as generate:
            payload, _, selected, _ = extract_email_payload(email, self.admin)
        self.assertEqual(selected.pk, specialized.pk)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(payload["members"][0]["member_id"], "TPA-2026-000001")

    def test_extracted_member_identifier_resolves_existing_enrollment(self):
        from .services.validation import validate_action
        enrollment = self.member()
        tx = self.tx(transaction_type="MEMBER_TERMINATE", remarks="End of employment")
        action = MemberAction.objects.create(transaction=tx, action=tx.transaction_type, corrected_data={"member_id": enrollment.member.tpa_member_id})
        validate_action(action)
        action.refresh_from_db()
        self.assertEqual(action.validation_status, "VALID")
