from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from apps.tickets.models import TicketEvent

from ..models import Member, MemberPolicyEnrollment, MemberTransaction, TransactionEvent
from .access import can_approve_tpa_transaction, can_process_tpa_transaction
from .stp import evaluate_stp
from .validation import validate_transaction


def _event(tx, actor, event_type, summary, details=None):
    TransactionEvent.objects.create(
        transaction=tx,
        actor=actor,
        event_type=event_type,
        summary=summary,
        details=details or {},
    )
    if tx.ticket_id:
        TicketEvent.objects.create(
            ticket=tx.ticket,
            actor=actor,
            event_type=f"tpa_{event_type}",
            summary=summary,
            details={"transaction_reference": tx.reference, **(details or {})},
        )


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date value: {value!r}")


def _data(action):
    return {
        **(action.submitted_data or {}),
        **(action.extracted_data or {}),
        **(action.corrected_data or {}),
    }


@transaction.atomic
def run_validation(tx, actor=None):
    validate_transaction(tx)
    tx.refresh_from_db()

    if tx.status in {tx.Status.NEEDS_INFORMATION, tx.Status.VALIDATION_FAILED}:
        tx.stp_eligible = False
        tx.stp_blockers = ["NO_MEMBER_ROWS"] if tx.status == tx.Status.NEEDS_INFORMATION else ["BLOCKING_VALIDATION"]
        tx.save(update_fields=["stp_eligible", "stp_blockers", "updated_at"])
        _event(
            tx,
            actor,
            "validation_completed",
            f"Validation completed with status {tx.get_status_display()}",
            {"score": str(tx.validation_score)},
        )
        return tx

    if tx.ticket_id:
        tx.ticket.refresh_from_db(fields=["approval_state"])

    eligible, blockers = evaluate_stp(tx)

    if tx.ticket_id and tx.ticket.approval_state == "rejected":
        tx.status = tx.Status.REJECTED
        tx.rejection_reason = "Linked GLIS ticket approval was rejected."
    elif tx.ticket_id and tx.ticket.approval_state == "pending":
        tx.status = tx.Status.PENDING_APPROVAL
    elif eligible:
        tx.status = tx.Status.AUTO_APPROVED
        tx.approved_at = timezone.now()
        tx.approved_by = None
    else:
        tx.status = tx.Status.PENDING_APPROVAL

    tx.save(
        update_fields=[
            "status",
            "rejection_reason",
            "approved_at",
            "approved_by",
            "updated_at",
        ]
    )
    _event(
        tx,
        actor,
        "validation_completed",
        f"Validation completed: {tx.validation_score}% · {tx.get_status_display()}",
        {"stp_eligible": eligible, "stp_blockers": blockers},
    )
    return tx


@transaction.atomic
def approve_transaction(tx, actor):
    if tx.status != tx.Status.PENDING_APPROVAL:
        raise ValueError("Transaction is not awaiting approval.")
    if not can_approve_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA approval authority.")
    if tx.ticket_id:
        tx.ticket.refresh_from_db(fields=["approval_state"])
        if tx.ticket.approval_state == "pending":
            raise ValueError("Complete the linked GLIS ticket approval first.")
        if tx.ticket.approval_state == "rejected":
            raise ValueError("The linked GLIS ticket approval was rejected.")

    tx.status = tx.Status.APPROVED
    tx.approved_at = timezone.now()
    tx.approved_by = actor
    tx.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
    _event(tx, actor, "approved", "TPA transaction approved")
    return tx


@transaction.atomic
def sync_from_ticket_approval(tx, actor=None):
    if not tx.ticket_id:
        return tx
    tx.ticket.refresh_from_db(fields=["approval_state"])
    if tx.ticket.approval_state == "rejected":
        tx.status = tx.Status.REJECTED
        tx.rejection_reason = "Linked GLIS ticket approval was rejected."
        tx.save(update_fields=["status", "rejection_reason", "updated_at"])
        _event(tx, actor, "approval_rejected", "Linked GLIS approval rejected")
    elif tx.ticket.approval_state == "approved" and tx.status == tx.Status.PENDING_APPROVAL:
        tx.status = tx.Status.APPROVED
        tx.approved_at = timezone.now()
        tx.approved_by = actor
        tx.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
        _event(tx, actor, "approved", "Linked GLIS approval completed")
    return tx


def _find_enrollment(tx, data):
    qs = MemberPolicyEnrollment.objects.select_related("member").filter(
        policy=tx.policy,
        enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
    )
    lookups = (
        ("member__tpa_member_id", data.get("tpa_member_id")),
        ("member__employee_id", data.get("employee_id")),
        ("member__national_id", data.get("national_id")),
        ("member__passport_number", data.get("passport_number")),
    )
    for field, value in lookups:
        value = str(value or "").strip()
        if value:
            match = qs.filter(**{field: value}).first()
            if match:
                return match
    return None


