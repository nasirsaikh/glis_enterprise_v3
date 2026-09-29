from datetime import date, datetime

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import Notification, Ticket, TicketComment, TicketEvent

from ..models import (
    Member,
    MemberPolicyEnrollment,
    MemberTransaction,
    TransactionEvent,
    TransactionQuery,
    TransactionQueryMessage,
)
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


def _notify_query_user(user, query, title, body):
    if not user or not getattr(user, "is_active", False):
        return
    Notification.objects.create(
        user=user,
        ticket=query.ticket,
        kind="update",
        title=title[:160],
        body=body[:500],
        link=reverse(
            "tpa:transaction_detail",
            args=[query.transaction.reference],
        ),
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
def dispatch_to_tpa(tx, actor=None):
    if tx.status not in {tx.Status.APPROVED, tx.Status.AUTO_APPROVED}:
        raise ValueError("Transaction must be approved before dispatch to TPA.")
    tx.status = tx.Status.SENT_TO_TPA
    tx.metadata = {
        **(tx.metadata or {}),
        "tpa_route": {
            "organization_id": tx.policy.tpa_organization_id,
            "organization": (
                tx.policy.tpa_organization.name_en
                if tx.policy.tpa_organization_id
                else "GLIS TPA Operations"
            ),
            "dispatched_at": timezone.now().isoformat(),
        },
    }
    tx.save(update_fields=["status", "metadata", "updated_at"])
    _event(
        tx,
        actor,
        "sent_to_tpa",
        "Transaction dispatched to TPA processing.",
        {"tpa_organization_id": tx.policy.tpa_organization_id},
    )
    return tx


@transaction.atomic
def start_tpa_processing(tx, actor):
    if tx.status != tx.Status.SENT_TO_TPA:
        raise ValueError("Transaction is not waiting for TPA processing.")
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")
    tx.status = tx.Status.TPA_IN_PROGRESS
    tx.save(update_fields=["status", "updated_at"])
    _event(tx, actor, "tpa_started", "TPA processing started.")
    return tx


@transaction.atomic
def update_tpa_action(action, actor, *, card_number="", effective_date=None, amount=None):
    tx = action.transaction
    if tx.status != tx.Status.TPA_IN_PROGRESS:
        raise ValueError("TPA member processing is available only while TPA processing is in progress.")
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")

    action.card_number = str(card_number or "").strip()
    action.tpa_effective_date = _as_date(effective_date) if effective_date else tx.effective_date
    action.tpa_premium_amount = (
        amount if amount not in (None, "") else action.calculated_premium
    )
    action.save(
        update_fields=[
            "card_number",
            "tpa_effective_date",
            "tpa_premium_amount",
            "updated_at",
        ]
    )
    _event(
        tx,
        actor,
        "tpa_member_updated",
        f"TPA processing data updated for row {action.row_number or action.pk}.",
        {
            "action_id": action.pk,
            "card_number": action.card_number,
            "effective_date": action.tpa_effective_date.isoformat()
            if action.tpa_effective_date
            else None,
            "amount": str(action.tpa_premium_amount)
            if action.tpa_premium_amount is not None
            else None,
        },
    )
    return action


@transaction.atomic
def raise_tpa_query(tx, actor, subject, message):
    if tx.status not in {tx.Status.SENT_TO_TPA, tx.Status.TPA_IN_PROGRESS}:
        raise ValueError("A TPA query can be raised only during TPA processing.")
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")

    from .ticketing import create_query_ticket, create_ticket_for_transaction

    if not tx.ticket_id:
        create_ticket_for_transaction(tx, actor=actor)
        tx.refresh_from_db(fields=["ticket"])

    query = TransactionQuery.objects.create(
        transaction=tx,
        subject=str(subject or "").strip() or "Additional information required",
        raised_by=actor,
        pre_query_status=tx.status,
    )
    query_ticket = create_query_ticket(
        tx,
        query,
        actor,
        str(message or "").strip(),
    )
    comment = TicketComment.objects.create(
        ticket=query_ticket,
        author=actor,
        body=(
            f"TPA QUERY — {query.subject}\n\n"
            f"{str(message or '').strip()}"
        ),
        is_internal=False,
    )
    TransactionQueryMessage.objects.create(
        query=query,
        ticket_comment=comment,
        sender=actor,
        kind=TransactionQueryMessage.Kind.QUERY,
    )
    tx.status = tx.Status.TPA_QUERY
    tx.save(update_fields=["status", "updated_at"])
    _event(
        tx,
        actor,
        "tpa_query_raised",
        f"TPA query raised: {query.subject}",
        {
            "query_id": query.pk,
            "query_ticket": query.ticket.reference if query.ticket else "",
            "ticket_comment_id": comment.pk,
        },
    )
    _notify_query_user(
        tx.requester,
        query,
        f"TPA query: {query.subject}",
        str(message or "").strip(),
    )
    return query


@transaction.atomic
def post_query_message(query, actor, message, *, kind=None):
    if query.status != TransactionQuery.Status.OPEN:
        raise ValueError("This query is already resolved.")
    tx = query.transaction
    if (
        actor.pk != tx.requester_id
        and not can_process_tpa_transaction(actor, tx)
    ):
        raise PermissionError(
            "Only the requester or an authorized TPA processor can reply to this query."
        )
    if not query.ticket_id:
        raise ValueError("The query is not linked to its GLIS query ticket.")
    text = str(message or "").strip()
    if not text:
        raise ValueError("Query message cannot be empty.")

    comment = TicketComment.objects.create(
        ticket=query.ticket,
        author=actor,
        body=text,
        is_internal=False,
    )
    TransactionQueryMessage.objects.create(
        query=query,
        ticket_comment=comment,
        sender=actor,
        kind=kind or TransactionQueryMessage.Kind.REPLY,
    )
    query.ticket.status = (
        Ticket.Status.IN_PROGRESS
        if actor.pk == tx.requester_id
        else Ticket.Status.PENDING_CUSTOMER
    )
    query.ticket.save(update_fields=["status", "updated_at"])
    recipient = query.raised_by if actor.pk == tx.requester_id else tx.requester
    if recipient and recipient.pk != actor.pk:
        _notify_query_user(
            recipient,
            query,
            f"TPA query updated: {query.subject}",
            text,
        )
    _event(
        tx,
        actor,
        "tpa_query_message",
        f"Query message added to {query.subject}.",
        {"query_id": query.pk, "ticket_comment_id": comment.pk},
    )
    return comment


@transaction.atomic
def resolve_tpa_query(query, actor):
    tx = query.transaction
    if query.status != TransactionQuery.Status.OPEN:
        return tx
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")

    query.status = TransactionQuery.Status.RESOLVED
    query.resolved_by = actor
    query.resolved_at = timezone.now()
    query.save(
        update_fields=[
            "status",
            "resolved_by",
            "resolved_at",
            "updated_at",
        ]
    )
    if query.ticket_id:
        query.ticket.status = Ticket.Status.RESOLVED
        query.ticket.resolved_at = timezone.now()
        query.ticket.save(
            update_fields=["status", "resolved_at", "updated_at"]
        )
    tx.status = query.pre_query_status or tx.Status.TPA_IN_PROGRESS
    if tx.status == tx.Status.SENT_TO_TPA:
        tx.status = tx.Status.TPA_IN_PROGRESS
    tx.save(update_fields=["status", "updated_at"])
    _event(
        tx,
        actor,
        "tpa_query_resolved",
        f"TPA query resolved: {query.subject}",
        {
            "query_id": query.pk,
            "query_ticket": query.ticket.reference if query.ticket else "",
        },
    )
    if tx.requester_id != actor.pk:
        _notify_query_user(
            tx.requester,
            query,
            f"TPA query resolved: {query.subject}",
            "The query has been resolved and TPA processing has resumed.",
        )
    return tx


@transaction.atomic
def complete_tpa_transaction(tx, actor):
    if tx.status != tx.Status.TPA_IN_PROGRESS:
        raise ValueError("Transaction must be in TPA processing before completion.")
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")
    if tx.queries.filter(status=TransactionQuery.Status.OPEN).exists():
        raise ValueError("Resolve all open queries before completing the transaction.")

    if tx.transaction_type != tx.Type.POLICY_CANCEL:
        for action in tx.member_actions.all():
            if action.validation_status == action.Result.ERROR:
                raise ValueError("Resolve member validation errors before completion.")
            if not action.tpa_effective_date:
                raise ValueError(
                    f"TPA effective date is required for row {action.row_number or action.pk}."
                )
            if action.tpa_premium_amount is None:
                raise ValueError(
                    f"TPA premium/refund amount is required for row {action.row_number or action.pk}."
                )
            if tx.transaction_type in {
                tx.Type.NEW_POLICY_ENROLLMENT,
                tx.Type.MEMBER_ADD,
            } and not action.card_number:
                raise ValueError(
                    f"Card/member number is required for row {action.row_number or action.pk}."
                )

    return process_transaction(tx, actor)


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
    if tx.status == tx.Status.AUTO_APPROVED:
        return dispatch_to_tpa(tx, actor=actor)
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
    return dispatch_to_tpa(tx, actor=actor)


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
        last_approval = (
            tx.ticket.approvals.filter(status="approved")
            .select_related("approver")
            .order_by("-decided_at", "-pk")
            .first()
        )
        approver = last_approval.approver if last_approval else actor
        tx.status = tx.Status.APPROVED
        tx.approved_at = (last_approval.decided_at if last_approval else timezone.now())
        tx.approved_by = approver
        tx.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
        _event(tx, approver or actor, "approved", "Linked GLIS approval completed")
        return dispatch_to_tpa(tx, actor=approver or actor)
    return tx


def _resolve_principal_member(tx, action, data):
    relationship = str(data.get("relationship") or "").upper()
    if relationship == Member.Relationship.PRINCIPAL:
        return None

    active = Member.objects.filter(
        relationship=Member.Relationship.PRINCIPAL,
        status=Member.Status.ACTIVE,
        enrollments__policy=tx.policy,
        enrollments__enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
    ).distinct()

    member_ref = str(data.get("principal_member_id") or "").strip()
    if member_ref:
        member = (
            active.filter(pk=int(member_ref)).first()
            if member_ref.isdigit()
            else active.filter(tpa_member_id=member_ref).first()
        )
        if member:
            return member

    action_ref = str(data.get("principal_action_id") or "").strip()
    if action_ref.isdigit():
        principal_action = tx.member_actions.filter(pk=int(action_ref)).select_related("member").first()
        if principal_action and principal_action.member_id:
            return principal_action.member

    principal_employee_id = str(data.get("principal_employee_id") or "").strip()
    if principal_employee_id:
        member = active.filter(employee_id=principal_employee_id).first()
        if member:
            return member
        for principal_action in tx.member_actions.select_related("member").all():
            principal_data = _data(principal_action)
            if (
                str(principal_data.get("relationship") or "").upper()
                == Member.Relationship.PRINCIPAL
                and str(principal_data.get("employee_id") or "").strip()
                == principal_employee_id
                and principal_action.member_id
            ):
                return principal_action.member

    raise ValueError("Parent principal could not be resolved for this dependent.")


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
    principal = _resolve_principal_member(tx, action, data)
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
        principal=principal,
        status=Member.Status.ACTIVE,
    )
    enrollment = MemberPolicyEnrollment.objects.create(
        member=member,
        policy=tx.policy,
        benefit_plan=plan,
        coverage_start_date=action.tpa_effective_date or tx.effective_date,
        coverage_end_date=tx.policy.expiry_date,
        enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
        card_number=action.card_number,
        premium_amount=(
            action.tpa_premium_amount
            if action.tpa_premium_amount is not None
            else action.calculated_premium
        ),
        premium_calculation_basis={
            **(action.calculation_snapshot or {}),
            "system_calculated_amount": str(action.calculated_premium),
            "tpa_final_amount": (
                str(action.tpa_premium_amount)
                if action.tpa_premium_amount is not None
                else str(action.calculated_premium)
            ),
            "tpa_effective_date": (
                action.tpa_effective_date.isoformat()
                if action.tpa_effective_date
                else tx.effective_date.isoformat()
            ),
        },
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
        enrollment.termination_date = action.tpa_effective_date or tx.effective_date
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
    original_status = tx.status
    if tx.status != tx.Status.TPA_IN_PROGRESS:
        raise ValueError(
            "Final processing is allowed only from TPA In Progress. "
            "Use the approval/dispatch/start-processing workflow first."
        )
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
        actions = list(tx.member_actions.select_for_update().order_by("row_number", "pk"))
        if tx.transaction_type in {
            tx.Type.NEW_POLICY_ENROLLMENT,
            tx.Type.MEMBER_ADD,
        }:
            actions.sort(
                key=lambda item: (
                    str(_data(item).get("relationship") or "").upper()
                    != Member.Relationship.PRINCIPAL,
                    item.row_number or item.pk,
                )
            )

        for action in actions:
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
        tx.status = (
            tx.Status.COMPLETED
            if original_status == tx.Status.TPA_IN_PROGRESS
            else tx.Status.PROCESSED
        )
        tx.processed_at = timezone.now()
        if tx.transaction_type == tx.Type.NEW_POLICY_ENROLLMENT:
            tx.policy.status = tx.policy.Status.ACTIVE
            tx.policy.initial_enrollment_completed_at = tx.processed_at
            tx.policy.initial_enrollment_completed_by = actor
            tx.policy.save(
                update_fields=[
                    "status",
                    "initial_enrollment_completed_at",
                    "initial_enrollment_completed_by",
                    "updated_at",
                ]
            )

    tx.save(update_fields=["status", "processed_at", "metadata", "updated_at"])
    _event(
        tx,
        actor,
        "processed" if not errors else "processing_failed",
        (
            "TPA transaction completed"
            if not errors and tx.status == tx.Status.COMPLETED
            else "TPA transaction processed"
            if not errors
            else "TPA transaction processing failed"
        ),
        {"errors": errors},
    )
    return tx
