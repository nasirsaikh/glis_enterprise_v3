from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ai.models import (
    AIExtractionProfile,
    AIProviderConfig,
    AITrainingExample,
)
from apps.tpa.models import (
    BenefitPlan,
    InboundEmail,
    Member,
    MemberPolicyEnrollment,
    Policy,
    PolicyAccess,
    TPAOrganization,
)
from apps.tpa.services.ai_intake import process_inbound_email


class Command(BaseCommand):
    help = (
        "Seed an idempotent TPA demo environment with policy, plans, members, "
        "permissions, AI configuration and inbound email samples."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Existing user to receive TPA demo access. Defaults to the first superuser.",
        )
        parser.add_argument(
            "--skip-ai-processing",
            action="store_true",
            help="Create the sample inbound email without processing it through Mock AI.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        year = today.year
        User = get_user_model()

        actor = self._resolve_actor(User, options.get("username"))
        group = self._configure_permissions(actor)

        sponsor, _ = TPAOrganization.objects.update_or_create(
            code="DEMO-CORP",
            defaults={
                "name_en": "Demo Corporate LLC",
                "name_ar": "شركة تجريبية",
                "organization_type": TPAOrganization.Type.CORPORATE,
                "commercial_registration": "DEMO-CR-1001",
                "contact_name": "Demo HR",
                "contact_email": "hr.demo@example.com",
                "contact_phone": "+968 9000 0001",
                "is_active": True,
            },
        )
        insurer, _ = TPAOrganization.objects.update_or_create(
            code="DEMO-INS",
            defaults={
                "name_en": "Demo Insurance Company",
                "name_ar": "شركة التأمين التجريبية",
                "organization_type": TPAOrganization.Type.INSURER,
                "contact_name": "Demo Medical Team",
                "contact_email": "medical.demo@example.com",
                "contact_phone": "+968 9000 0002",
                "is_active": True,
            },
        )
        tpa, _ = TPAOrganization.objects.update_or_create(
            code="DEMO-TPA",
            defaults={
                "name_en": "NextCare Demo TPA",
                "name_ar": "مدير مطالبات تجريبي",
                "organization_type": TPAOrganization.Type.TPA,
                "contact_name": "Demo TPA Operations",
                "contact_email": "tpa.demo@example.com",
                "contact_phone": "+968 9000 0003",
                "is_active": True,
            },
        )

        policy, _ = Policy.objects.update_or_create(
            policy_number=f"DEMO-MED-{year}",
            defaults={
                "sponsor": sponsor,
                "insurance_company": insurer,
                "tpa_organization": tpa,
                "policy_name": f"Demo Corporate Medical {year}",
                "start_date": date(year, 1, 1),
                "expiry_date": date(year, 12, 31),
                "status": Policy.Status.ACTIVE,
                "product_type": "MEDICAL",
                "currency": "OMR",
                "stp_enabled": True,
                "premium_calculation_enabled": True,
                "allowed_backdating_days": 365,
                "validation_bypass_allowed": False,
                "configuration": {
                    "seeded": True,
                    "notes": "Sample policy for TPA workflow testing.",
                },
                "initial_enrollment_completed_at": timezone.now(),
                "initial_enrollment_completed_by": actor,
            },
        )

        gold, _ = BenefitPlan.objects.update_or_create(
            policy=policy,
            code="GOLD",
            defaults={
                "name": "Gold",
                "description": "Demo premium medical plan",
                "annual_premium": Decimal("365.000"),
                "default_sum_insured": Decimal("25000.000"),
                "premium_configuration": {
                    "method": "PRORATA",
                    "denominator": 365,
                },
                "is_active": True,
            },
        )
        silver, _ = BenefitPlan.objects.update_or_create(
            policy=policy,
            code="SILVER",
            defaults={
                "name": "Silver",
                "description": "Demo standard medical plan",
                "annual_premium": Decimal("240.000"),
                "default_sum_insured": Decimal("15000.000"),
                "premium_configuration": {
                    "method": "PRORATA",
                    "denominator": 365,
                },
                "is_active": True,
            },
        )

        PolicyAccess.objects.update_or_create(
            organization=sponsor,
            policy=policy,
            user=actor,
            defaults={
                "can_view": True,
                "can_view_members": True,
                "can_create_enrollment": True,
                "can_create_endorsement": True,
                "can_view_premium": True,
                "can_approve": True,
                "can_process": True,
                "active": True,
            },
        )

        principal = self._member(
            sponsor=sponsor,
            employee_id="DEMO-EMP-001",
            defaults={
                "first_name": "Ahmed",
                "middle_name": "Ali",
                "last_name": "Al Harthi",
                "date_of_birth": date(1988, 5, 12),
                "gender": "Male",
                "relationship": Member.Relationship.PRINCIPAL,
                "national_id": "DEMO-CID-1001",
                "passport_number": "DEMO-P-1001",
                "status": Member.Status.ACTIVE,
            },
        )
        spouse = self._member(
            sponsor=sponsor,
            employee_id="DEMO-EMP-002",
            defaults={
                "first_name": "Aisha",
                "middle_name": "",
                "last_name": "Al Harthi",
                "date_of_birth": date(1990, 9, 22),
                "gender": "Female",
                "relationship": Member.Relationship.SPOUSE,
                "national_id": "DEMO-CID-1002",
                "passport_number": "DEMO-P-1002",
                "principal": principal,
                "status": Member.Status.ACTIVE,
            },
        )
        child = self._member(
            sponsor=sponsor,
            employee_id="DEMO-EMP-003",
            defaults={
                "first_name": "Mariam",
                "middle_name": "",
                "last_name": "Al Harthi",
                "date_of_birth": date(2018, 3, 15),
                "gender": "Female",
                "relationship": Member.Relationship.CHILD,
                "national_id": "DEMO-CID-1003",
                "passport_number": "",
                "principal": principal,
                "status": Member.Status.ACTIVE,
            },
        )

        for member, plan in ((principal, gold), (spouse, gold), (child, silver)):
            MemberPolicyEnrollment.objects.update_or_create(
                member=member,
                policy=policy,
                defaults={
                    "benefit_plan": plan,
                    "coverage_start_date": policy.start_date,
                    "coverage_end_date": policy.expiry_date,
                    "enrollment_status": MemberPolicyEnrollment.Status.ACTIVE,
                    "premium_amount": plan.annual_premium,
                    "premium_calculation_basis": {
                        "method": "FULL",
                        "seeded": True,
                    },
                },
            )

        provider, _ = AIProviderConfig.objects.update_or_create(
            name="TPA Mock AI",
            defaults={
                "provider": AIProviderConfig.Provider.MOCK,
                "model_name": "tpa-mock-v1",
                "endpoint": "",
                "secret_reference": "",
                "temperature": Decimal("0.00"),
                "timeout_seconds": 30,
                "supports_vision": False,
                "task_capabilities": [
                    "email_extraction",
                    "member_field_mapping",
                ],
                "runtime_options": {},
                "allow_sensitive_data": True,
                "is_active": True,
                "priority": 900,
            },
        )

        email_profile, _ = AIExtractionProfile.objects.update_or_create(
            name="TPA Medical Email Extraction",
            task=AIExtractionProfile.Task.EMAIL_EXTRACTION,
            applicable_product="MEDICAL",
            applicable_transaction_type="",
            defaults={
                "system_prompt": (
                    "Extract only facts present in the email. Do not decide eligibility, "
                    "premium, STP or approval."
                ),
                "instructions": (
                    "Map relationships to PRINCIPAL/SPOUSE/CHILD/OTHER and dates to "
                    "YYYY-MM-DD. Use the selected policy hint when supplied."
                ),
                "field_aliases": {
                    "employee_id": ["employee no", "staff id", "emp no"],
                    "national_id": ["civil id", "national id"],
                    "plan_code": ["plan", "benefit plan"],
                },
                "priority": 1,
                "is_active": True,
            },
        )
        AITrainingExample.objects.update_or_create(
            profile=email_profile,
            name="Demo member addition email",
            defaults={
                "input_text": (
                    f"Policy Number: {policy.policy_number}\n"
                    "Transaction Type: MEMBER_ADD\n"
                    f"Effective Date: {today.isoformat()}\n"
                    "--- member ---\n"
                    "Employee ID: DEMO-EMAIL-001\n"
                    "First Name: Salim\n"
                    "Last Name: Al Balushi\n"
                    "Date of Birth: 1993-07-18\n"
                    "Gender: Male\n"
                    "Relationship: PRINCIPAL\n"
                    "Plan Code: GOLD"
                ),
                "expected_output": {
                    "policy_number": policy.policy_number,
                    "transaction_type": "MEMBER_ADD",
                    "effective_date": today.isoformat(),
                    "summary": "Add one member",
                    "confidence": 0.98,
                    "members": [
                        {
                            "employee_id": "DEMO-EMAIL-001",
                            "first_name": "Salim",
                            "last_name": "Al Balushi",
                            "date_of_birth": "1993-07-18",
                            "gender": "Male",
                            "relationship": "PRINCIPAL",
                            "plan_code": "GOLD",
                            "confidence": 0.98,
                        }
                    ],
                },
                "sort_order": 1,
                "is_active": True,
            },
        )

        AIExtractionProfile.objects.update_or_create(
            name="TPA Medical Vision Extraction",
            task=AIExtractionProfile.Task.DOCUMENT_EXTRACTION,
            applicable_product="MEDICAL",
            applicable_transaction_type="",
            defaults={
                "system_prompt": (
                    "Extract member identity/enrollment fields from insurance supporting "
                    "documents. Return JSON only."
                ),
                "instructions": (
                    "Never infer eligibility or pricing. If a field is unreadable, return null."
                ),
                "field_aliases": {},
                "priority": 1,
                "is_active": True,
            },
        )

        processed_email = self._seed_email(
            actor=actor,
            policy=policy,
            ai_provider=provider,
            key="seed-tpa-email-processed-v1",
            subject="Demo AI member addition - valid",
            body=(
                f"Policy Number: {policy.policy_number}\n"
                "Transaction Type: MEMBER_ADD\n"
                f"Effective Date: {today.isoformat()}\n"
                "Please add the following member.\n"
                "--- member ---\n"
                "Employee ID: DEMO-EMAIL-001\n"
                "First Name: Salim\n"
                "Middle Name:\n"
                "Last Name: Al Balushi\n"
                "Date of Birth: 1993-07-18\n"
                "Gender: Male\n"
                "Relationship: PRINCIPAL\n"
                "Principal Employee ID:\n"
                "Principal Member ID:\n"
                "National ID: DEMO-CID-EMAIL-001\n"
                "Passport Number: DEMO-P-EMAIL-001\n"
                "Plan Code: GOLD\n"
            ),
        )

        review_email = self._seed_email(
            actor=actor,
            policy=policy,
            ai_provider=provider,
            key="seed-tpa-email-review-v1",
            subject="Demo AI member addition - validation errors",
            body=(
                f"Policy Number: {policy.policy_number}\n"
                "Transaction Type: MEMBER_ADD\n"
                f"Effective Date: {today.isoformat()}\n"
                "This sample intentionally contains member validation errors.\n"
                "--- member ---\n"
                "Employee ID: DEMO-EMAIL-ERR-001\n"
                "First Name: Fatma\n"
                "Middle Name:\n"
                "Last Name: Demo\n"
                "Date of Birth:\n"
                "Gender: Female\n"
                "Relationship: CHILD\n"
                "Principal Employee ID:\n"
                "Principal Member ID:\n"
                "National ID: DEMO-CID-ERR-001\n"
                "Passport Number:\n"
                "Plan Code: INVALID-PLAN\n"
            ),
        )

        processed_tx = processed_email.transaction
        if (
            not options["skip_ai_processing"]
            and processed_email.processing_state != InboundEmail.State.PROCESSED
        ):
            processed_tx = process_inbound_email(processed_email, actor)

        self.stdout.write(self.style.SUCCESS("TPA sample data seeded successfully."))
        self.stdout.write(f"Actor: {actor.get_username()}")
        self.stdout.write(f"Group: {group.name}")
        self.stdout.write(f"Policy: {policy.policy_number} (initial enrollment completed)")
        self.stdout.write(f"TPA: {tpa.name_en}")
        self.stdout.write("Plans: GOLD, SILVER")
        self.stdout.write(
            f"Existing family: {principal.tpa_member_id}, "
            f"{spouse.tpa_member_id}, {child.tpa_member_id}"
        )
        self.stdout.write(f"AI provider: {provider.name} (Mock)")
        if processed_tx:
            self.stdout.write(
                f"Processed AI email transaction: {processed_tx.reference} "
                f"[{processed_tx.get_status_display()}]"
            )
        self.stdout.write(
            f"Unprocessed/error sample inbound email ID: {review_email.pk}"
        )
        self.stdout.write(
            "Portal: /portal/tpa/  |  Inbound email: /portal/tpa/inbound-emails/"
        )

    def _resolve_actor(self, User, username):
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(
                    f"User {username!r} does not exist. Create the user first or omit --username."
                ) from exc

        actor = User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
        if actor:
            return actor

        actor, created = User.objects.get_or_create(
            username="tpa_seed_bot",
            defaults={
                "email": "tpa-seed@example.invalid",
                "is_active": True,
                "is_staff": False,
            },
        )
        if created or actor.has_usable_password():
            actor.set_unusable_password()
            actor.save(update_fields=["password"])
        return actor

    def _configure_permissions(self, actor):
        group, _ = Group.objects.get_or_create(name="TPA Demo Operators")
        codenames = [
            "view_tpa_dashboard",
            "create_enrollment",
            "create_endorsement",
            "terminate_member",
            "delete_member",
            "cancel_policy",
            "approve_endorsement",
            "process_endorsement",
            "view_sensitive_member_data",
            "view_ai_source_data",
            "export_tpa_data",
        ]
        permissions = Permission.objects.filter(
            content_type__app_label="tpa",
            codename__in=codenames,
        )
        group.permissions.set(permissions)
        if not actor.is_superuser:
            actor.groups.add(group)
        return group

    def _member(self, *, sponsor, employee_id, defaults):
        member = Member.objects.filter(
            sponsor=sponsor,
            employee_id=employee_id,
        ).first()
        if member is None:
            member = Member.objects.create(
                sponsor=sponsor,
                employee_id=employee_id,
                **defaults,
            )
        else:
            for field, value in defaults.items():
                setattr(member, field, value)
            member.save()
        return member

    def _seed_email(self, *, actor, policy, ai_provider, key, subject, body):
        email, _ = InboundEmail.objects.update_or_create(
            provider="seed",
            provider_message_id=key,
            defaults={
                "created_by": actor,
                "sender": "hr.demo@example.com",
                "recipient": "tpa.demo@example.com",
                "subject": subject,
                "received_at": timezone.now(),
                "body_text": body,
                "processing_hints": {
                    "ai_provider_id": ai_provider.pk,
                    "policy_id": policy.pk,
                    "policy_number": policy.policy_number,
                    "transaction_type": "MEMBER_ADD",
                    "effective_date": timezone.localdate().isoformat(),
                },
                "attachment_metadata": [],
            },
        )
        return email