def _process_add(tx, action):
    data = _data(action)
    plan = tx.policy.plans.get(code=data["plan_code"], is_active=True)
    member = Member.objects.create(
        sponsor=tx.sponsor,
        employee_id=str(data.get("employee_id") or "").strip(),
        first_name=str(data["first_name"]).strip(),
        middle_name=str(data.get("middle_name") or "").strip(),
        last_name=str(data["last_name"]).strip(),
        date_of_birth=_as_date(data["date_of_birth"]),
        gender=str(data["gender"]).strip(),
        relationship=str(data["relationship"]).strip().upper(),
        national_id=str(data.get("national_id") or "").strip(),
        passport_number=str(data.get("passport_number") or "").strip(),
        status=Member.Status.ACTIVE,
    )
    enrollment = MemberPolicyEnrollment.objects.create(
        member=member,
        policy=tx.policy,
        benefit_plan=plan,
        coverage_start_date=tx.effective_date,
        coverage_end_date=tx.policy.expiry_date,
        enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
        premium_amount=action.calculated_premium,
        premium_calculation_basis=action.calculation_snapshot,
    )
    action.member = member
    action.after_data = {
        "member_id": member.tpa_member_id,
        "enrollment_id": enrollment.pk,
        "status": enrollment.enrollment_status,
    }


def _process_termination(tx, action, void=False):
    data = _data(action)
    enrollment = _find_enrollment(tx, data)
    if not enrollment:
        raise ValueError("Active member enrollment no longer exists.")
    member = enrollment.member
    if void:
        enrollment.enrollment_status = MemberPolicyEnrollment.Status.VOIDED
        enrollment.voided_at = timezone.now()
        member.status = Member.Status.VOIDED
        enrollment.save(update_fields=["enrollment_status", "voided_at", "updated_at"])
    else:
        enrollment.enrollment_status = MemberPolicyEnrollment.Status.TERMINATED
        enrollment.termination_date = tx.effective_date
        enrollment.termination_reason = tx.remarks
        member.status = Member.Status.TERMINATED
        enrollment.save(
            update_fields=[
                "enrollment_status",
                "termination_date",
                "termination_reason",
                "updated_at",
            ]
        )
    member.save(update_fields=["status", "updated_at"])
    action.member = member
    action.after_data = {
        "member_id": member.tpa_member_id,
        "enrollment_id": enrollment.pk,
        "status": enrollment.enrollment_status,
    }


@transaction.atomic
def process_transaction(tx, actor):
    if tx.status not in {tx.Status.APPROVED, tx.Status.AUTO_APPROVED}:
        raise ValueError("Transaction must be approved before processing.")
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")

    tx.status = tx.Status.PROCESSING
    tx.save(update_fields=["status", "updated_at"])
    errors = []

    if tx.transaction_type == tx.Type.POLICY_CANCEL:
        tx.policy.status = tx.policy.Status.CANCELLED
        tx.policy.cancellation_effective_date = tx.effective_date
        tx.policy.save(update_fields=["status", "cancellation_effective_date", "updated_at"])
        tx.policy.enrollments.filter(
            enrollment_status=MemberPolicyEnrollment.Status.ACTIVE
        ).update(
            enrollment_status=MemberPolicyEnrollment.Status.CANCELLED,
            cancellation_date=tx.effective_date,
        )
    else:
        for action in tx.member_actions.select_for_update().order_by("row_number", "pk"):
            try:
                if tx.transaction_type in {
                    tx.Type.NEW_POLICY_ENROLLMENT,
                    tx.Type.MEMBER_ADD,
                }:
                    _process_add(tx, action)
                elif tx.transaction_type == tx.Type.MEMBER_TERMINATE:
                    _process_termination(tx, action, void=False)
                elif tx.transaction_type == tx.Type.MEMBER_DELETE:
                    _process_termination(tx, action, void=True)

                action.processing_status = "SUCCESS"
                action.processing_message = "Processed successfully."
                action.processed_at = timezone.now()
                action.save(
                    update_fields=[
                        "member",
                        "after_data",
                        "processing_status",
                        "processing_message",
                        "processed_at",
                        "updated_at",
                    ]
                )
            except Exception as exc:
                action.processing_status = "FAILED"
                action.processing_message = str(exc)
                action.processed_at = timezone.now()
                action.save(
                    update_fields=[
                        "processing_status",
                        "processing_message",
                        "processed_at",
                        "updated_at",
                    ]
                )
                errors.append({"row": action.row_number, "error": str(exc)})

    if errors:
        tx.status = tx.Status.FAILED
        tx.metadata = {**(tx.metadata or {}), "processing_errors": errors}
    else:
        tx.status = tx.Status.PROCESSED
        tx.processed_at = timezone.now()

    tx.save(update_fields=["status", "processed_at", "metadata", "updated_at"])
    _event(
        tx,
        actor,
        "processed" if not errors else "processing_failed",
        "TPA transaction processed" if not errors else "TPA transaction processing failed",
        {"errors": errors},
    )
    return tx
