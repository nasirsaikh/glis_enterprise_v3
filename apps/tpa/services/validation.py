from decimal import Decimal

from django.utils import timezone

from ..models import MemberAction, MemberPolicyEnrollment, Policy
from .pricing import calculate_member_premium


NON_BYPASSABLE = {
    "POLICY_NOT_AUTHORIZED",
    "POLICY_MISSING",
    "PLAN_CROSS_POLICY",
    "DUPLICATE_PROCESSED_TRANSACTION",
    "CONCURRENCY_CONFLICT",
}


def error(code, field, message, blocking=True):
    return {
        "code": code,
        "field": field,
        "message": message,
        "blocking": blocking,
        "non_bypassable": code in NON_BYPASSABLE,
    }


def _payload(action):
    return {
        **(action.submitted_data or {}),
        **(action.extracted_data or {}),
        **(action.corrected_data or {}),
    }


def _find_active_enrollment(tx, data):
    qs = MemberPolicyEnrollment.objects.select_related("member").filter(
        policy=tx.policy,
        enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
    )
    employee_id = str(data.get("employee_id") or "").strip()
    national_id = str(data.get("national_id") or "").strip()
    passport_number = str(data.get("passport_number") or "").strip()
    member_id = str(data.get("tpa_member_id") or "").strip()

    if member_id:
        match = qs.filter(member__tpa_member_id=member_id).first()
        if match:
            return match
    if employee_id:
        match = qs.filter(member__employee_id=employee_id).first()
        if match:
            return match
    if national_id:
        match = qs.filter(member__national_id=national_id).first()
        if match:
            return match
    if passport_number:
        match = qs.filter(member__passport_number=passport_number).first()
        if match:
            return match
    return None


def validate_action(action):
    tx = action.transaction
    data = _payload(action)
    errors = []
    warnings = []

    if tx.policy.status != Policy.Status.ACTIVE:
        errors.append(error("POLICY_NOT_ACTIVE", "policy", "Policy is not active."))

    if not (tx.policy.start_date <= tx.effective_date <= tx.policy.expiry_date):
        errors.append(
            error(
                "EFFECTIVE_DATE_OUTSIDE_POLICY",
                "effective_date",
                "Effective date is outside the policy period.",
            )
        )

    if (
        tx.effective_date < timezone.localdate()
        and (timezone.localdate() - tx.effective_date).days
        > tx.policy.allowed_backdating_days
    ):
        errors.append(
            error(
                "BACKDATING_LIMIT",
                "effective_date",
                "Effective date exceeds allowed backdating.",
            )
        )

    if tx.transaction_type in {
        tx.Type.NEW_POLICY_ENROLLMENT,
        tx.Type.MEMBER_ADD,
    }:
        for field in (
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "relationship",
            "plan_code",
        ):
            if not data.get(field):
                errors.append(
                    error(
                        "REQUIRED_FIELD",
                        field,
                        f"{field.replace('_', ' ').title()} is required.",
                    )
                )

        plan = tx.policy.plans.filter(
            code=data.get("plan_code"),
            is_active=True,
        ).first()
        if data.get("plan_code") and not plan:
            errors.append(
                error(
                    "INVALID_PLAN",
                    "plan_code",
                    "Plan does not exist or is inactive for this policy.",
                )
            )

        employee_id = str(data.get("employee_id") or "").strip()
        national_id = str(data.get("national_id") or "").strip()
        if employee_id and MemberPolicyEnrollment.objects.filter(
            policy=tx.policy,
            enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
            member__employee_id=employee_id,
        ).exists():
            errors.append(
                error(
                    "MEMBER_ALREADY_ACTIVE",
                    "employee_id",
                    "Member is already active under this policy.",
                )
            )
        if national_id and MemberPolicyEnrollment.objects.filter(
            policy=tx.policy,
            enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
            member__national_id=national_id,
        ).exists():
            errors.append(
                error(
                    "DUPLICATE_NATIONAL_ID",
                    "national_id",
                    "National/Civil ID is already active under this policy.",
                )
            )

        if plan and not any(item["blocking"] for item in errors):
            amount, snapshot = calculate_member_premium(
                tx.policy,
                plan,
                tx.effective_date,
            )
            action.calculated_premium = amount
            action.calculation_snapshot = snapshot

    elif tx.transaction_type in {
        tx.Type.MEMBER_TERMINATE,
        tx.Type.MEMBER_DELETE,
    }:
        if not any(
            data.get(field)
            for field in (
                "tpa_member_id",
                "employee_id",
                "national_id",
                "passport_number",
            )
        ):
            errors.append(
                error(
                    "MEMBER_IDENTIFIER_REQUIRED",
                    "member",
                    "Provide TPA member ID, employee ID, national ID or passport number.",
                )
            )
        enrollment = _find_active_enrollment(tx, data)
        if not errors and not enrollment:
            errors.append(
                error(
                    "ACTIVE_MEMBER_NOT_FOUND",
                    "member",
                    "No active member enrollment matches the supplied identifier.",
                )
            )
        if enrollment:
            action.member = enrollment.member

    if (
        action.extraction_confidence is not None
        and action.extraction_confidence < 80
    ):
        warnings.append(
            {
                "code": "LOW_EXTRACTION_CONFIDENCE",
                "message": "Extraction confidence is below 80%; review this row.",
            }
        )

    action.validation_errors = errors
    action.warnings = warnings
    if any(item["blocking"] for item in errors):
        action.validation_status = MemberAction.Result.ERROR
    elif warnings:
        action.validation_status = MemberAction.Result.WARNING
    else:
        action.validation_status = MemberAction.Result.VALID

    action.save(
        update_fields=[
            "member",
            "validation_errors",
            "warnings",
            "validation_status",
            "calculated_premium",
            "calculation_snapshot",
            "updated_at",
        ]
    )
    return errors


def validate_transaction(tx):
    actions = list(tx.member_actions.all().order_by("row_number", "pk"))

    if tx.transaction_type != tx.Type.POLICY_CANCEL and not actions:
        tx.validation_score = Decimal("0")
        tx.premium_adjustment = Decimal("0")
        tx.premium_after = tx.premium_before
        tx.status = tx.Status.NEEDS_INFORMATION
        tx.save(
            update_fields=[
                "validation_score",
                "premium_adjustment",
                "premium_after",
                "status",
                "updated_at",
            ]
        )
        return actions

    passed = 0
    premium = Decimal("0")
    has_errors = False
    for action in actions:
        validate_action(action)
        if action.validation_status != MemberAction.Result.ERROR:
            passed += 1
        else:
            has_errors = True
        premium += action.calculated_premium or Decimal("0")

    if tx.transaction_type == tx.Type.POLICY_CANCEL and not actions:
        tx.validation_score = Decimal("100")
    else:
        tx.validation_score = Decimal(str(round((passed / len(actions)) * 100, 2)))

    tx.premium_adjustment = premium
    tx.premium_after = (tx.premium_before or Decimal("0")) + premium
    tx.status = tx.Status.VALIDATION_FAILED if has_errors else tx.Status.PENDING_APPROVAL
    tx.save(
        update_fields=[
            "validation_score",
            "premium_adjustment",
            "premium_after",
            "status",
            "updated_at",
        ]
    )
    return actions
