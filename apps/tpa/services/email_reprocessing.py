"""Queue explicit admin retries without changing completed endorsements."""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.job_center.queue import enqueue
from apps.job_center.models import QueuedJob

from ..models import InboundEmail, MemberTransaction
from .access import (
    can_create_tpa_transaction,
    can_edit_tpa_intake,
    visible_inbound_emails,
)


REPROCESS_QUEUED = "REPROCESS_QUEUED"
REPROCESSABLE_STATUSES = {
    MemberTransaction.Status.DRAFT,
    MemberTransaction.Status.PENDING_VALIDATION,
    MemberTransaction.Status.NEEDS_INFORMATION,
    MemberTransaction.Status.VALIDATION_FAILED,
}


def email_reprocessing_pending(email):
    return email.processing_stage == REPROCESS_QUEUED and QueuedJob.objects.filter(
        handler="tpa.reprocess_inbound_email", parameters__email_id=email.pk,
        status__in=[QueuedJob.Status.PENDING, QueuedJob.Status.RUNNING],
    ).exists()


def validate_email_reprocessing(email, actor, *, check_processing=False):
    if not (
        actor and actor.is_authenticated and actor.is_active and actor.is_staff
        and actor.has_perm("tpa.change_inboundemail")
    ):
        raise PermissionDenied("Inbound email change permission is required.")
    if not visible_inbound_emails(actor).filter(pk=email.pk).exists():
        raise PermissionDenied("This email is outside your authorized organizations.")
    if check_processing and email.processing_state == InboundEmail.State.PROCESSING:
        raise ValueError("This email is already being processed.")
    if not email.transaction_id:
        if email.ticket_id:
            raise ValueError("This email already belongs to a ticket. Continue in the ticket workspace.")
        if not can_create_tpa_transaction(actor):
            raise PermissionDenied("TPA transaction creation permission is required.")
        return
    tx = email.transaction
    if (
        tx.status not in REPROCESSABLE_STATUSES or tx.processed_at
        or tx.member_actions.filter(processed_at__isnull=False).exists()
    ):
        raise ValueError(
            f"Endorsement {tx.reference} has left intake ({tx.get_status_display()}). "
            "Reprocessing is available only during intake and correction."
        )
    if not can_edit_tpa_intake(actor, tx):
        raise PermissionDenied("You have read-only access to this endorsement. Reopen a paused ticket before reprocessing.")


def queue_email_reprocessing(email, actor):
    if not getattr(settings, "JOB_CENTER_ENABLED", True):
        raise ValueError("Enable Job Center to run inbound email reprocessing in the background.")
    with transaction.atomic():
        email = InboundEmail.objects.select_for_update().get(pk=email.pk)
        if email.transaction_id:
            email.transaction = MemberTransaction.objects.select_for_update().get(
                pk=email.transaction_id
            )
        validate_email_reprocessing(email, actor, check_processing=True)
        if email_reprocessing_pending(email):
            raise ValueError("This email is already queued for reprocessing.")
        job = enqueue(
            "tpa.reprocess_inbound_email",
            {"email_id": email.pk, "actor_id": actor.pk},
            max_attempts=1,
        )
        email.processing_state = InboundEmail.State.RECEIVED
        email.processing_stage = REPROCESS_QUEUED
        email.processing_error = ""
        email.processed_at = None
        email.save(update_fields=[
            "processing_state", "processing_stage", "processing_error",
            "processed_at", "updated_at",
        ])
        return job
