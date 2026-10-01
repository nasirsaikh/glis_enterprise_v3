from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.job_center.registry import register_job
from apps.tpa.services.mailbox import poll_inbound_mailbox


@register_job("tpa.poll_inbound_mailbox")
def poll_tpa_inbound_mailbox(actor_id=None, limit=None, process_ai=None):
    User = get_user_model()
    actor = None
    if actor_id:
        actor = User.objects.filter(pk=actor_id, is_active=True).first()
    if actor is None:
        configured_actor = str(
            getattr(settings, "TPA_MAIL_ACTOR_USERNAME", "") or ""
        ).strip()
        if configured_actor:
            actor = User.objects.filter(
                is_active=True,
            ).filter(
                username__iexact=configured_actor
            ).first() or User.objects.filter(
                is_active=True,
                email__iexact=configured_actor,
            ).first()
    if actor is None:
        actor = (
            User.objects.filter(is_superuser=True, is_active=True)
            .order_by("pk")
            .first()
        )
    if actor is None:
        raise RuntimeError(
            "TPA mailbox polling needs an active actor. Configure "
            "TPA_MAIL_ACTOR_USERNAME/actor_id or create an active superuser."
        )
    return poll_inbound_mailbox(
        actor=actor,
        limit=(max(int(limit), 1) if limit not in (None, "") else None),
        process_ai=process_ai,
    )


@register_job("tpa.reprocess_inbound_email")
def reprocess_tpa_inbound_email(email_id, actor_id):
    from apps.tpa.models import InboundEmail
    from apps.tpa.services.ai_intake import process_inbound_email
    from apps.tpa.services.email_reprocessing import REPROCESS_QUEUED

    email = InboundEmail.objects.get(pk=email_id)
    if email.processing_stage != REPROCESS_QUEUED:
        return {"email_id": email.pk, "skipped": True, "reason": "Email is no longer queued."}
    actor = get_user_model().objects.filter(pk=actor_id, is_active=True).first()
    try:
        tx = process_inbound_email(email, actor, force=True)
    except Exception as exc:
        # Permission/status failures before extraction also need visible feedback.
        InboundEmail.objects.filter(pk=email.pk, processing_stage=REPROCESS_QUEUED).update(
            processing_state=InboundEmail.State.REVIEW,
            processing_stage="REPROCESS_BLOCKED",
            processing_error=str(exc),
            updated_at=timezone.now(),
        )
        raise
    email.refresh_from_db()
    return {
        "email_id": email.pk,
        "processing_state": email.processing_state,
        "processing_stage": email.processing_stage,
        "transaction_reference": tx.reference if tx else None,
        "processing_error": email.processing_error,
    }
