import base64
import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import TicketAttachment
from apps.tpa.forms import MemberRowForm
from apps.tpa.models import (
    BenefitPlan,
    CardDispatch,
    InboundEmail,
    Member,
    MemberAction,
    MemberPolicyEnrollment,
    MemberTransaction,
    Policy,
    PolicyAccess,
    SourceDocument,
    TPAEmailAuthority,
    TPAMailboxSyncState,
    TPAOrganization,
    TransactionQuery,
)
from apps.tpa.services.access import (
    can_view_query_attachment,
    can_view_query_message,
    can_view_transaction_query,
    visible_shared_internal_messages,
)
from apps.tpa.services.ai_intake import process_inbound_email
from apps.tpa.services.authority import resolve_email_authority, sender_is_authorized
from apps.tpa.services.mailbox import _graph_get, poll_office365_graph
from apps.tpa.services.member_selection import resolve_card_numbers
from apps.tpa.services.ticketing import create_ticket_for_transaction
from apps.tpa.services.validation import validate_action
from apps.tpa.services.workflow import (
    approve_transaction,
    complete_tpa_transaction,
    raise_transaction_query,
    run_validation,
    share_query_message_with_client,
    start_tpa_processing,
    update_card_dispatch,
    update_tpa_action,
)


@override_settings(
    TPA_MAIL_PROVIDER="office365_graph",
    TPA_MAIL_ENABLED=True,
    TPA_MAIL_AUTO_PROCESS_AI=False,
    TPA_MAIL_MAX_MESSAGES_PER_RUN=20,
    TPA_O365_TENANT_ID="tenant-test",
    TPA_O365_CLIENT_ID="client-test",
    TPA_O365_CLIENT_SECRET="secret-test",
    TPA_O365_MAILBOX="tpa@example.com",
    TPA_O365_FOLDER="Inbox",
)
class TPAAutomationTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        User = get_user_model()
        self.requester = User.objects.create_user(
            username="requester",
            email="requester@example.com",
            password="x",
        )
        self.internal = User.objects.create_superuser(
            username="tpa-admin",
            email="tpa-admin@example.com",
            password="x",
        )
        self.sponsor = TPAOrganization.objects.create(
            code="AUTO-SP",
            name_en="Automation Sponsor",
            organization_type=TPAOrganization.Type.CORPORATE,
        )
        self.insurer = TPAOrganization.objects.create(
            code="AUTO-IN",
            name_en="Automation Insurer",
            organization_type=TPAOrganization.Type.INSURER,
        )
        self.tpa = TPAOrganization.objects.create(
            code="AUTO-TPA",
            name_en="Automation TPA",
            organization_type=TPAOrganization.Type.TPA,
        )
        self.policy = Policy.objects.create(
            sponsor=self.sponsor,
            insurance_company=self.insurer,
            tpa_organization=self.tpa,
            policy_number="AUTO-POL-1",
            start_date=date(2026, 1, 1),
            expiry_date=date(2026, 12, 31),
            status=Policy.Status.ACTIVE,
            allowed_backdating_days=3650,
            physical_card_required=False,
            initial_enrollment_completed_at=timezone.now(),
            initial_enrollment_completed_by=self.internal,
        )
        self.plan = BenefitPlan.objects.create(
            policy=self.policy,
            code="GOLD",
            name="Gold",
            annual_premium=Decimal("365.000"),
            premium_configuration={"method": "PRORATA", "denominator": 365},
        )
        PolicyAccess.objects.create(
            organization=self.sponsor,
            policy=self.policy,
            user=self.requester,
            can_view=True,
            can_create_endorsement=True,
            active=True,
        )

    def _transaction(self, tx_type=MemberTransaction.Type.MEMBER_ADD, status=MemberTransaction.Status.DRAFT, **kwargs):
        return MemberTransaction.objects.create(
            sponsor=self.sponsor,
            insurer=self.insurer,
            policy=self.policy,
            transaction_type=tx_type,
            effective_date=kwargs.pop("effective_date", date(2026, 7, 1)),
            requester=self.requester,
            requester_organization=self.sponsor,
            status=status,
            **kwargs,
        )

    def _active_enrollment(self, suffix="1"):
        member = Member.objects.create(
            sponsor=self.sponsor,
            employee_id=f"EMP-{suffix}",
            first_name="Existing",
            last_name=f"Member {suffix}",
            date_of_birth=date(1990, 1, 1),
            gender="Male",
            relationship=Member.Relationship.PRINCIPAL,
            national_id=f"CID-{suffix}",
            passport_number=f"PASS-{suffix}",
            status=Member.Status.ACTIVE,
        )
        enrollment = MemberPolicyEnrollment.objects.create(
            member=member,
            policy=self.policy,
            benefit_plan=self.plan,
            coverage_start_date=date(2026, 1, 1),
            coverage_end_date=date(2026, 12, 31),
            enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
            card_number=f"CARD-{suffix}",
            premium_amount=Decimal("365.000"),
        )
        return member, enrollment

    @patch("apps.tpa.services.mailbox.process_inbound_email")
    @patch("apps.tpa.services.mailbox._graph_attachment_payload")
    @patch("apps.tpa.services.mailbox._graph_get")
    @patch("apps.tpa.services.mailbox._graph_token", return_value="token")
    def test_graph_message_is_idempotent_and_stores_multiple_attachments(
        self,
        _token,
        graph_get,
        attachment_payload,
        process_inbound,
    ):
        message = {
            "id": "graph-message-1",
            "internetMessageId": "<graph-message-1@example.com>",
            "conversationId": "conversation-1",
            "subject": "Add employees",
            "receivedDateTime": "2026-09-29T08:00:00Z",
            "from": {"emailAddress": {"name": "HR", "address": "hr@example.com"}},
            "toRecipients": [{"emailAddress": {"name": "TPA", "address": "tpa@example.com"}}],
            "ccRecipients": [],
            "body": {"contentType": "text", "content": "Add the attached employees."},
            "hasAttachments": True,
        }
        graph_get.return_value = {
            "value": [message],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-token-1",
        }
        attachment_payload.return_value = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "att-1",
                "name": "members.csv",
                "contentType": "text/csv",
                "contentBytes": base64.b64encode(b"employee_id\nE-1\n").decode(),
                "size": 16,
            },
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "id": "att-2",
                "name": "id.jpg",
                "contentType": "image/jpeg",
                "contentBytes": base64.b64encode(b"jpeg-bytes").decode(),
                "size": 10,
            },
        ]

        first = poll_office365_graph(
            actor=self.internal,
            process_ai=False,
        )
        second = poll_office365_graph(
            actor=self.internal,
            process_ai=False,
        )

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(InboundEmail.objects.count(), 1)
        email = InboundEmail.objects.get()
        self.assertEqual(email.graph_message_id, "graph-message-1")
        self.assertEqual(email.internet_message_id, "<graph-message-1@example.com>")
        self.assertEqual(email.conversation_id, "conversation-1")
        self.assertEqual(email.attachments.count(), 2)
        self.assertEqual(len(email.attachment_metadata), 2)
        state = TPAMailboxSyncState.objects.get()
        self.assertIn("delta-token-1", state.delta_link)
        process_inbound.assert_not_called()

    @patch("apps.tpa.services.mailbox.time.sleep")
    @patch("apps.tpa.services.mailbox.requests.get")
    def test_graph_get_retries_transient_service_failure(self, get, _sleep):
        unavailable = MagicMock()
        unavailable.status_code = 503
        unavailable.headers = {}
        success = MagicMock()
        success.status_code = 200
        success.headers = {}
        success.raise_for_status.return_value = None
        success.json.return_value = {"value": []}
        get.side_effect = [unavailable, success]

        payload = _graph_get(
            "https://graph.microsoft.com/v1.0/test",
            "token",
            timeout=1,
        )

        self.assertEqual(payload, {"value": []})
        self.assertEqual(get.call_count, 2)

    @patch("apps.tpa.services.ai_intake.extract_email_payload")
    def test_email_classification_without_confidence_goes_to_review(self, extract_payload):
        provider = MagicMock()
        provider.name = "Test Provider"
        provider.provider = "mock"
        provider.model_name = "test-model"
        extract_payload.return_value = (
            {
                "is_endorsement_request": True,
                "classification": "MEMBER_ADD",
                "transaction_type": "MEMBER_ADD",
                "confidence": None,
                "policy_number": self.policy.policy_number,
                "members": [],
            },
            provider,
            None,
            {"raw": "response"},
        )
        email = InboundEmail.objects.create(
            provider="office365_graph",
            provider_message_id="missing-confidence",
            sender="hr@example.com",
            recipient="tpa@example.com",
            mailbox="tpa@example.com",
            received_at=timezone.now(),
        )

        result = process_inbound_email(email, self.internal)

        self.assertIsNone(result)
        email.refresh_from_db()
        self.assertEqual(email.processing_state, InboundEmail.State.REVIEW)
        self.assertIn("incomplete", email.processing_error.lower())
        self.assertEqual(email.ai_provider_name, "Test Provider")
        self.assertEqual(email.ai_model_name, "test-model")
        self.assertIsNone(email.transaction_id)

    @patch("apps.tpa.services.ai_intake.extract_email_payload")
    def test_non_endorsement_email_is_ignored_without_transaction(self, extract_payload):
        provider = MagicMock(name="provider")
        provider.name = "Test Provider"
        provider.provider = "mock"
        provider.model_name = "test-model"
        extract_payload.return_value = (
            {
                "is_endorsement_request": False,
                "classification": "NOT_ENDORSEMENT",
                "confidence": 0.99,
                "members": [],
            },
            provider,
            None,
            {"classification": "NOT_ENDORSEMENT"},
        )
        email = InboundEmail.objects.create(
            provider="office365_graph",
            provider_message_id="not-endorsement",
            sender="newsletter@example.com",
            recipient="tpa@example.com",
            mailbox="tpa@example.com",
            received_at=timezone.now(),
        )

        result = process_inbound_email(email, self.internal)

        self.assertIsNone(result)
        email.refresh_from_db()
        self.assertEqual(email.processing_state, InboundEmail.State.IGNORED)
        self.assertIsNone(email.transaction_id)

    @patch("apps.tpa.services.ai_intake.extract_email_payload")
    def test_missing_policy_email_goes_to_review(self, extract_payload):
        provider = MagicMock(name="provider")
        provider.name = "Test Provider"
        provider.provider = "mock"
        provider.model_name = "test-model"
        extract_payload.return_value = (
            {
                "is_endorsement_request": True,
                "classification": "MEMBER_ADD",
                "transaction_type": "MEMBER_ADD",
                "confidence": 0.99,
                "policy_number": None,
                "members": [],
            },
            provider,
            None,
            {"classification": "MEMBER_ADD"},
        )
        email = InboundEmail.objects.create(
            provider="office365_graph",
            provider_message_id="missing-policy",
            sender="hr@example.com",
            recipient="tpa@example.com",
            mailbox="tpa@example.com",
            received_at=timezone.now(),
        )

        result = process_inbound_email(email, self.internal)

        self.assertIsNone(result)
        email.refresh_from_db()
        self.assertEqual(email.processing_state, InboundEmail.State.REVIEW)
        self.assertEqual(email.processing_stage, "POLICY_MATCH")
        self.assertIsNone(email.transaction_id)

    @patch("apps.tpa.services.ai_intake.extract_email_payload")
    def test_unauthorized_sender_is_blocked_before_transaction_creation(self, extract_payload):
        provider = MagicMock(name="provider")
        provider.name = "Test Provider"
        provider.provider = "mock"
        provider.model_name = "test-model"
        extract_payload.return_value = (
            {
                "is_endorsement_request": True,
                "classification": "MEMBER_ADD",
                "transaction_type": "MEMBER_ADD",
                "confidence": 0.99,
                "policy_number": self.policy.policy_number,
                "effective_date": "2026-09-29",
                "members": [],
            },
            provider,
            None,
            {"classification": "MEMBER_ADD"},
        )
        email = InboundEmail.objects.create(
            provider="office365_graph",
            provider_message_id="unauthorized",
            sender="unknown@example.com",
            recipient="tpa@example.com",
            mailbox="tpa@example.com",
            received_at=timezone.now(),
        )

        result = process_inbound_email(email, self.internal)

        self.assertIsNone(result)
        email.refresh_from_db()
        self.assertEqual(email.processing_state, InboundEmail.State.UNAUTHORIZED)
        self.assertEqual(email.processing_stage, "SENDER_AUTHORITY")
        self.assertIsNone(email.transaction_id)

    def test_zero_member_transaction_cannot_submit(self):
        tx = self._transaction()
        self.client.force_login(self.requester)

        response = self.client.post(
            reverse("tpa:transaction_submit", args=[tx.reference])
        )

        self.assertEqual(response.status_code, 302)
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.DRAFT)
        self.assertFalse(tx.member_actions.exists())

    def test_bulk_card_resolution_separates_matches_duplicates_missing_and_inactive(self):
        _, active = self._active_enrollment("BULK-ACTIVE")
        _, inactive = self._active_enrollment("BULK-INACTIVE")
        inactive.enrollment_status = MemberPolicyEnrollment.Status.TERMINATED
        inactive.save(update_fields=["enrollment_status", "updated_at"])
        tx = self._transaction(tx_type=MemberTransaction.Type.MEMBER_DELETE)

        result = resolve_card_numbers(
            tx,
            f"{active.card_number}, {active.card_number}; MISSING-CARD {inactive.card_number}",
        )

        self.assertEqual([item.pk for item in result["matched"]], [active.pk])
        self.assertEqual(result["duplicates"], [active.card_number])
        self.assertEqual(result["not_found"], ["MISSING-CARD"])
        self.assertEqual(result["inactive"], [inactive.card_number])

    def test_sender_authority_is_policy_and_transaction_specific(self):
        authority = TPAEmailAuthority.objects.create(
            email_address="hr@example.com",
            user=self.requester,
            organization=self.sponsor,
            policy=self.policy,
            permitted_transaction_types=[MemberTransaction.Type.MEMBER_ADD],
            active=True,
        )
        resolved = resolve_email_authority(
            "HR@example.com",
            self.policy,
            MemberTransaction.Type.MEMBER_ADD,
            as_of=date(2026, 9, 29),
        )
        self.assertEqual(resolved.pk, authority.pk)
        self.assertIsNone(
            resolve_email_authority(
                "hr@example.com",
                self.policy,
                MemberTransaction.Type.MEMBER_DELETE,
                as_of=date(2026, 9, 29),
            )
        )

        email = InboundEmail.objects.create(
            provider="office365_graph",
            provider_message_id="authority-test",
            sender="hr@example.com",
            recipient="tpa@example.com",
            mailbox="tpa@example.com",
            received_at=timezone.now(),
        )
        allowed, _, _ = sender_is_authorized(
            email,
            self.policy,
            MemberTransaction.Type.MEMBER_ADD,
        )
        blocked, _, _ = sender_is_authorized(
            email,
            self.policy,
            MemberTransaction.Type.MEMBER_DELETE,
        )
        self.assertTrue(allowed)
        self.assertFalse(blocked)

    def test_organization_wide_authority_supports_insurer_and_tpa(self):
        insurer_authority = TPAEmailAuthority.objects.create(
            email_address="insurer@example.com",
            organization=self.insurer,
            policy=None,
            permitted_transaction_types=[MemberTransaction.Type.MEMBER_ADD],
            active=True,
        )
        tpa_authority = TPAEmailAuthority.objects.create(
            email_address="processor@example.com",
            organization=self.tpa,
            policy=None,
            permitted_transaction_types=[MemberTransaction.Type.MEMBER_DELETE],
            active=True,
        )

        self.assertEqual(
            resolve_email_authority(
                "insurer@example.com",
                self.policy,
                MemberTransaction.Type.MEMBER_ADD,
                as_of=date(2026, 9, 29),
            ).pk,
            insurer_authority.pk,
        )
        self.assertEqual(
            resolve_email_authority(
                "processor@example.com",
                self.policy,
                MemberTransaction.Type.MEMBER_DELETE,
                as_of=date(2026, 9, 29),
            ).pk,
            tpa_authority.pk,
        )

    def test_selected_participant_query_is_not_visible_to_unselected_requester(self):
        User = get_user_model()
        selected = User.objects.create_user(
            username="selected-reviewer",
            email="selected@example.com",
            password="x",
        )
        PolicyAccess.objects.create(
            organization=self.insurer,
            policy=self.policy,
            user=selected,
            can_view=True,
            active=True,
        )
        tx = self._transaction(status=MemberTransaction.Status.TPA_IN_PROGRESS)
        query = raise_transaction_query(
            tx,
            self.internal,
            "Restricted review",
            "Selected participant only.",
            purpose=TransactionQuery.Purpose.TPA,
            audience=TransactionQuery.Audience.SELECTED_PARTICIPANTS,
            selected_participant_ids=[selected.pk],
        )

        self.assertFalse(can_view_transaction_query(self.requester, query))
        self.assertTrue(can_view_transaction_query(selected, query))
        self.assertFalse(can_view_query_message(self.requester, query.messages.get()))
        self.assertTrue(can_view_query_message(selected, query.messages.get()))

    def test_read_only_policy_user_cannot_mutate_intake_endpoints(self):
        User = get_user_model()
        readonly = User.objects.create_user(
            username="readonly",
            email="readonly@example.com",
            password="x",
        )
        PolicyAccess.objects.create(
            organization=self.sponsor,
            policy=self.policy,
            user=readonly,
            can_view=True,
            can_create_endorsement=False,
            active=True,
        )
        tx = self._transaction()
        failed_source = SourceDocument.objects.create(
            transaction=tx,
            original_name="failed.pdf",
            processing_state=SourceDocument.State.REVIEW,
            processing_error="OCR provider unavailable.",
            uploaded_by=self.requester,
        )
        self.client.force_login(readonly)

        add_response = self.client.post(
            reverse("tpa:transaction_add_member", args=[tx.reference]),
            data={
                "employee_id": "READONLY-1",
                "first_name": "Read",
                "last_name": "Only",
                "date_of_birth": "1990-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "principal_reference": "",
                "plan_code": "GOLD",
                "national_id": "READONLY-CID",
                "passport_number": "",
            },
        )
        delete_response = self.client.post(
            reverse(
                "tpa:transaction_delete_source",
                args=[tx.reference, failed_source.pk],
            )
        )

        self.assertEqual(add_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        self.assertEqual(tx.member_actions.count(), 0)
        self.assertTrue(SourceDocument.objects.filter(pk=failed_source.pk).exists())

    def test_manual_member_form_rejects_active_and_transaction_duplicates(self):
        self._active_enrollment("ACTIVE")
        tx = self._transaction()
        MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            row_number=1,
            corrected_data={
                "employee_id": "PENDING-1",
                "first_name": "Pending",
                "last_name": "Member",
                "date_of_birth": "1990-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "plan_code": "GOLD",
                "national_id": "PENDING-CID",
            },
        )

        active_form = MemberRowForm(
            data={
                "employee_id": "EMP-ACTIVE",
                "first_name": "Duplicate",
                "last_name": "Active",
                "date_of_birth": "1990-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "principal_reference": "",
                "plan_code": "GOLD",
                "national_id": "NEW-CID",
                "passport_number": "",
            },
            transaction=tx,
        )
        pending_form = MemberRowForm(
            data={
                "employee_id": "PENDING-1",
                "first_name": "Duplicate",
                "last_name": "Pending",
                "date_of_birth": "1990-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "principal_reference": "",
                "plan_code": "GOLD",
                "national_id": "OTHER-CID",
                "passport_number": "",
            },
            transaction=tx,
        )

        self.assertFalse(active_form.is_valid())
        self.assertIn("employee_id", active_form.errors)
        self.assertFalse(pending_form.is_valid())
        self.assertIn("employee_id", pending_form.errors)

    def test_approval_query_must_be_resolved_before_approval(self):
        tx = self._transaction(status=MemberTransaction.Status.PENDING_APPROVAL)
        query = raise_transaction_query(
            tx,
            self.internal,
            "Clarify member evidence",
            "Please clarify the member evidence before approval.",
            purpose=TransactionQuery.Purpose.APPROVAL,
            audience=TransactionQuery.Audience.CLIENT_VISIBLE,
        )
        self.assertEqual(query.status, TransactionQuery.Status.OPEN)
        with self.assertRaisesRegex(ValueError, "Resolve the open approval query"):
            approve_transaction(tx, self.internal)

    def test_internal_message_sharing_exposes_body_not_internal_attachment_authority(self):
        tx = self._transaction(status=MemberTransaction.Status.TPA_IN_PROGRESS)
        query = raise_transaction_query(
            tx,
            self.internal,
            "Internal review",
            "Internal insurer/TPA assessment.",
            purpose=TransactionQuery.Purpose.TPA,
            audience=TransactionQuery.Audience.INSURER_TPA_INTERNAL,
        )
        message = query.messages.get()

        self.assertFalse(can_view_transaction_query(self.requester, query))
        self.assertFalse(can_view_query_message(self.requester, message))
        self.assertFalse(can_view_query_attachment(self.requester, message))

        share_query_message_with_client(message, self.internal)
        message.refresh_from_db()

        self.assertTrue(can_view_query_message(self.requester, message))
        self.assertFalse(can_view_query_attachment(self.requester, message))
        self.assertEqual(
            list(visible_shared_internal_messages(self.requester, tx).values_list("pk", flat=True)),
            [message.pk],
        )
        self.assertFalse(can_view_transaction_query(self.requester, query))

    def test_full_and_pro_rata_refunds_are_deterministic(self):
        _, enrollment = self._active_enrollment("REFUND")
        full_tx = self._transaction(
            tx_type=MemberTransaction.Type.MEMBER_DELETE,
            refund_basis=MemberTransaction.RefundBasis.FULL,
        )
        full_action = MemberAction.objects.create(
            transaction=full_tx,
            action=full_tx.transaction_type,
            corrected_data={"card_number": enrollment.card_number},
        )
        validate_action(full_action)
        full_action.refresh_from_db()
        self.assertEqual(full_action.calculated_premium, Decimal("-365.000"))
        self.assertEqual(full_action.calculation_snapshot["method"], "FULL_REFUND")

        prorata_tx = self._transaction(
            tx_type=MemberTransaction.Type.MEMBER_DELETE,
            refund_basis=MemberTransaction.RefundBasis.PRO_RATA,
        )
        prorata_action = MemberAction.objects.create(
            transaction=prorata_tx,
            action=prorata_tx.transaction_type,
            corrected_data={"card_number": enrollment.card_number},
        )
        validate_action(prorata_action)
        prorata_action.refresh_from_db()
        self.assertLess(prorata_action.calculated_premium, Decimal("0"))
        self.assertEqual(
            prorata_action.calculation_snapshot["method"],
            "PRO_RATA_REFUND",
        )

    def test_suspend_then_reactivate_member(self):
        member, enrollment = self._active_enrollment("SUSPEND")
        suspend = self._transaction(
            tx_type=MemberTransaction.Type.MEMBER_SUSPEND,
            status=MemberTransaction.Status.PENDING_VALIDATION,
            expected_reactivation_date=date(2026, 7, 31),
            remarks="Temporary leave",
        )
        suspend_action = MemberAction.objects.create(
            transaction=suspend,
            action=suspend.transaction_type,
            corrected_data={"card_number": enrollment.card_number},
        )
        run_validation(suspend, self.internal)
        approve_transaction(suspend, self.internal)
        start_tpa_processing(suspend, self.internal)
        suspend_action.refresh_from_db()
        update_tpa_action(
            suspend_action,
            self.internal,
            effective_date=date(2026, 7, 1),
            amount=Decimal("0.000"),
        )
        complete_tpa_transaction(suspend, self.internal)
        enrollment.refresh_from_db()
        member.refresh_from_db()
        self.assertEqual(enrollment.enrollment_status, MemberPolicyEnrollment.Status.SUSPENDED)
        self.assertEqual(member.status, Member.Status.SUSPENDED)
        self.assertEqual(enrollment.suspension_reason, "Temporary leave")
        self.assertEqual(enrollment.expected_reactivation_date, date(2026, 7, 31))

        reactivate = self._transaction(
            tx_type=MemberTransaction.Type.MEMBER_REACTIVATE,
            status=MemberTransaction.Status.PENDING_VALIDATION,
            effective_date=date(2026, 8, 1),
        )
        reactivate_action = MemberAction.objects.create(
            transaction=reactivate,
            action=reactivate.transaction_type,
            corrected_data={"card_number": enrollment.card_number},
        )
        run_validation(reactivate, self.internal)
        approve_transaction(reactivate, self.internal)
        start_tpa_processing(reactivate, self.internal)
        reactivate_action.refresh_from_db()
        update_tpa_action(
            reactivate_action,
            self.internal,
            effective_date=date(2026, 8, 1),
            amount=Decimal("0.000"),
        )
        complete_tpa_transaction(reactivate, self.internal)
        enrollment.refresh_from_db()
        member.refresh_from_db()
        self.assertEqual(enrollment.enrollment_status, MemberPolicyEnrollment.Status.ACTIVE)
        self.assertEqual(member.status, Member.Status.ACTIVE)
        self.assertEqual(enrollment.reactivation_date, date(2026, 8, 1))

    def test_card_dispatch_proof_is_not_downloadable_by_client(self):
        tx = self._transaction(
            status=MemberTransaction.Status.CARD_DISPATCH,
            physical_card_required=True,
        )
        ticket = create_ticket_for_transaction(tx, actor=self.internal)
        proof = TicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=self.internal,
            file=SimpleUploadedFile(
                "delivery-proof.pdf",
                b"%PDF-1.4 test proof",
                content_type="application/pdf",
            ),
            original_name="delivery-proof.pdf",
            content_type="application/pdf",
            size=19,
            is_restricted=True,
            scan_status="clean",
            source_field="tpa_card_dispatch",
        )
        CardDispatch.objects.create(
            transaction=tx,
            status=CardDispatch.Status.DELIVERED,
            proof_attachment=proof,
            recorded_by=self.internal,
        )

        self.client.force_login(self.requester)
        blocked = self.client.get(
            reverse("tpa:transaction_card_dispatch_proof", args=[tx.reference])
        )
        self.assertEqual(blocked.status_code, 403)

        self.client.force_login(self.internal)
        allowed = self.client.get(
            reverse("tpa:transaction_card_dispatch_proof", args=[tx.reference])
        )
        self.assertEqual(allowed.status_code, 200)

    def test_physical_card_dispatch_blocks_completion_until_delivery(self):
        self.policy.physical_card_required = True
        self.policy.save(update_fields=["physical_card_required", "updated_at"])
        tx = self._transaction(
            status=MemberTransaction.Status.PENDING_VALIDATION,
            physical_card_required=True,
        )
        action = MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            corrected_data={
                "employee_id": "CARD-EMP-1",
                "first_name": "Card",
                "last_name": "Member",
                "date_of_birth": "1992-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "plan_code": "GOLD",
                "national_id": "CARD-CID-1",
            },
        )
        run_validation(tx, self.internal)
        approve_transaction(tx, self.internal)
        start_tpa_processing(tx, self.internal)
        action.refresh_from_db()
        update_tpa_action(
            action,
            self.internal,
            card_number="PHYSICAL-CARD-1",
            effective_date=date(2026, 7, 1),
            amount=action.calculated_premium,
        )
        complete_tpa_transaction(tx, self.internal)
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.CARD_DISPATCH)

        update_card_dispatch(
            tx,
            self.internal,
            method=CardDispatch.Method.COURIER,
            status=CardDispatch.Status.DELIVERED,
            courier_company="Test Courier",
            tracking_number="AWB-1",
            delivered_or_collected_at=timezone.now(),
        )
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.COMPLETED)
        self.assertTrue(
            MemberPolicyEnrollment.objects.filter(
                policy=self.policy,
                card_number="PHYSICAL-CARD-1",
                enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
            ).exists()
        )
