import bleach
from datetime import date, datetime

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import Notification, Ticket, TicketComment, TicketEvent

from ..models import (
    CardDispatch,
    Member,
    MemberPolicyEnrollment,
    MemberTransaction,
    TransactionEvent,
    TransactionQuery,
    TransactionQueryMessage,
)
from .access import (
    can_approve_tpa_transaction,
    can_process_tpa_transaction,
    can_view_query_message,
    can_view_transaction_query,
)
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


def _clean_chat_html(value):
    return bleach.clean(
        str(value or ""),
        tags=[
            "p", "br", "strong", "b", "em", "i", "u", "ol", "ul", "li",
            "blockquote", "a", "span", "div", "img",
        ],
        attributes={
            "a": ["href", "title", "target", "rel"],
            "img": ["src", "alt", "title"],
            "span": ["class"],
            "div": ["class"],
        },
        protocols=["http", "https", "mailto", "data"],
        strip=True,
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
def reject_transaction(tx, actor, reason):
    if tx.status != tx.Status.PENDING_APPROVAL:
        raise ValueError("Only a transaction pending approval can be rejected.")
    if not can_approve_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA approval authority.")
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("Rejection reason is required.")
    if tx.queries.filter(
        status=TransactionQuery.Status.OPEN,
        purpose=TransactionQuery.Purpose.APPROVAL,
    ).exists():
        raise ValueError("Resolve the open approval query before rejecting the transaction.")

    tx.status = tx.Status.REJECTED
    tx.rejection_reason = reason
    tx.approved_by = actor
    tx.approved_at = timezone.now()
    tx.save(
        update_fields=[
            "status",
            "rejection_reason",
            "approved_by",
            "approved_at",
            "updated_at",
        ]
    )
    if tx.ticket_id:
        tx.ticket.approval_state = "rejected"
        tx.ticket.save(update_fields=["approval_state", "updated_at"])
    _event(
        tx,
        actor,
        "approval_rejected",
        "TPA transaction rejected during approval.",
        {"reason": reason},
    )
    return tx


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
def update_tpa_action(
    action,
    actor,
    *,
    card_number="",
    effective_date=None,
    amount=None,
    override_reason="",
    comments="",
):
    tx = action.transaction
    if tx.status != tx.Status.TPA_IN_PROGRESS:
        raise ValueError("TPA member processing is available only while TPA processing is in progress.")
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")

    final_amount = amount if amount not in (None, "") else action.calculated_premium
    if final_amount != action.calculated_premium and not str(override_reason or "").strip():
        raise ValueError(
            "Provide an override reason when the TPA final amount differs from the system calculated amount."
        )

    action.card_number = str(card_number or "").strip()
    action.tpa_effective_date = _as_date(effective_date) if effective_date else tx.effective_date
    action.tpa_premium_amount = final_amount
    action.tpa_override_reason = str(override_reason or "").strip()
    action.processing_message = str(comments or "").strip()
    action.save(
        update_fields=[
            "card_number",
            "tpa_effective_date",
            "tpa_premium_amount",
            "tpa_override_reason",
            "processing_message",
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
            "system_amount": str(action.calculated_premium),
            "tpa_final_amount": str(action.tpa_premium_amount)
            if action.tpa_premium_amount is not None
            else None,
            "override_reason": action.tpa_override_reason,
            "comments": action.processing_message,
        },
    )
    return action


@transaction.atomic
def raise_transaction_query(
    tx,
    actor,
    subject,
    message,
    *,
    purpose=TransactionQuery.Purpose.TPA,
    audience=TransactionQuery.Audience.CLIENT_VISIBLE,
    selected_participant_ids=None,
):
    if purpose == TransactionQuery.Purpose.APPROVAL:
        if tx.status != tx.Status.PENDING_APPROVAL:
            raise ValueError("Approval discussion is available only while approval is pending.")
        if not can_approve_tpa_transaction(actor, tx):
            raise PermissionError("You do not have TPA approval authority.")
    else:
        if tx.status not in {
            tx.Status.SENT_TO_TPA,
            tx.Status.TPA_IN_PROGRESS,
            tx.Status.TPA_QUERY,
        }:
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
        purpose=purpose,
        audience=audience,
        raised_by=actor,
        pre_query_status=tx.status,
    )
    if selected_participant_ids:
        query.selected_participants.set(selected_participant_ids)

    query_ticket = create_query_ticket(
        tx,
        query,
        actor,
        str(message or "").strip(),
    )
    internal = audience == TransactionQuery.Audience.INSURER_TPA_INTERNAL
    comment = TicketComment.objects.create(
        ticket=query_ticket,
        author=actor,
        body=_clean_chat_html(message),
        is_internal=internal,
    )
    TransactionQueryMessage.objects.create(
        query=query,
        ticket_comment=comment,
        sender=actor,
        kind=TransactionQueryMessage.Kind.QUERY,
        audience=audience,
    )

    if purpose != TransactionQuery.Purpose.APPROVAL and not internal:
        tx.status = tx.Status.TPA_QUERY
        tx.save(update_fields=["status", "updated_at"])

    _event(
        tx,
        actor,
        "approval_query_raised" if purpose == TransactionQuery.Purpose.APPROVAL else "tpa_query_raised",
        f"{query.get_purpose_display()} raised: {query.subject}",
        {
            "query_id": query.pk,
            "query_ticket": query.ticket.reference if query.ticket else "",
            "ticket_comment_id": comment.pk,
            "audience": audience,
        },
    )
    if audience == TransactionQuery.Audience.CLIENT_VISIBLE:
        _notify_query_user(
            tx.requester,
            query,
            f"{query.get_purpose_display()}: {query.subject}",
            str(message or "").strip(),
        )
    elif audience == TransactionQuery.Audience.SELECTED_PARTICIPANTS:
        for participant in query.selected_participants.filter(is_active=True):
            if participant.pk != actor.pk:
                _notify_query_user(
                    participant,
                    query,
                    f"{query.get_purpose_display()}: {query.subject}",
                    str(message or "").strip(),
                )
    return query


