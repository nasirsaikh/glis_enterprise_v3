from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from apps.ai.models import AIExtractionProfile, AIInteraction
from apps.ai.runtime import generate_json
from apps.tickets.models import TicketAttachment

from ..models import (
    InboundEmail,
    InboundEmailAttachment,
    MemberAction,
    MemberTransaction,
    Policy,
    SourceDocument,
)
from .extraction import normalize_ai_payload, select_profile, select_provider
from .intake import import_member_spreadsheet
from .ticketing import create_ticket_for_transaction
from .workflow import run_validation


TRANSACTION_ALIASES = {
    "NEW_POLICY_ENROLLMENT": MemberTransaction.Type.NEW_POLICY_ENROLLMENT,
    "NEW ENROLLMENT": MemberTransaction.Type.NEW_POLICY_ENROLLMENT,
    "ENROLLMENT": MemberTransaction.Type.NEW_POLICY_ENROLLMENT,
    "MEMBER_ADD": MemberTransaction.Type.MEMBER_ADD,
    "MEMBER ADD": MemberTransaction.Type.MEMBER_ADD,
    "MEMBER ADDITION": MemberTransaction.Type.MEMBER_ADD,
    "ADD": MemberTransaction.Type.MEMBER_ADD,
    "MEMBER_TERMINATE": MemberTransaction.Type.MEMBER_TERMINATE,
    "MEMBER TERMINATE": MemberTransaction.Type.MEMBER_TERMINATE,
    "TERMINATION": MemberTransaction.Type.MEMBER_TERMINATE,
    "MEMBER_DELETE": MemberTransaction.Type.MEMBER_DELETE,
    "MEMBER DELETE": MemberTransaction.Type.MEMBER_DELETE,
    "DELETE": MemberTransaction.Type.MEMBER_DELETE,
    "POLICY_CANCEL": MemberTransaction.Type.POLICY_CANCEL,
    "POLICY CANCEL": MemberTransaction.Type.POLICY_CANCEL,
    "CANCELLATION": MemberTransaction.Type.POLICY_CANCEL,
}


def _as_date(value, fallback=None):
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
    return fallback


