from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.ai.models import AIExtractionProfile, AIProviderConfig
from apps.tickets.models import TicketComment

from .models import (
    BenefitPlan,
    InboundEmail,
    Member,
    MemberAction,
    MemberPolicyEnrollment,
    MemberTransaction,
    Policy,
    PolicyAccess,
    TPAOrganization,
    TransactionQuery,
)
from .forms import MemberRowForm, TransactionForm
from .services.access import can_access_tpa, can_create_tpa_transaction
from .services.ai_intake import process_inbound_email
from .services.document_intake import create_source_documents, process_source_bundle
from .services.pricing import calculate_member_premium
from .services.workflow import (
    approve_transaction,
    complete_tpa_transaction,
    post_query_message,
    raise_tpa_query,
    resolve_tpa_query,
    run_validation,
    start_tpa_processing,
    update_tpa_action,
)


class TPACoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tpa",
            password="x",
        )
        self.sponsor = TPAOrganization.objects.create(
            code="SP1",
            name_en="Sponsor",
            organization_type="CORPORATE",
        )
        self.insurer = TPAOrganization.objects.create(
            code="IN1",
            name_en="Insurer",
            organization_type=TPAOrganization.Type.INSURER,
        )
        self.tpa = TPAOrganization.objects.create(
            code="TPA1",
            name_en="Test TPA",
            organization_type=TPAOrganization.Type.TPA,
        )
        self.policy = Policy.objects.create(
            sponsor=self.sponsor,
            insurance_company=self.insurer,
            tpa_organization=self.tpa,
            policy_number="POL-1",
            start_date=date(2026, 1, 1),
            expiry_date=date(2026, 12, 31),
            status=Policy.Status.ACTIVE,
            allowed_backdating_days=3650,
            initial_enrollment_completed_at=timezone.now(),
            initial_enrollment_completed_by=self.user,
        )
        self.plan = BenefitPlan.objects.create(
            policy=self.policy,
            code="GOLD",
            name="Gold",
            annual_premium="365.000",
            premium_configuration={"method": "PRORATA", "denominator": 365},
        )

    def _transaction(self, status=MemberTransaction.Status.DRAFT):
        return MemberTransaction.objects.create(
            sponsor=self.sponsor,
            insurer=self.insurer,
            policy=self.policy,
            transaction_type=MemberTransaction.Type.MEMBER_ADD,
            effective_date=date(2026, 7, 1),
            requester=self.user,
            requester_organization=self.sponsor,
            status=status,
        )

    def test_prorata_is_decimal_and_snapshotted(self):
        amount, snapshot = calculate_member_premium(
            self.policy,
            self.plan,
            date(2026, 7, 1),
        )
        self.assertEqual(str(amount), "184.000")
        self.assertEqual(snapshot["method"], "PRORATA")

    def test_transaction_reference_generated(self):
        tx = self._transaction()
        self.assertTrue(tx.reference.startswith("TPA-END-2026-"))

    def test_user_without_permission_or_policy_access_cannot_enter_tpa(self):
        self.assertFalse(can_access_tpa(self.user))
        self.assertFalse(can_create_tpa_transaction(self.user))

    def test_policy_access_controls_workspace_and_create_visibility(self):
        PolicyAccess.objects.create(
            organization=self.sponsor,
            policy=self.policy,
            user=self.user,
            can_view=True,
            can_create_endorsement=True,
            active=True,
        )
        self.assertTrue(can_access_tpa(self.user))
        self.assertTrue(can_create_tpa_transaction(self.user))

    def test_endorsement_form_excludes_initial_enrollment(self):
        PolicyAccess.objects.create(
            organization=self.sponsor,
            policy=self.policy,
            user=self.user,
            can_view=True,
            can_create_endorsement=True,
            active=True,
        )
        form = TransactionForm(user=self.user)
        values = {value for value, _ in form.fields["transaction_type"].choices}
        self.assertNotIn(MemberTransaction.Type.NEW_POLICY_ENROLLMENT, values)
        self.assertIn(MemberTransaction.Type.MEMBER_ADD, values)
        self.assertIn(self.policy, form.fields["policy"].queryset)

    def test_configure_tpa_ollama_creates_separate_vision_and_text_providers(self):
        call_command(
            "configure_tpa_ollama",
            endpoint="http://127.0.0.1:11434",
            ocr_model="glm-ocr:test",
            text_model="qwen2.5:7b",
            verbosity=0,
        )

        vision = AIProviderConfig.objects.get(name="TPA Ollama Vision OCR")
        text = AIProviderConfig.objects.get(name="TPA Ollama Text Mapping")
        self.assertEqual(vision.provider, AIProviderConfig.Provider.OLLAMA)
        self.assertTrue(vision.supports_vision)
        self.assertIn("document_extraction", vision.task_capabilities)
        self.assertEqual(vision.model_name, "glm-ocr:test")
        self.assertEqual(text.provider, AIProviderConfig.Provider.OLLAMA)
        self.assertFalse(text.supports_vision)
        self.assertIn("member_field_mapping", text.task_capabilities)
        self.assertIn("email_extraction", text.task_capabilities)

    def test_redesigned_dashboard_renders_with_apexcharts_shell(self):
        tx = self._transaction()
        self.client.force_login(self.user)

        response = self.client.get(reverse("tpa:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tpa-status-chart")
        self.assertContains(response, "tpa-source-chart")
        self.assertContains(response, "TPA MEMBER MANAGEMENT")
        self.assertNotContains(response, "Plotly")

    def test_redesigned_transaction_workspace_renders_without_plotly(self):
        tx = self._transaction()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tpa:transaction_detail", args=[tx.reference])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tpa-quality-chart")
        self.assertContains(response, "tpa-error-chart")
        self.assertContains(response, "OLLAMA OCR")
        self.assertNotContains(response, "Plotly.newPlot")

    def test_structured_source_bundle_does_not_require_ai(self):
        tx = self._transaction()
        upload = SimpleUploadedFile(
            "members.csv",
            (
                "employee_id,first_name,last_name,date_of_birth,gender,relationship,plan_code,national_id\n"
                "CSV-100,CSV,Member,1992-04-10,Male,PRINCIPAL,GOLD,CSV-CID-100\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        documents = create_source_documents(tx, [upload], actor=self.user)
        actions = process_source_bundle(tx, documents, actor=self.user)

        tx.refresh_from_db()
        documents[0].refresh_from_db()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].corrected_data["employee_id"], "CSV-100")
        self.assertEqual(documents[0].extraction_method, "STRUCTURED_IMPORT")
        self.assertTrue(documents[0].processed)
        self.assertEqual(documents[0].processing_state, "PROCESSED")
        self.assertEqual(tx.ai_extraction_status, "EXTRACTED")

    def test_validation_with_no_member_rows_requires_information(self):
        tx = self._transaction(status=MemberTransaction.Status.PENDING_VALIDATION)
        run_validation(tx, actor=self.user)
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.NEEDS_INFORMATION)
        self.assertEqual(str(tx.validation_score), "0.00")

    def test_member_add_can_validate_approve_and_process(self):
        tx = self._transaction(status=MemberTransaction.Status.PENDING_VALIDATION)
        action = MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            row_number=1,
            corrected_data={
                "employee_id": "E-100",
                "first_name": "Test",
                "last_name": "Member",
                "date_of_birth": "1990-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "plan_code": "GOLD",
                "national_id": "CID-100",
            },
        )

        run_validation(tx, actor=self.user)
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.PENDING_APPROVAL)
        self.assertEqual(str(tx.validation_score), "100.00")
        self.assertEqual(str(tx.premium_adjustment), "184.000")

        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=["is_superuser", "is_staff"])

        approve_transaction(tx, self.user)
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.SENT_TO_TPA)

        start_tpa_processing(tx, self.user)
        action.refresh_from_db()
        update_tpa_action(
            action,
            self.user,
            card_number="CARD-E-100",
            effective_date=date(2026, 7, 1),
            amount=action.calculated_premium,
        )
        complete_tpa_transaction(tx, self.user)
        tx.refresh_from_db()

        self.assertEqual(tx.status, MemberTransaction.Status.COMPLETED)
        enrollment = MemberPolicyEnrollment.objects.get(
            policy=self.policy,
            member__employee_id="E-100",
            enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
        )
        self.assertEqual(enrollment.card_number, "CARD-E-100")
        self.assertEqual(enrollment.coverage_start_date, date(2026, 7, 1))
        self.assertEqual(str(enrollment.premium_amount), "184.000")
        self.assertEqual(
            enrollment.premium_calculation_basis["tpa_final_amount"],
            "184.000",
        )

    def test_initial_policy_enrollment_activates_policy_only_after_tpa_completion(self):
        policy = Policy.objects.create(
            sponsor=self.sponsor,
            insurance_company=self.insurer,
            tpa_organization=self.tpa,
            policy_number="POL-OPENING-1",
            policy_name="Opening Census Policy",
            start_date=date(2026, 1, 1),
            expiry_date=date(2026, 12, 31),
            status=Policy.Status.DRAFT,
            stp_enabled=False,
            allowed_backdating_days=3650,
        )
        BenefitPlan.objects.create(
            policy=policy,
            code="GOLD",
            name="Gold",
            annual_premium="365.000",
            premium_configuration={"method": "PRORATA", "denominator": 365},
        )
        tx = MemberTransaction.objects.create(
            sponsor=self.sponsor,
            insurer=self.insurer,
            policy=policy,
            transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT,
            effective_date=date(2026, 1, 1),
            requester=self.user,
            requester_organization=self.sponsor,
            status=MemberTransaction.Status.PENDING_VALIDATION,
        )
        action = MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            row_number=1,
            corrected_data={
                "employee_id": "OPEN-EMP-1",
                "first_name": "Opening",
                "last_name": "Member",
                "date_of_birth": "1988-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "plan_code": "GOLD",
                "national_id": "OPEN-CID-1",
            },
        )

        run_validation(tx, actor=self.user)
        tx.refresh_from_db()
        policy.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.PENDING_APPROVAL)
        self.assertEqual(policy.status, Policy.Status.DRAFT)
        self.assertIsNone(policy.initial_enrollment_completed_at)

        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=["is_superuser", "is_staff"])

        approve_transaction(tx, self.user)
        start_tpa_processing(tx, self.user)
        action.refresh_from_db()
        update_tpa_action(
            action,
            self.user,
            card_number="OPEN-CARD-1",
            effective_date=date(2026, 1, 1),
            amount=action.calculated_premium,
        )
        complete_tpa_transaction(tx, self.user)

        tx.refresh_from_db()
        policy.refresh_from_db()
        enrollment = MemberPolicyEnrollment.objects.get(
            policy=policy,
            member__employee_id="OPEN-EMP-1",
        )
        self.assertEqual(tx.status, MemberTransaction.Status.COMPLETED)
        self.assertEqual(policy.status, Policy.Status.ACTIVE)
        self.assertIsNotNone(policy.initial_enrollment_completed_at)
        self.assertEqual(policy.initial_enrollment_completed_by_id, self.user.pk)
        self.assertEqual(enrollment.card_number, "OPEN-CARD-1")

    def test_dependent_manual_form_requires_parent_principal(self):
        tx = self._transaction()
        form = MemberRowForm(
            data={
                "employee_id": "E-200",
                "first_name": "Child",
                "middle_name": "",
                "last_name": "Member",
                "date_of_birth": "2018-01-01",
                "gender": "Female",
                "relationship": "CHILD",
                "principal_reference": "",
                "plan_code": "GOLD",
                "national_id": "CID-200",
                "passport_number": "",
            },
            transaction=tx,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("principal_reference", form.errors)

    def test_same_transaction_principal_is_available_for_manual_dependent(self):
        tx = self._transaction()
        principal_action = MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            row_number=1,
            corrected_data={
                "employee_id": "E-PRINCIPAL",
                "first_name": "Parent",
                "last_name": "Member",
                "date_of_birth": "1985-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "plan_code": "GOLD",
                "national_id": "CID-PARENT",
            },
        )
        form = MemberRowForm(
            data={
                "employee_id": "E-CHILD",
                "first_name": "Child",
                "middle_name": "",
                "last_name": "Member",
                "date_of_birth": "2018-01-01",
                "gender": "Female",
                "relationship": "CHILD",
                "principal_reference": f"action:{principal_action.pk}",
                "plan_code": "GOLD",
                "national_id": "CID-CHILD",
                "passport_number": "",
            },
            transaction=tx,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["principal_action_id"],
            str(principal_action.pk),
        )

    def test_dependent_is_linked_to_principal_during_processing(self):
        tx = self._transaction(status=MemberTransaction.Status.PENDING_VALIDATION)
        parent_action = MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            row_number=1,
            corrected_data={
                "employee_id": "E-FAMILY-1",
                "first_name": "Parent",
                "last_name": "Member",
                "date_of_birth": "1985-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "plan_code": "GOLD",
                "national_id": "CID-FAMILY-1",
            },
        )
        child_action = MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            row_number=2,
            corrected_data={
                "employee_id": "E-FAMILY-2",
                "first_name": "Child",
                "last_name": "Member",
                "date_of_birth": "2018-01-01",
                "gender": "Female",
                "relationship": "CHILD",
                "plan_code": "GOLD",
                "national_id": "CID-FAMILY-2",
                "principal_employee_id": "E-FAMILY-1",
            },
        )

        run_validation(tx, actor=self.user)
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.PENDING_APPROVAL)
        self.assertEqual(str(tx.validation_score), "100.00")

        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=["is_superuser", "is_staff"])

        approve_transaction(tx, self.user)
        start_tpa_processing(tx, self.user)
        for action, card in (
            (parent_action, "CARD-FAMILY-1"),
            (child_action, "CARD-FAMILY-2"),
        ):
            action.refresh_from_db()
            update_tpa_action(
                action,
                self.user,
                card_number=card,
                effective_date=date(2026, 7, 1),
                amount=action.calculated_premium,
            )
        complete_tpa_transaction(tx, self.user)

        parent = Member.objects.get(employee_id="E-FAMILY-1")
        child = Member.objects.get(employee_id="E-FAMILY-2")
        self.assertEqual(child.principal_id, parent.pk)

    def test_tpa_query_creates_dedicated_ticket_and_embedded_messages(self):
        tx = self._transaction(status=MemberTransaction.Status.PENDING_VALIDATION)
        MemberAction.objects.create(
            transaction=tx,
            action=tx.transaction_type,
            row_number=1,
            corrected_data={
                "employee_id": "E-Q-1",
                "first_name": "Query",
                "last_name": "Member",
                "date_of_birth": "1990-01-01",
                "gender": "Male",
                "relationship": "PRINCIPAL",
                "plan_code": "GOLD",
                "national_id": "CID-Q-1",
            },
        )
        run_validation(tx, actor=self.user)

        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=["is_superuser", "is_staff"])

        approve_transaction(tx, self.user)
        start_tpa_processing(tx, self.user)
        query = raise_tpa_query(
            tx,
            self.user,
            "Confirm relationship",
            "Please confirm the member relationship.",
        )

        tx.refresh_from_db()
        query.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.TPA_QUERY)
        self.assertEqual(query.status, TransactionQuery.Status.OPEN)
        self.assertIsNotNone(query.ticket_id)
        self.assertNotEqual(query.ticket_id, tx.ticket_id)
        self.assertEqual(query.messages.count(), 1)
        self.assertTrue(
            TicketComment.objects.filter(
                ticket=query.ticket,
                tpa_query_message__query=query,
            ).exists()
        )

        outsider = get_user_model().objects.create_user(
            username="query-viewer",
            password="x",
        )
        with self.assertRaises(PermissionError):
            post_query_message(query, outsider, "I should not be allowed to reply.")

        post_query_message(query, self.user, "Relationship confirmed.")
        self.assertEqual(query.messages.count(), 2)
        resolve_tpa_query(query, self.user)
        query.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(query.status, TransactionQuery.Status.RESOLVED)
        self.assertEqual(tx.status, MemberTransaction.Status.TPA_IN_PROGRESS)

    def test_inbound_email_mock_ai_creates_transaction_and_member_row(self):
        AIProviderConfig.objects.create(
            name="Test TPA Mock AI",
            provider=AIProviderConfig.Provider.MOCK,
            model_name="mock",
            allow_sensitive_data=True,
            supports_vision=True,
            task_capabilities=["email_extraction", "document_extraction"],
            priority=1,
            is_active=True,
        )
        AIExtractionProfile.objects.create(
            name="Test email extraction",
            task=AIExtractionProfile.Task.EMAIL_EXTRACTION,
            applicable_product="MEDICAL",
            instructions="Return strict member JSON.",
            priority=1,
            is_active=True,
        )
        email = InboundEmail.objects.create(
            provider="test",
            provider_message_id="mock-email-1",
            created_by=self.user,
            sender="hr@example.com",
            recipient="tpa@example.com",
            subject="Add member",
            received_at=timezone.now(),
            body_text=(
                f"Policy Number: {self.policy.policy_number}\n"
                "Transaction Type: MEMBER_ADD\n"
                "Effective Date: 2026-07-01\n"
                "--- member ---\n"
                "Employee ID: E-AI-100\n"
                "First Name: AI\n"
                "Middle Name:\n"
                "Last Name: Member\n"
                "Date of Birth: 1991-02-03\n"
                "Gender: Male\n"
                "Relationship: PRINCIPAL\n"
                "Principal Employee ID:\n"
                "Principal Member ID:\n"
                "National ID: CID-AI-100\n"
                "Passport Number: P-AI-100\n"
                "Plan Code: GOLD\n"
            ),
            processing_hints={
                "policy_id": self.policy.pk,
                "policy_number": self.policy.policy_number,
                "transaction_type": "MEMBER_ADD",
                "effective_date": "2026-07-01",
            },
        )

        tx = process_inbound_email(email, self.user)
        email.refresh_from_db()
        tx.refresh_from_db()

        self.assertEqual(email.processing_state, InboundEmail.State.PROCESSED)
        self.assertEqual(email.transaction_id, tx.pk)
        self.assertEqual(tx.source, MemberTransaction.Source.EMAIL)
        self.assertIsNotNone(tx.ticket_id)
        self.assertEqual(tx.member_actions.count(), 1)
        action = tx.member_actions.get()
        self.assertEqual(action.extracted_data["employee_id"], "E-AI-100")
        self.assertEqual(action.validation_status, MemberAction.Result.VALID)

