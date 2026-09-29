import re

from ..models import MemberPolicyEnrollment, MemberTransaction
from .member_merge import merge_member_rows


def enrollment_payload(enrollment):
    member = enrollment.member
    return {
        "tpa_member_id": member.tpa_member_id,
        "card_number": enrollment.card_number,
        "employee_id": member.employee_id,
        "first_name": member.first_name,
        "middle_name": member.middle_name,
        "last_name": member.last_name,
        "date_of_birth": member.date_of_birth.isoformat() if member.date_of_birth else "",
        "gender": member.gender,
        "relationship": member.relationship,
        "national_id": member.national_id,
        "passport_number": member.passport_number,
        "plan_code": enrollment.benefit_plan.code,
        "coverage_start_date": enrollment.coverage_start_date.isoformat() if enrollment.coverage_start_date else "",
        "coverage_end_date": enrollment.coverage_end_date.isoformat() if enrollment.coverage_end_date else "",
        "enrollment_status": enrollment.enrollment_status,
        "enrollment_id": enrollment.pk,
    }


def selectable_enrollments(tx):
    statuses = [MemberPolicyEnrollment.Status.ACTIVE]
    if tx.transaction_type == MemberTransaction.Type.MEMBER_REACTIVATE:
        statuses = [MemberPolicyEnrollment.Status.SUSPENDED]
    return (
        MemberPolicyEnrollment.objects.select_related("member", "benefit_plan")
        .filter(policy=tx.policy, enrollment_status__in=statuses)
        .order_by("member__employee_id", "member__first_name", "pk")
    )


def add_enrollments_to_transaction(tx, enrollments, *, source="policy_selection"):
    rows = [enrollment_payload(item) for item in enrollments]
    return merge_member_rows(
        tx,
        rows,
        source=source,
        confidence=100,
    )


def populate_policy_cancellation(tx):
    if tx.transaction_type != MemberTransaction.Type.POLICY_CANCEL:
        return []
    enrollments = MemberPolicyEnrollment.objects.select_related(
        "member", "benefit_plan"
    ).filter(
        policy=tx.policy,
        enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
    )
    return add_enrollments_to_transaction(
        tx,
        enrollments,
        source="policy_cancellation_population",
    )


def parse_card_numbers(raw):
    tokens = [
        value.strip()
        for value in re.split(r"[\s,;]+", str(raw or ""))
        if value.strip()
    ]
    unique = []
    duplicates = []
    seen = set()
    for value in tokens:
        key = value.casefold()
        if key in seen:
            duplicates.append(value)
            continue
        seen.add(key)
        unique.append(value)
    return unique, duplicates


def resolve_card_numbers(tx, raw):
    values, duplicates = parse_card_numbers(raw)
    all_enrollments = list(
        MemberPolicyEnrollment.objects.select_related("member", "benefit_plan")
        .filter(policy=tx.policy, card_number__in=values)
    )
    by_card = {item.card_number.casefold(): item for item in all_enrollments if item.card_number}

    matched = []
    inactive = []
    not_found = []
    required_status = (
        MemberPolicyEnrollment.Status.SUSPENDED
        if tx.transaction_type == MemberTransaction.Type.MEMBER_REACTIVATE
        else MemberPolicyEnrollment.Status.ACTIVE
    )
    for value in values:
        enrollment = by_card.get(value.casefold())
        if enrollment is None:
            not_found.append(value)
        elif enrollment.enrollment_status != required_status:
            inactive.append(value)
        else:
            matched.append(enrollment)
    return {
        "matched": matched,
        "not_found": not_found,
        "duplicates": duplicates,
        "inactive": inactive,
    }
