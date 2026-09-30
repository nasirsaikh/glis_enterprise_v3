from decimal import Decimal

from django.utils import timezone

from ..models import Member, MemberAction, MemberPolicyEnrollment, Policy
from .pricing import calculate_member_premium, calculate_member_refund


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


def _find_principal_reference(tx, data, current_action=None):
    active = Member.objects.filter(
        relationship=Member.Relationship.PRINCIPAL,
        status=Member.Status.ACTIVE,
        enrollments__policy=tx.policy,
        enrollments__enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
    ).distinct()

    member_ref = str(data.get("principal_member_id") or "").strip()
    if member_ref:
        if member_ref.isdigit():
            member = active.filter(pk=int(member_ref)).first()
        else:
            member = active.filter(tpa_member_id=member_ref).first()
        if member:
            return ("member", member)

    action_ref = str(data.get("principal_action_id") or "").strip()
    if action_ref.isdigit():
        principal_action = tx.member_actions.filter(pk=int(action_ref)).first()
        if principal_action and principal_action.pk != getattr(current_action, "pk", None):
            principal_data = _payload(principal_action)
            if str(principal_data.get("relationship") or "").upper() == Member.Relationship.PRINCIPAL:
                return ("action", principal_action)

    employee_id = str(data.get("principal_employee_id") or "").strip()
    if employee_id:
        member = active.filter(employee_id=employee_id).first()
        if member:
            return ("member", member)
        for principal_action in tx.member_actions.all():
            if principal_action.pk == getattr(current_action, "pk", None):
                continue
            principal_data = _payload(principal_action)
            if (
                str(principal_data.get("relationship") or "").upper()
                == Member.Relationship.PRINCIPAL
                and str(principal_data.get("employee_id") or "").strip() == employee_id
            ):
                return ("action", principal_action)
    return None


def _find_enrollment(tx, data, statuses):
    qs = MemberPolicyEnrollment.objects.select_related(
        "member", "benefit_plan", "policy"
    ).filter(
        policy=tx.policy,
        enrollment_status__in=statuses,
    )
    employee_id = str(data.get("employee_id") or "").strip()
    national_id = str(data.get("national_id") or "").strip()
    passport_number = str(data.get("passport_number") or "").strip()
    member_id = str(data.get("tpa_member_id") or data.get("member_id") or "").strip()
    card_number = str(data.get("card_number") or "").strip()

    lookups = (
        ("member__tpa_member_id", member_id),
        ("card_number", card_number),
        ("member__employee_id", employee_id),
        ("member__national_id", national_id),
        ("member__passport_number", passport_number),
    )
    for field, value in lookups:
        if value:
            match = qs.filter(**{field: value}).first()
            if match:
                return match
    return None


def _find_active_enrollment(tx, data):
    return _find_enrollment(tx, data, [MemberPolicyEnrollment.Status.ACTIVE])


def _find_suspended_enrollment(tx, data):
    return _find_enrollment(tx, data, [MemberPolicyEnrollment.Status.SUSPENDED])