def _confidence(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if number <= 1:
        number *= 100
    return number.quantize(Decimal("0.01"))


def _member_payload(row):
    data = {key: value for key, value in (row or {}).items() if value not in (None, "")}
    full_name = str(data.get("full_name") or "").strip()
    if full_name and not data.get("first_name"):
        parts = full_name.split()
        data["first_name"] = parts[0]
        data["last_name"] = parts[-1] if len(parts) > 1 else ""
        if len(parts) > 2:
            data["middle_name"] = " ".join(parts[1:-1])
    data.pop("confidence", None)
    return data


def _profile_prompt(profile):
    base = (
        "You extract group medical/member endorsement data. "
        "Return JSON only. Never make eligibility, premium, approval or STP decisions. "
        "Use null when a value is unknown. The required top-level JSON is: "
        '{"policy_number":null,"transaction_type":null,"effective_date":null,'
        '"summary":"","confidence":0.0,"members":[]}. '
        "Each member may contain employee_id, member_id, first_name, middle_name, "
        "last_name, full_name, date_of_birth (YYYY-MM-DD), gender, relationship "
        "(PRINCIPAL/SPOUSE/CHILD/OTHER), principal_employee_id, principal_member_id, "
        "national_id, passport_number, plan_code, effective_date and confidence."
    )
    if not profile:
        return base

    examples = []
    for example in profile.examples.filter(is_active=True)[:5]:
        examples.append(
            f"Example input:\n{example.input_text}\nExpected JSON:\n{example.expected_output}"
        )
    return "\n\n".join(
        part
        for part in [
            base,
            profile.system_prompt,
            profile.instructions,
            "\n\n".join(examples),
        ]
        if part
    )


def _email_prompt(email, hints):
    hint_policy = hints.get("policy_number") or ""
    hint_type = hints.get("transaction_type") or ""
    hint_date = hints.get("effective_date") or ""
    return (
        f"Policy Number: {hint_policy}\n"
        f"Transaction Type: {hint_type}\n"
        f"Effective Date: {hint_date}\n"
        f"Subject: {email.subject}\n"
        f"From: {email.sender}\n"
        f"To: {email.recipient}\n\n"
        "Email body:\n"
        f"{email.body_text or ''}"
    )


def _document_prompt(email, attachment, hints):
    return (
        "Extract member endorsement data from this image attachment and merge the "
        "email context where useful.\n"
        f"Policy Number: {hints.get('policy_number') or ''}\n"
        f"Transaction Type: {hints.get('transaction_type') or ''}\n"
        f"Effective Date: {hints.get('effective_date') or ''}\n"
        f"Email Subject: {email.subject}\n"
        f"Attachment: {attachment.original_name}"
    )


def _resolve_policy(payload, hints, email):
    policy_id = hints.get("policy_id")
    if policy_id:
        policy = Policy.objects.filter(pk=policy_id).first()
        if policy:
            return policy

    policy_number = str(payload.get("policy_number") or "").strip()
    if policy_number:
        policy = Policy.objects.filter(policy_number__iexact=policy_number).first()
        if policy:
            return policy

    haystack = f"{email.subject}\n{email.body_text}".lower()
    matches = [
        policy
        for policy in Policy.objects.filter(status=Policy.Status.ACTIVE)
        if policy.policy_number.lower() in haystack
    ]
    return matches[0] if len(matches) == 1 else None


def _resolve_transaction_type(payload, hints):
    value = hints.get("transaction_type") or payload.get("transaction_type") or ""
    normalized = str(value).strip().upper().replace("-", " ")
    return TRANSACTION_ALIASES.get(normalized) or TRANSACTION_ALIASES.get(
        normalized.replace("_", " ")
    )


def _log_interaction(*, actor, provider, profile, email, normalized, duration_ms, succeeded, error_code=""):
    return AIInteraction.objects.create(
        user=actor,
        purpose="tpa_email_extraction",
        provider=f"{provider.provider}:{provider.model_name or provider.name}",
        request_summary={
            "inbound_email_id": email.pk,
            "subject": email.subject,
            "profile_id": profile.pk if profile else None,
            "provider_config_id": provider.pk,
        },
        response=normalized if succeeded else {},
        confidence=(
            (_confidence(normalized.get("confidence")) or Decimal("0")) / Decimal("100")
            if succeeded
            else None
        ),
        duration_ms=max(duration_ms, 0),
        succeeded=succeeded,
        error_code=error_code,
    )


def extract_email_payload(email, actor=None):
    hints = email.processing_hints or {}
    provider = select_provider(sensitive=True, capability="email_extraction")
    if not provider:
        raise RuntimeError(
            "No active AI provider allows sensitive data and has the email_extraction capability."
        )

    profile = select_profile(
        AIExtractionProfile.Task.EMAIL_EXTRACTION,
        product="MEDICAL",
        transaction_type=str(hints.get("transaction_type") or ""),
    )
    prompt = _email_prompt(email, hints)
    try:
        raw, duration_ms = generate_json(
            provider,
            system_prompt=_profile_prompt(profile),
            user_prompt=prompt,
        )
        normalized = normalize_ai_payload(raw)
        _log_interaction(
            actor=actor,
            provider=provider,
            profile=profile,
            email=email,
            normalized=normalized,
            duration_ms=duration_ms,
            succeeded=True,
        )
        return normalized, provider, profile
    except Exception as exc:
        _log_interaction(
            actor=actor,
            provider=provider,
            profile=profile,
            email=email,
            normalized={},
            duration_ms=0,
            succeeded=False,
            error_code=exc.__class__.__name__[:50],
        )
        raise


def _add_ai_members(tx, payload):
    next_row = (
        tx.member_actions.order_by("-row_number")
        .values_list("row_number", flat=True)
        .first()
        or 0
    )
    created = []
    for offset, row in enumerate(payload.get("members") or [], start=1):
        created.append(
            MemberAction.objects.create(
                transaction=tx,
                action=tx.transaction_type,
                row_number=next_row + offset,
                extracted_data=_member_payload(row),
                extraction_confidence=_confidence(row.get("confidence"))
                or _confidence(payload.get("confidence")),
            )
        )
    return created


def _copy_attachment_to_ticket(tx, attachment, actor):
    if not tx.ticket_id:
        return None
    attachment.file.open("rb")
    try:
        ticket_attachment = TicketAttachment(
            ticket=tx.ticket,
            uploaded_by=actor,
            original_name=attachment.original_name,
            content_type=attachment.content_type or "application/octet-stream",
            size=attachment.size,
            is_restricted=True,
            scan_status="clean",
            source_field="tpa_inbound_email",
        )
        ticket_attachment.file.save(
            attachment.original_name,
            File(attachment.file),
            save=False,
        )
        ticket_attachment.save()
        return ticket_attachment
    finally:
        attachment.file.close()


def _process_image_attachment(tx, email, attachment, actor, hints):
    provider = select_provider(
        vision=True,
        sensitive=True,
        capability="document_extraction",
    )
    if not provider:
        raise RuntimeError(
            "No active vision AI provider allows sensitive data and has the document_extraction capability."
        )
    profile = select_profile(
        AIExtractionProfile.Task.DOCUMENT_EXTRACTION,
        product=tx.policy.product_type,
        transaction_type=tx.transaction_type,
    )
    attachment.file.open("rb")
    try:
        raw_bytes = attachment.file.read()
    finally:
        attachment.file.close()

    raw, duration_ms = generate_json(
        provider,
        system_prompt=_profile_prompt(profile),
        user_prompt=_document_prompt(email, attachment, hints),
        images=[
            {
                "bytes": raw_bytes,
                "mime_type": attachment.content_type or "image/jpeg",
            }
        ],
    )
    normalized = normalize_ai_payload(raw)
    _add_ai_members(tx, normalized)
    _log_interaction(
        actor=actor,
        provider=provider,
        profile=profile,
        email=email,
        normalized=normalized,
        duration_ms=duration_ms,
        succeeded=True,
    )
    attachment.extracted_payload = normalized
    attachment.processing_state = InboundEmailAttachment.State.PROCESSED
    attachment.processing_error = ""
    attachment.save(
        update_fields=[
            "extracted_payload",
            "processing_state",
            "processing_error",
            "updated_at",
        ]
    )


def _process_attachments(tx, email, actor):
    for attachment in email.attachments.all().order_by("pk"):
        if attachment.processing_state == InboundEmailAttachment.State.PROCESSED:
            continue
        attachment.processing_state = InboundEmailAttachment.State.PROCESSING
        attachment.processing_error = ""
        attachment.save(
            update_fields=["processing_state", "processing_error", "updated_at"]
        )
        ticket_attachment = _copy_attachment_to_ticket(tx, attachment, actor)
        suffix = attachment.original_name.lower().rsplit(".", 1)[-1] if "." in attachment.original_name else ""

        try:
            if suffix in {"csv", "xlsx"}:
                attachment.file.open("rb")
                try:
                    actions = import_member_spreadsheet(tx, attachment.file, actor=actor)
                finally:
                    attachment.file.close()
                attachment.extracted_payload = {"rows_created": len(actions)}
                attachment.processing_state = InboundEmailAttachment.State.PROCESSED
                attachment.save(
                    update_fields=[
                        "extracted_payload",
                        "processing_state",
                        "updated_at",
                    ]
                )
            elif (attachment.content_type or "").startswith("image/"):
                _process_image_attachment(
                    tx,
                    email,
                    attachment,
                    actor,
                    email.processing_hints or {},
                )
            else:
                attachment.processing_state = InboundEmailAttachment.State.REVIEW
                attachment.processing_error = (
                    "Attachment retained for audit. Automated extraction currently supports "
                    "CSV/XLSX and vision-capable image files."
                )
                attachment.save(
                    update_fields=[
                        "processing_state",
                        "processing_error",
                        "updated_at",
                    ]
                )

            if ticket_attachment:
                SourceDocument.objects.get_or_create(
                    transaction=tx,
                    ticket_attachment=ticket_attachment,
                    defaults={
                        "original_name": attachment.original_name,
                        "document_kind": "EMAIL_ATTACHMENT",
                        "extraction_method": (
                            "STRUCTURED_IMPORT"
                            if suffix in {"csv", "xlsx"}
                            else "VISION_AI"
                            if (attachment.content_type or "").startswith("image/")
                            else "MANUAL_REVIEW"
                        ),
                        "processed": attachment.processing_state
                        == InboundEmailAttachment.State.PROCESSED,
                        "processing_error": attachment.processing_error,
                        "extracted_payload": attachment.extracted_payload,
                        "uploaded_by": actor,
                    },
                )
        except Exception as exc:
            attachment.processing_state = InboundEmailAttachment.State.REVIEW
            attachment.processing_error = str(exc)
            attachment.save(
                update_fields=[
                    "processing_state",
                    "processing_error",
                    "updated_at",
                ]
            )


def process_inbound_email(email, actor):
    if email.transaction_id and email.processing_state == InboundEmail.State.PROCESSED:
        return email.transaction

    email.processing_state = InboundEmail.State.PROCESSING
    email.processing_error = ""
    email.save(
        update_fields=["processing_state", "processing_error", "updated_at"]
    )

    try:
        payload, provider, profile = extract_email_payload(email, actor=actor)
        hints = email.processing_hints or {}
        policy = _resolve_policy(payload, hints, email)
        if not policy:
            raise ValueError(
                "AI could not resolve an active policy. Add/select the policy hint and process again."
            )

        transaction_type = _resolve_transaction_type(payload, hints)
        if not transaction_type:
            raise ValueError(
                "AI could not resolve the TPA transaction type. Add/select the transaction type hint and process again."
            )

        effective_date = _as_date(
            hints.get("effective_date") or payload.get("effective_date"),
            fallback=email.received_at.date(),
        )

        with transaction.atomic():
            if email.transaction_id:
                tx = email.transaction
            else:
                tx = MemberTransaction.objects.create(
                    sponsor=policy.sponsor,
                    insurer=policy.insurance_company,
                    policy=policy,
                    transaction_type=transaction_type,
                    source=MemberTransaction.Source.EMAIL,
                    effective_date=effective_date,
                    requester=actor,
                    requester_organization=policy.sponsor,
                    status=MemberTransaction.Status.PENDING_VALIDATION,
                    submitted_at=timezone.now(),
                    ai_summary=payload.get("summary") or email.subject,
                    ai_extraction_status="EXTRACTED",
                    metadata={
                        "inbound_email_id": email.pk,
                        "ai_provider_id": provider.pk,
                        "ai_profile_id": profile.pk if profile else None,
                    },
                )
                email.transaction = tx

            if not tx.member_actions.exists():
                _add_ai_members(tx, payload)

            create_ticket_for_transaction(tx, actor=actor)

        _process_attachments(tx, email, actor)
        run_validation(tx, actor=actor)
        tx.refresh_from_db()

        attachment_review = email.attachments.exclude(
            processing_state=InboundEmailAttachment.State.PROCESSED
        ).exists()

        email.ai_extracted_payload = payload
        email.ai_confidence = _confidence(payload.get("confidence"))
        email.processing_state = (
            InboundEmail.State.REVIEW
            if attachment_review
            else InboundEmail.State.PROCESSED
        )
        email.processing_error = (
            "One or more email attachments require review."
            if attachment_review
            else ""
        )
        email.processed_at = timezone.now()
        email.transaction = tx
        email.save(
            update_fields=[
                "ai_extracted_payload",
                "ai_confidence",
                "processing_state",
                "processing_error",
                "processed_at",
                "transaction",
                "updated_at",
            ]
        )
        return tx
    except Exception as exc:
        email.processing_state = InboundEmail.State.REVIEW
        email.processing_error = str(exc)
        email.save(
            update_fields=[
                "processing_state",
                "processing_error",
                "updated_at",
            ]
        )
        raise