def raise_tpa_query(tx, actor, subject, message, *, audience=None):
    return raise_transaction_query(
        tx,
        actor,
        subject,
        message,
        purpose=TransactionQuery.Purpose.TPA,
        audience=audience or TransactionQuery.Audience.CLIENT_VISIBLE,
    )


@transaction.atomic
def post_query_message(query, actor, message, *, kind=None, audience=None):
    if query.status != TransactionQuery.Status.OPEN:
        raise ValueError("This query is already resolved.")
    tx = query.transaction
    if not can_view_transaction_query(actor, query):
        raise PermissionError("You do not have access to this conversation.")

    is_internal_user = (
        actor.is_superuser
        or can_approve_tpa_transaction(actor, tx)
        or can_process_tpa_transaction(actor, tx)
    )
    is_requester = actor.pk == tx.requester_id
    is_selected = query.selected_participants.filter(pk=actor.pk).exists()
    if not (is_internal_user or is_requester or is_selected):
        raise PermissionError("You are not a participant in this conversation.")

    message_audience = audience or query.audience
    if not is_internal_user and message_audience == TransactionQuery.Audience.INSURER_TPA_INTERNAL:
        raise PermissionError("Client participants cannot post internal insurer/TPA messages.")
    if is_requester and query.audience == TransactionQuery.Audience.INSURER_TPA_INTERNAL:
        raise PermissionError("This is an internal insurer/TPA conversation.")

    text = _clean_chat_html(message).strip()
    if not text:
        raise ValueError("Query message cannot be empty.")
    if not query.ticket_id:
        raise ValueError("The query is not linked to its GLIS query ticket.")

    comment = TicketComment.objects.create(
        ticket=query.ticket,
        author=actor,
        body=text,
        is_internal=message_audience == TransactionQuery.Audience.INSURER_TPA_INTERNAL,
    )
    query_message = TransactionQueryMessage.objects.create(
        query=query,
        ticket_comment=comment,
        sender=actor,
        kind=kind or TransactionQueryMessage.Kind.REPLY,
        audience=message_audience,
    )

    if query.purpose == TransactionQuery.Purpose.APPROVAL:
        query.ticket.status = Ticket.Status.IN_PROGRESS
    elif message_audience == TransactionQuery.Audience.CLIENT_VISIBLE:
        query.ticket.status = (
            Ticket.Status.IN_PROGRESS
            if is_requester
            else Ticket.Status.PENDING_CUSTOMER
        )
    else:
        query.ticket.status = Ticket.Status.IN_PROGRESS
    query.ticket.save(update_fields=["status", "updated_at"])

    if message_audience == TransactionQuery.Audience.CLIENT_VISIBLE:
        recipient = query.raised_by if is_requester else tx.requester
        if recipient and recipient.pk != actor.pk:
            _notify_query_user(
                recipient,
                query,
                f"{query.get_purpose_display()} updated: {query.subject}",
                text,
            )
    elif message_audience == TransactionQuery.Audience.SELECTED_PARTICIPANTS:
        for participant in query.selected_participants.filter(is_active=True):
            if participant.pk != actor.pk:
                _notify_query_user(
                    participant,
                    query,
                    f"{query.get_purpose_display()} updated: {query.subject}",
                    text,
                )

    _event(
        tx,
        actor,
        "query_message",
        f"Message added to {query.subject}.",
        {
            "query_id": query.pk,
            "ticket_comment_id": comment.pk,
            "audience": message_audience,
        },
    )
    return query_message


