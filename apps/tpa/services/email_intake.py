from django.db import transaction

from ..models import InboundEmail


@transaction.atomic
def register_inbound_email(
    *,
    provider,
    provider_message_id,
    sender,
    recipient,
    subject="",
    received_at,
    body_text="",
    attachment_metadata=None,
    created_by=None,
    processing_hints=None,
):
    email, created = InboundEmail.objects.get_or_create(
        provider=provider or "",
        provider_message_id=provider_message_id,
        defaults={
            "sender": sender,
            "recipient": recipient,
            "subject": subject or "",
            "received_at": received_at,
            "body_text": body_text or "",
            "attachment_metadata": attachment_metadata or [],
            "created_by": created_by,
            "processing_hints": processing_hints or {},
        },
    )
    return email, created


def mark_email_for_review(email, reason):
    email.processing_state = InboundEmail.State.REVIEW
    email.processing_error = reason
    email.save(
        update_fields=[
            "processing_state",
            "processing_error",
            "updated_at",
        ]
    )
    return email
