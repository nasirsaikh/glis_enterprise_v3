from apps.accounts.models import Organization
from datetime import date
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    BenefitPlan, CardDispatch, MemberAction, MemberTransaction, Policy,
    PolicyAccess, Organization, TransactionQuery,
)
from .services.wizard import get_transaction_wizard


class TransactionWizardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("wizard-admin", "wizard@example.com", "test")
        cls.requester = User.objects.create_user("wizard-client", password="test")
        cls.reader = User.objects.create_user("wizard-reader", password="test")
        cls.outsider = User.objects.create_user("wizard-outsider", password="test")
        cls.outsider.user_permissions.add(Permission.objects.get(codename="view_tpa_dashboard"))
        cls.organization = Organization.objects.create(code="WSP", name_en="Wizard organization", organization_type_id="CORPORATE")
        cls.insurer = Organization.objects.create(code="WIN", name_en="Wizard Insurer", organization_type_id="INSURER")
        cls.policy = Policy.objects.create(
            organization=cls.organization, insurance_company=cls.insurer, policy_number="WIZARD-1",
            start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31),
            status=Policy.Status.ACTIVE, allowed_backdating_days=3650, stp_enabled=False,
            initial_enrollment_completed_at=timezone.now(), initial_enrollment_completed_by=cls.admin,
        )
        BenefitPlan.objects.create(policy=cls.policy, code="GOLD", name="Gold", annual_premium="365.000")
        PolicyAccess.objects.create(organization=cls.organization, policy=cls.policy, user=cls.requester,
                                   can_view=True, can_create_endorsement=True)
        PolicyAccess.objects.create(organization=cls.organization, policy=cls.policy, user=cls.reader, can_view=True)

    def setUp(self):
        self.client.force_login(self.admin)

    def tx(self, status=MemberTransaction.Status.DRAFT, **kwargs):
        return MemberTransaction.objects.create(
            organization=self.organization, insurer=self.insurer, policy=self.policy,
            transaction_type=kwargs.pop("transaction_type", MemberTransaction.Type.MEMBER_ADD),
            effective_date=date(2026, 7, 1), requester=self.requester,
            requester_organization=self.organization, status=status, **kwargs,
        )

    def member(self, tx):
        return MemberAction.objects.create(
            transaction=tx, action=tx.transaction_type, row_number=1,
            corrected_data={"employee_id": "W-1", "first_name": "Wizard", "last_name": "Member",
                            "date_of_birth": "1990-01-01", "gender": "Male", "relationship": "PRINCIPAL",
                            "plan_code": "GOLD", "national_id": "W-CID-1"},
        )

    def get(self, tx, step=None, **headers):
        return self.client.get(reverse("tpa:transaction_detail", args=[tx.reference]),
                               {"step": step} if step else {}, **headers)

    def post(self, name, tx, data=None, *args, htmx=True):
        return self.client.post(reverse(f"tpa:{name}", args=[tx.reference, *args]), data or {},
                                **({"HTTP_HX_REQUEST": "true"} if htmx else {}))

    def assert_step(self, response, step):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-current-step="{step}"')
        self.assertEqual(response.content.count(b'id="transaction-step-container"'), 1)

    def test_status_defaults_and_partial_rendering(self):
        expected = {
            "draft": "intake", "extracting": "intake", "pending_validation": "validation",
            "needs_information": "intake", "validation_failed": "validation",
            "pending_approval": "approval", "approved": "approval", "auto_approved": "approval",
            "sent_to_tpa": "tpa_processing", "tpa_in_progress": "tpa_processing", "tpa_query": "tpa_processing",
            "processing": "tpa_processing", "failed": "tpa_processing", "rejected": "approval",
            "processed": "complete", "completed": "complete", "cancelled": "complete",
        }
        for status, step in expected.items():
            with self.subTest(status=status):
                response = self.get(self.tx(status), HTTP_HX_REQUEST="true")
                self.assert_step(response, step)
                self.assertNotContains(response, "<!doctype html>")
                self.assertIn(f"?step={step}", response["HX-Push-Url"])

    def test_normal_get_renders_shell_and_one_step(self):
        response = self.get(self.tx())
        self.assert_step(response, "intake")
        self.assertContains(response, "<!doctype html>")
        self.assertNotContains(response, 'id="tpa-quality-chart"')
        self.assertNotContains(response, "Complete TPA Processing")
        self.assertContains(response, 'aria-current="step"')

    def test_initial_enrollment_includes_policy_step(self):
        tx = self.tx(transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT)
        self.assert_step(self.get(tx), "policy_setup")
        self.assert_step(self.get(tx, "intake"), "intake")
        self.assertNotContains(self.get(tx, "intake"), "Add Benefit Plan")

    def test_card_dispatch_is_conditional(self):
        self.assertNotContains(self.get(self.tx()), "Card Dispatch")
        tx = self.tx(MemberTransaction.Status.CARD_DISPATCH, physical_card_required=True)
        self.assert_step(self.get(tx), "card_dispatch")
        self.assertContains(self.get(tx), "Save Dispatch")
        tx = self.tx(transaction_type=MemberTransaction.Type.MEMBER_DELETE, physical_card_required=True)
        self.assertNotContains(self.get(tx), "Card Dispatch")

    def test_future_step_is_gated_in_full_and_htmx_requests(self):
        tx = self.tx()
        response = self.get(tx, "complete")
        self.assertRedirects(response, reverse("portal:ticket_detail", args=[tx.ticket.reference]) + "?step=intake")
        response = self.get(tx, "approval", HTTP_HX_REQUEST="true")
        self.assert_step(response, "intake")
        self.assertIn("?step=intake", response["HX-Push-Url"])
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.DRAFT)

    def test_unknown_or_omitted_step_returns_controlled_error(self):
        tx = self.tx()
        self.assertEqual(self.get(tx, "unknown").status_code, 404)
        response = self.get(tx, "card_dispatch", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["HX-Retarget"], "#transaction-request-error")

    def test_history_restore_returns_full_page(self):
        response = self.get(self.tx("pending_validation"), "validation", HTTP_HX_REQUEST="true",
                            HTTP_HX_HISTORY_RESTORE_REQUEST="true")
        self.assertContains(response, "<!doctype html>")
        self.assert_step(response, "validation")
        self.assertIn("HX-Request", response["Vary"])

    def test_completed_steps_are_read_only_and_navigation_does_not_mutate(self):
        tx = self.tx("completed", physical_card_required=True)
        self.client.force_login(self.requester)
        for step in ["intake", "validation", "approval", "tpa_processing", "card_dispatch", "complete"]:
            with self.subTest(step=step):
                response = self.get(tx, step, HTTP_HX_REQUEST="true")
                self.assert_step(response, step)
                self.assertNotContains(response, 'hx-post=')
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.COMPLETED)

    def test_other_policy_cannot_be_accessed(self):
        tx = self.tx()
        self.client.force_login(self.outsider)
        self.assertEqual(self.get(tx).status_code, 404)

    def test_approval_and_processing_authority_remain_required(self):
        tx = self.tx("pending_approval")
        self.client.force_login(self.requester)
        self.assertNotContains(self.get(tx), 'hx-post="' + reverse("tpa:transaction_approve", args=[tx.reference]))
        self.post("transaction_approve", tx)
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.PENDING_APPROVAL)
        tx.status = tx.Status.SENT_TO_TPA
        tx.save(update_fields=["status"])
        self.post("transaction_tpa_start", tx)
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.SENT_TO_TPA)

    def test_read_only_intake_action_shows_inline_permission_error(self):
        tx = self.tx()
        self.client.force_login(self.reader)
        response = self.post("transaction_add_member", tx)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["HX-Retarget"], "#transaction-request-error")
        self.assertContains(response, "read-only", status_code=403)
        self.assertFalse(tx.member_actions.exists())

    def test_invalid_manual_member_preserves_fields_and_modal(self):
        tx = self.tx()
        response = self.post("transaction_add_member", tx, {"first_name": "Keep Me"})
        self.assert_step(response, "intake")
        self.assertContains(response, 'data-reopen-modal="manual-member"')
        self.assertContains(response, "Keep Me")
        self.assertContains(response, "This field is required")
        self.assertFalse(response.has_header("HX-Refresh"))

    def test_modal_member_form_includes_working_csrf_token(self):
        tx = self.tx()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.get(reverse("tpa:transaction_detail", args=[tx.reference]))
        html = response.content.decode()
        modal_form = html.split('<form id="manual-member-form"', 1)[1].split('</form>', 1)[0]
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', modal_form)
        self.assertIsNotNone(token)
        response = client.post(reverse("tpa:transaction_add_member", args=[tx.reference]),
                               {"csrfmiddlewaretoken": token.group(1)}, HTTP_HX_REQUEST="true")
        self.assert_step(response, "intake")

    def test_invalid_upload_and_plan_display_bound_errors(self):
        tx = self.tx()
        response = self.post("transaction_upload_sources", tx, {
            "source_files": SimpleUploadedFile("bad.exe", b"bad")
        })
        self.assert_step(response, "intake")
        self.assertContains(response, "Unsupported source file")
        tx = self.tx(transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT)
        response = self.post("policy_plan_add", tx, {"code": "GOLD", "name": "Duplicate", "annual_premium": "1"})
        self.assert_step(response, "policy_setup")
        self.assertContains(response, "already exists")

    def test_invalid_row_correction_preserves_values_and_modal(self):
        tx = self.tx()
        action = self.member(tx)
        response = self.post("transaction_edit_member", tx, {"first_name": "Corrected Name"}, action.pk)
        self.assert_step(response, "intake")
        self.assertContains(response, f'data-reopen-modal="edit-member-{action.pk}"')
        self.assertContains(response, "Corrected Name")
        action.refresh_from_db()
        self.assertEqual(action.corrected_data["first_name"], "Wizard")

    def test_submit_validation_approve_start_and_complete_use_fragments(self):
        tx = self.tx()
        action = self.member(tx)
        self.assert_step(self.post("transaction_submit", tx), "validation")
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.PENDING_APPROVAL)
        self.assert_step(self.get(tx, "validation", HTTP_HX_REQUEST="true"), "validation")
        self.assert_step(self.post("transaction_approve", tx), "tpa_processing")
        self.assert_step(self.post("transaction_tpa_start", tx), "tpa_processing")
        action.refresh_from_db()
        response = self.post("transaction_tpa_action", tx, {
            "card_number": "W-CARD", "effective_date": "2026-07-01", "amount": str(action.calculated_premium),
        }, action.pk)
        self.assert_step(response, "tpa_processing")
        response = self.post("transaction_tpa_complete", tx)
        self.assert_step(response, "complete")
        self.assertNotContains(response, 'hx-post=')
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.COMPLETED)

    def test_invalid_processing_row_stays_in_step_with_errors(self):
        tx = self.tx("tpa_in_progress")
        action = self.member(tx)
        response = self.post("transaction_tpa_action", tx, {"card_number": "Retain", "amount": "bad"}, action.pk)
        self.assert_step(response, "tpa_processing")
        self.assertContains(response, "Retain")
        self.assertContains(response, "Enter a number")

    def test_validation_cannot_rewind_tpa_processing(self):
        tx = self.tx("tpa_in_progress")
        response = self.post("transaction_validate", tx)
        self.assertEqual(response.status_code, 403)
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.TPA_IN_PROGRESS)

    def test_rerun_validation_shows_results_in_validation_step(self):
        tx = self.tx("pending_validation")
        self.member(tx)
        self.assert_step(self.post("transaction_validate", tx), "validation")
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.PENDING_APPROVAL)

    def test_rejection_requires_reason_then_shows_closed_approval(self):
        tx = self.tx("pending_approval")
        response = self.post("transaction_reject", tx)
        self.assert_step(response, "approval")
        self.assertContains(response, "This field is required")
        response = self.post("transaction_reject", tx, {"reason": "Outside coverage"})
        self.assert_step(response, "approval")
        self.assertContains(response, "Outside coverage")
        self.assertNotContains(response, 'hx-post=')

    def test_query_reply_resolve_stays_on_processing_step(self):
        tx = self.tx("tpa_in_progress")
        response = self.post("transaction_raise_query", tx, {
            "wizard_step": "tpa_processing", "subject": "Confirm date", "message": "Please confirm",
            "purpose": "TPA", "audience": "CLIENT_VISIBLE",
        })
        self.assert_step(response, "tpa_processing")
        query = tx.queries.get()
        self.client.force_login(self.requester)
        response = self.post("transaction_query_message", tx, {
            "wizard_step": "tpa_processing", f"query-{query.pk}-message": "Confirmed",
            f"query-{query.pk}-audience": "CLIENT_VISIBLE",
        }, query.pk)
        self.assert_step(response, "tpa_processing")
        self.assertContains(response, "Confirmed")
        self.client.force_login(self.admin)
        response = self.post("transaction_resolve_query", tx, {"wizard_step": "tpa_processing"}, query.pk)
        self.assert_step(response, "tpa_processing")
        query.refresh_from_db()
        self.assertEqual(query.status, TransactionQuery.Status.RESOLVED)

    def test_approval_query_marker_respects_thread_visibility(self):
        tx = self.tx("pending_approval")
        response = self.post("transaction_raise_query", tx, {
            "wizard_step": "approval", "subject": "Internal review", "message": "Confirm exception",
            "purpose": "APPROVAL", "audience": "INSURER_TPA_INTERNAL",
        })
        self.assert_step(response, "approval")
        approval = next(step for step in get_transaction_wizard(tx, self.admin)["workflow_steps"]
                        if step["key"] == "approval")
        self.assertTrue(approval["has_query"])
        approval = next(step for step in get_transaction_wizard(tx, self.requester)["workflow_steps"]
                        if step["key"] == "approval")
        self.assertFalse(approval["has_query"])

    def test_card_dispatch_completion_and_invalid_form(self):
        tx = self.tx("tpa_in_progress", physical_card_required=True)
        action = self.member(tx)
        action.validation_status = MemberAction.Result.VALID
        action.card_number = "PHYSICAL-1"
        action.tpa_effective_date = tx.effective_date
        action.tpa_premium_amount = 0
        action.save()
        self.assert_step(self.post("transaction_tpa_complete", tx), "card_dispatch")
        response = self.post("transaction_card_dispatch", tx)
        self.assert_step(response, "card_dispatch")
        self.assertContains(response, "This field is required")
        response = self.post("transaction_card_dispatch", tx, {
            "method": CardDispatch.Method.CLIENT_COLLECTION, "status": CardDispatch.Status.COLLECTED,
            "recipient_name": "HR Office",
        })
        self.assert_step(response, "complete")
        tx.refresh_from_db()
        self.assertEqual(tx.status, tx.Status.COMPLETED)

    def test_normal_post_redirects_to_selected_step(self):
        tx = self.tx()
        self.member(tx)
        response = self.post("transaction_submit", tx, htmx=False)
        self.assertRedirects(response, reverse("portal:ticket_detail", args=[tx.ticket.reference]) + "?step=validation")

    def test_enrollment_creation_has_three_steps_and_htmx_errors(self):
        url = reverse("tpa:policy_enrollment_create")
        response = self.client.get(url)
        self.assertContains(response, 'data-transaction-wizard')
        self.assertEqual(response.content.count(b'data-wizard-step='), 3)
        response = self.client.post(url, {"policy_number": "WIZARD-1"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "already exists")

    def test_previous_next_linking_does_not_call_workflow_services(self):
        tx = self.tx("pending_approval")
        with patch("apps.tpa.views.run_validation") as validation, patch("apps.tpa.views.approve_transaction") as approve:
            response = self.get(tx, "validation", HTTP_HX_REQUEST="true")
        self.assert_step(response, "validation")
        self.assertContains(response, '?step=approval')
        validation.assert_not_called()
        approve.assert_not_called()
        wizard = get_transaction_wizard(tx, self.admin, "validation")
        self.assertEqual(wizard["previous_step"]["key"], "intake")
        self.assertEqual(wizard["next_step"]["key"], "approval")
