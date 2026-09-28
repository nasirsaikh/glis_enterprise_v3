from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import (
    BenefitPlan,
    MemberAction,
    MemberPolicyEnrollment,
    MemberTransaction,
    Policy,
    PolicyAccess,
    TPAOrganization,
)
from .forms import MemberRowForm
from .services.access import can_access_tpa, can_create_tpa_transaction
from .services.pricing import calculate_member_premium
from .services.workflow import approve_transaction, process_transaction, run_validation


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
            organization_type="INSURER",
        )
        self.policy = Policy.objects.create(
            sponsor=self.sponsor,
            insurance_company=self.insurer,
            policy_number="POL-1",
            start_date=date(2026, 1, 1),
            expiry_date=date(2026, 12, 31),
            status="active",
            allowed_backdating_days=3650,
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

    def test_validation_with_no_member_rows_requires_information(self):
        tx = self._transaction(status=MemberTransaction.Status.PENDING_VALIDATION)
        run_validation(tx, actor=self.user)
        tx.refresh_from_db()
        self.assertEqual(tx.status, MemberTransaction.Status.NEEDS_INFORMATION)
        self.assertEqual(str(tx.validation_score), "0.00")

    def test_member_add_can_validate_approve_and_process(self):
        tx = self._transaction(status=MemberTransaction.Status.PENDING_VALIDATION)
        MemberAction.objects.create(
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
        process_transaction(tx, self.user)
        tx.refresh_from_db()

        self.assertEqual(tx.status, MemberTransaction.Status.PROCESSED)
        self.assertTrue(
            MemberPolicyEnrollment.objects.filter(
                policy=self.policy,
                member__employee_id="E-100",
                enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
            ).exists()
        )

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
        MemberAction.objects.create(
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
        MemberAction.objects.create(
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
        process_transaction(tx, self.user)

        parent = Member.objects.get(employee_id="E-FAMILY-1")
        child = Member.objects.get(employee_id="E-FAMILY-2")
        self.assertEqual(child.principal_id, parent.pk)