def validate_action(action):
    tx = action.transaction
    data = _payload(action)
    errors = []
    warnings = []
    for provenance in action.provenance or []:
        for conflict in provenance.get("conflicts") or []:
            warnings.append(
                {
                    "code": "SOURCE_CONFLICT",
                    "message": (
                        conflict.get("message")
                        or f"Conflicting source value for {conflict.get('field')}: "
                        f"kept {conflict.get('kept')!r}, incoming {conflict.get('incoming')!r}."
                    ),
                }
            )

    if (
        tx.policy.status != Policy.Status.ACTIVE
        and tx.transaction_type != tx.Type.NEW_POLICY_ENROLLMENT
    ):
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

        relationship = str(data.get("relationship") or "").upper()
        if relationship and relationship != Member.Relationship.PRINCIPAL:
            has_reference = any(
                str(data.get(field) or "").strip()
                for field in (
                    "principal_member_id",
                    "principal_action_id",
                    "principal_employee_id",
                )
            )
            if not has_reference:
                errors.append(
                    error(
                        "PARENT_PRINCIPAL_REQUIRED",
                        "principal",
                        "A parent principal must be selected for spouse, child or other dependent.",
                    )
                )
            elif not _find_principal_reference(tx, data, current_action=action):
                errors.append(
                    error(
                        "INVALID_PARENT_PRINCIPAL",
                        "principal",
                        "The selected parent principal is not an active principal on this policy or a principal row in this transaction.",
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
        passport_number = str(data.get("passport_number") or "").strip()
        if passport_number and MemberPolicyEnrollment.objects.filter(
            policy=tx.policy,
            enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
            member__passport_number=passport_number,
        ).exists():
            errors.append(
                error(
                    "DUPLICATE_PASSPORT",
                    "passport_number",
                    "Passport number is already active under this policy.",
                )
            )

        duplicate_fields = []
        for field in ("employee_id", "national_id", "passport_number"):
            value = str(data.get(field) or "").strip()
            if not value:
                continue
            for other in tx.member_actions.exclude(pk=action.pk):
                other_data = _payload(other)
                if str(other_data.get(field) or "").strip().casefold() == value.casefold():
                    duplicate_fields.append(field)
                    break
        for field in sorted(set(duplicate_fields)):
            errors.append(
                error(
                    "DUPLICATE_TRANSACTION_ROW",
                    field,
                    f"{field.replace('_', ' ').title()} is duplicated in this transaction.",
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

    elif tx.transaction_type == tx.Type.MEMBER_UPDATE:
        if not any(
            data.get(field)
            for field in (
                "tpa_member_id",
                "member_id",
                "card_number",
                "employee_id",
                "national_id",
                "passport_number",
            )
        ):
            errors.append(
                error(
                    "MEMBER_IDENTIFIER_REQUIRED",
                    "member",
                    "Provide card/member ID, employee ID, national ID or passport number.",
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
            for field in ("first_name", "last_name", "date_of_birth", "gender"):
                if not data.get(field):
                    errors.append(
                        error(
                            "REQUIRED_FIELD",
                            field,
                            f"{field.replace('_', ' ').title()} is required.",
                        )
                    )
            for field, lookup, label in (
                ("employee_id", "member__employee_id", "Employee number"),
                ("national_id", "member__national_id", "Civil/National ID"),
                ("passport_number", "member__passport_number", "Passport number"),
            ):
                value = str(data.get(field) or "").strip()
                if value and MemberPolicyEnrollment.objects.filter(
                    policy=tx.policy,
                    enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
                    **{lookup: value},
                ).exclude(member_id=enrollment.member_id).exists():
                    errors.append(
                        error(
                            "DUPLICATE_MEMBER_IDENTIFIER",
                            field,
                            f"{label} is already used by another active member on this policy.",
                        )
                    )
            action.calculated_premium = Decimal("0")
            action.calculation_snapshot = {
                "method": "NO_PREMIUM_CHANGE",
                "reason": "MEMBER_DEMOGRAPHIC_CHANGE",
            }

    elif tx.transaction_type in {
        tx.Type.MEMBER_TERMINATE,
        tx.Type.MEMBER_DELETE,
        tx.Type.MEMBER_SUSPEND,
    }:
        if not any(
            data.get(field)
            for field in (
                "tpa_member_id",
                "member_id",
                "card_number",
                "employee_id",
                "national_id",
                "passport_number",
            )
        ):
            errors.append(
                error(
                    "MEMBER_IDENTIFIER_REQUIRED",
                    "member",
                    "Provide card/member ID, employee ID, national ID or passport number.",
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
            if tx.transaction_type == tx.Type.MEMBER_DELETE:
                if tx.refund_basis == tx.RefundBasis.NONE:
                    errors.append(
                        error(
                            "REFUND_BASIS_REQUIRED",
                            "refund_basis",
                            "Choose Full Refund or Pro-Rata Refund for member deletion.",
                        )
                    )
                elif not any(item["blocking"] for item in errors):
                    amount, snapshot = calculate_member_refund(
                        enrollment,
                        tx.effective_date,
                        tx.refund_basis,
                    )
                    action.calculated_premium = amount
                    action.calculation_snapshot = snapshot

    elif tx.transaction_type == tx.Type.MEMBER_REACTIVATE:
        if not any(
            data.get(field)
            for field in (
                "tpa_member_id",
                "member_id",
                "card_number",
                "employee_id",
                "national_id",
                "passport_number",
            )
        ):
            errors.append(
                error(
                    "MEMBER_IDENTIFIER_REQUIRED",
                    "member",
                    "Provide card/member ID, employee ID, national ID or passport number.",
                )
            )
        enrollment = _find_suspended_enrollment(tx, data)
        if not errors and not enrollment:
            errors.append(
                error(
                    "SUSPENDED_MEMBER_NOT_FOUND",
                    "member",
                    "Only a currently suspended member on this policy can be reactivated.",
                )
            )
        if enrollment:
            action.member = enrollment.member
            if enrollment.suspension_date and tx.effective_date < enrollment.suspension_date:
                errors.append(
                    error(
                        "INVALID_REACTIVATION_DATE",
                        "effective_date",
                        "Reactivation date cannot be before the suspension date.",
                    )
                )

    elif tx.transaction_type == tx.Type.POLICY_CANCEL:
        enrollment = _find_enrollment(
            tx,
            data,
            [
                MemberPolicyEnrollment.Status.ACTIVE,
                MemberPolicyEnrollment.Status.SUSPENDED,
            ],
        )
        if enrollment:
            action.member = enrollment.member
            if tx.refund_basis == tx.RefundBasis.NONE:
                errors.append(
                    error(
                        "REFUND_BASIS_REQUIRED",
                        "refund_basis",
                        "Choose Full Refund or Pro-Rata Refund for policy cancellation.",
                    )
                )
            elif not any(item["blocking"] for item in errors):
                amount, snapshot = calculate_member_refund(
                    enrollment,
                    tx.effective_date,
                    tx.refund_basis,
                )
                action.calculated_premium = amount
                action.calculation_snapshot = snapshot

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
        tx.validation_completed_at = timezone.now()
        tx.save(
            update_fields=[
                "validation_score",
                "premium_adjustment",
                "premium_after",
                "validation_completed_at",
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
        if tx.refund_basis == tx.RefundBasis.NONE:
            tx.validation_score = Decimal("0")
            has_errors = True
        else:
            tx.validation_score = Decimal("100")
    else:
        tx.validation_score = Decimal(str(round((passed / len(actions)) * 100, 2)))

    tx.premium_adjustment = premium
    tx.premium_after = (tx.premium_before or Decimal("0")) + premium
    tx.validation_completed_at = timezone.now()
    tx.status = tx.Status.VALIDATION_FAILED if has_errors else tx.Status.PENDING_APPROVAL
    tx.save(
        update_fields=[
            "validation_score",
            "premium_adjustment",
            "premium_after",
            "validation_completed_at",
            "status",
            "updated_at",
        ]
    )
    return actions