@transaction.atomic
def share_query_message_with_client(query_message, actor):
    tx = query_message.query.transaction
    if not (
        actor.is_superuser
        or can_approve_tpa_transaction(actor, tx)
        or can_process_tpa_transaction(actor, tx)
    ):
        raise PermissionError("You do not have authority to share internal discussion.")
    if query_message.audience != TransactionQuery.Audience.INSURER_TPA_INTERNAL:
        return query_message
    query_message.shared_with_client_at = timezone.now()
    query_message.shared_with_client_by = actor
    query_message.save(
        update_fields=[
            "shared_with_client_at",
            "shared_with_client_by",
            "updated_at",
        ]
    )
    _event(
        tx,
        actor,
        "internal_message_shared",
        "Selected insurer/TPA discussion was shared with the client.",
        {
            "query_id": query_message.query_id,
            "message_id": query_message.pk,
        },
    )
    _notify_query_user(
        tx.requester,
        query_message.query,
        f"Information shared: {query_message.query.subject}",
        query_message.ticket_comment.body,
    )
    return query_message


@transaction.atomic
def resolve_tpa_query(query, actor):
    tx = query.transaction
    if query.status != TransactionQuery.Status.OPEN:
        return tx
    if query.purpose == TransactionQuery.Purpose.APPROVAL:
        if not can_approve_tpa_transaction(actor, tx):
            raise PermissionError("You do not have TPA approval authority.")
    elif not can_process_tpa_transaction(actor, tx):
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

    if query.purpose != TransactionQuery.Purpose.APPROVAL:
        other_open_client_queries = tx.queries.filter(
            status=TransactionQuery.Status.OPEN,
            audience=TransactionQuery.Audience.CLIENT_VISIBLE,
        ).exclude(pk=query.pk).exists()
        if not other_open_client_queries:
            tx.status = query.pre_query_status or tx.Status.TPA_IN_PROGRESS
            if tx.status == tx.Status.SENT_TO_TPA:
                tx.status = tx.Status.TPA_IN_PROGRESS
            tx.save(update_fields=["status", "updated_at"])

    _event(
        tx,
        actor,
        "approval_query_resolved" if query.purpose == TransactionQuery.Purpose.APPROVAL else "tpa_query_resolved",
        f"{query.get_purpose_display()} resolved: {query.subject}",
        {
            "query_id": query.pk,
            "query_ticket": query.ticket.reference if query.ticket else "",
        },
    )
    if query.audience == TransactionQuery.Audience.CLIENT_VISIBLE and tx.requester_id != actor.pk:
        _notify_query_user(
            tx.requester,
            query,
            f"{query.get_purpose_display()} resolved: {query.subject}",
            "The information request has been resolved.",
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
        actions = list(tx.member_actions.all())
        if not actions:
            raise ValueError("At least one member is required before continuing.")
        for action in actions:
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

    if (
        tx.transaction_type == tx.Type.MEMBER_ADD
        and tx.physical_card_required
    ):
        dispatch, _ = CardDispatch.objects.get_or_create(
            transaction=tx,
            defaults={"status": CardDispatch.Status.READY},
        )
        if dispatch.status in {
            CardDispatch.Status.DELIVERED,
            CardDispatch.Status.COLLECTED,
            CardDispatch.Status.NOT_REQUIRED,
        }:
            return process_transaction(tx, actor)
        if dispatch.status == CardDispatch.Status.PENDING:
            dispatch.status = CardDispatch.Status.READY
            dispatch.save(update_fields=["status", "updated_at"])
        tx.status = tx.Status.CARD_DISPATCH
        tx.save(update_fields=["status", "updated_at"])
        _event(
            tx,
            actor,
            "card_ready",
            "TPA processing completed; physical card is ready for dispatch/collection.",
        )
        return tx

    return process_transaction(tx, actor)


@transaction.atomic
def update_card_dispatch(
    tx,
    actor,
    *,
    method="",
    status="",
    courier_company="",
    tracking_number="",
    dispatched_at=None,
    expected_delivery_at=None,
    delivered_or_collected_at=None,
    recipient_name="",
    recipient_organization="",
    contact="",
    remarks="",
    proof_attachment=None,
):
    if tx.status != tx.Status.CARD_DISPATCH:
        raise ValueError("Card dispatch is not active for this transaction.")
    if not can_process_tpa_transaction(actor, tx):
        raise PermissionError("You do not have TPA processing authority.")

    dispatch, _ = CardDispatch.objects.select_for_update().get_or_create(
        transaction=tx
    )
    if method:
        dispatch.method = method
    if status:
        dispatch.status = status
    dispatch.courier_company = str(courier_company or "").strip()
    dispatch.tracking_number = str(tracking_number or "").strip()
    dispatch.dispatched_at = dispatched_at or dispatch.dispatched_at
    dispatch.expected_delivery_at = expected_delivery_at or dispatch.expected_delivery_at
    dispatch.delivered_or_collected_at = (
        delivered_or_collected_at or dispatch.delivered_or_collected_at
    )
    dispatch.recipient_name = str(recipient_name or "").strip()
    dispatch.recipient_organization = str(recipient_organization or "").strip()
    dispatch.contact = str(contact or "").strip()
    dispatch.remarks = str(remarks or "").strip()
    if proof_attachment is not None:
        dispatch.proof_attachment = proof_attachment
    dispatch.recorded_by = actor
    dispatch.save()

    _event(
        tx,
        actor,
        "card_dispatch_updated",
        f"Card dispatch updated: {dispatch.get_status_display()}.",
        {
            "method": dispatch.method,
            "status": dispatch.status,
            "tracking_number": dispatch.tracking_number,
        },
    )

    if dispatch.status in {
        CardDispatch.Status.DELIVERED,
        CardDispatch.Status.COLLECTED,
        CardDispatch.Status.NOT_REQUIRED,
    }:
        return process_transaction(tx, actor)
    return tx


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
    if tx.queries.filter(
        status=TransactionQuery.Status.OPEN,
        purpose=TransactionQuery.Purpose.APPROVAL,
    ).exists():
        raise ValueError("Resolve the open approval query before approving the transaction.")
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


def _find_enrollment(tx, data, statuses=None):
    statuses = statuses or [MemberPolicyEnrollment.Status.ACTIVE]
    qs = MemberPolicyEnrollment.objects.select_related("member").filter(
        policy=tx.policy,
        enrollment_status__in=statuses,
    )
    lookups = (
        ("member__tpa_member_id", data.get("tpa_member_id")),
        ("card_number", data.get("card_number")),
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


def _process_suspension(tx, action):
    data = _data(action)
    enrollment = _find_enrollment(tx, data)
    if not enrollment:
        raise ValueError("Active member enrollment no longer exists.")
    member = enrollment.member
    enrollment.enrollment_status = MemberPolicyEnrollment.Status.SUSPENDED
    enrollment.suspension_date = action.tpa_effective_date or tx.effective_date
    enrollment.suspension_reason = tx.remarks
    expected = tx.expected_reactivation_date or (tx.metadata or {}).get("temporary_until")
    enrollment.expected_reactivation_date = _as_date(expected) if expected else None
    enrollment.save(
        update_fields=[
            "enrollment_status",
            "suspension_date",
            "suspension_reason",
            "expected_reactivation_date",
            "updated_at",
        ]
    )
    member.status = Member.Status.SUSPENDED
    member.save(update_fields=["status", "updated_at"])
    action.member = member
    action.after_data = {
        "member_id": member.tpa_member_id,
        "enrollment_id": enrollment.pk,
        "status": enrollment.enrollment_status,
        "suspension_date": enrollment.suspension_date.isoformat(),
    }


def _process_reactivation(tx, action):
    data = _data(action)
    enrollment = _find_enrollment(
        tx,
        data,
        statuses=[MemberPolicyEnrollment.Status.SUSPENDED],
    )
    if not enrollment:
        raise ValueError("Suspended member enrollment no longer exists.")
    member = enrollment.member
    enrollment.enrollment_status = MemberPolicyEnrollment.Status.ACTIVE
    enrollment.reactivation_date = action.tpa_effective_date or tx.effective_date
    enrollment.save(
        update_fields=[
            "enrollment_status",
            "reactivation_date",
            "updated_at",
        ]
    )
    member.status = Member.Status.ACTIVE
    member.save(update_fields=["status", "updated_at"])
    action.member = member
    action.after_data = {
        "member_id": member.tpa_member_id,
        "enrollment_id": enrollment.pk,
        "status": enrollment.enrollment_status,
        "reactivation_date": enrollment.reactivation_date.isoformat(),
    }


@transaction.atomic
def process_transaction(tx, actor):
    original_status = tx.status
    if tx.status not in {tx.Status.TPA_IN_PROGRESS, tx.Status.CARD_DISPATCH}:
        raise ValueError(
            "Final processing is allowed only from TPA In Progress or completed card dispatch."
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
        enrollments = tx.policy.enrollments.select_for_update().filter(
            enrollment_status__in=[
                MemberPolicyEnrollment.Status.ACTIVE,
                MemberPolicyEnrollment.Status.SUSPENDED,
            ]
        )
        member_ids = list(enrollments.values_list("member_id", flat=True))
        enrollments.update(
            enrollment_status=MemberPolicyEnrollment.Status.CANCELLED,
            cancellation_date=tx.effective_date,
        )
        Member.objects.filter(pk__in=member_ids).update(status=Member.Status.CANCELLED)
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
                elif tx.transaction_type == tx.Type.MEMBER_SUSPEND:
                    _process_suspension(tx, action)
                elif tx.transaction_type == tx.Type.MEMBER_REACTIVATE:
                    _process_reactivation(tx, action)

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
            if original_status in {tx.Status.TPA_IN_PROGRESS, tx.Status.CARD_DISPATCH}
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
