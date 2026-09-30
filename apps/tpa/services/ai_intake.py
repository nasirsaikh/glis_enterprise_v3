from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import os

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from apps.ai.models import AIExtractionProfile, AIInteraction, AIProviderConfig
from apps.ai.runtime import generate_json
from apps.tickets.models import Notification, TicketAttachment

from ..models import (
    InboundEmail,
    InboundEmailAttachment,
    MemberAction,
    MemberTransaction,
    Policy,
    SourceDocument,
    TransactionEvent,
)
from .authority import sender_is_authorized
from .document_intake import process_source_bundle
from .extraction import normalize_ai_payload, select_profile, select_provider
from .intake import import_member_spreadsheet
from .member_merge import merge_member_rows
from .prompts import profile_guidance
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
    "MEMBER_UPDATE": MemberTransaction.Type.MEMBER_UPDATE,
    "MEMBER UPDATE": MemberTransaction.Type.MEMBER_UPDATE,
    "DEMOGRAPHIC CHANGE": MemberTransaction.Type.MEMBER_UPDATE,
    "DEMOGRAPHIC UPDATE": MemberTransaction.Type.MEMBER_UPDATE,
    "MEMBER_TERMINATE": MemberTransaction.Type.MEMBER_TERMINATE,
    "MEMBER TERMINATE": MemberTransaction.Type.MEMBER_TERMINATE,
    "TERMINATION": MemberTransaction.Type.MEMBER_TERMINATE,
    "PERMANENT TERMINATION": MemberTransaction.Type.MEMBER_TERMINATE,
    "MEMBER_SUSPEND": MemberTransaction.Type.MEMBER_SUSPEND,
    "MEMBER SUSPEND": MemberTransaction.Type.MEMBER_SUSPEND,
    "TEMPORARY SUSPENSION": MemberTransaction.Type.MEMBER_SUSPEND,
    "TEMPORARY DEACTIVATION": MemberTransaction.Type.MEMBER_SUSPEND,
    "MEMBER_REACTIVATE": MemberTransaction.Type.MEMBER_REACTIVATE,
    "MEMBER REACTIVATE": MemberTransaction.Type.MEMBER_REACTIVATE,
    "REACTIVATION": MemberTransaction.Type.MEMBER_REACTIVATE,
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
        "You classify and extract group medical/member endorsement email evidence. "
        "Return JSON only. Never make sender-authorization, eligibility, premium, refund, approval or STP decisions. "
        "Extract every member row, including tables and labeled fields. Preserve leading zeros in identifiers. "
        "Read all available values before marking them missing. Never guess DOB, relationship or benefit plan. "
        "Use null when a value is unknown and list genuinely missing information. The required top-level JSON is: "
        '{"is_endorsement_request":true,"classification":"MEMBER_ADD","confidence":0.0,'
        '"policy_number":null,"transaction_type":"MEMBER_ADD","transaction_reference":null,'
        '"effective_date":null,"refund_basis":null,"temporary_until":null,"remarks":"",'
        '"summary":"","missing_information":[],"warnings":[],"source_references":[],"members":[]}. '
        "classification/transaction_type may be MEMBER_ADD, MEMBER_UPDATE, MEMBER_DELETE, MEMBER_TERMINATE, "
        "MEMBER_SUSPEND, MEMBER_REACTIVATE, POLICY_CANCEL, QUERY_REPLY, NOT_ENDORSEMENT or NEEDS_REVIEW. "
        "For deletion/cancellation, refund_basis may be FULL or PRO_RATA when explicitly stated. "
        "Each member may contain employee_id, member_id, tpa_member_id, card_number, first_name, middle_name, "
        "last_name, full_name, date_of_birth (YYYY-MM-DD), gender, relationship "
        "(PRINCIPAL/SPOUSE/CHILD/OTHER), principal_employee_id, principal_member_id, "
        "national_id, passport_number, plan_code, effective_date and confidence."
    )
    if not profile:
        return base

    return base + "\n\n" + profile_guidance(profile)


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
        "Attachment names: " + ", ".join(email.attachments.values_list("original_name", flat=True)) + "\n\n"
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
    resolved = TRANSACTION_ALIASES.get(normalized) or TRANSACTION_ALIASES.get(
        normalized.replace("_", " ")
    )
    if resolved == MemberTransaction.Type.NEW_POLICY_ENROLLMENT:
        raise ValueError(
            "Initial policy enrollment must be created from TPA → Initial Policy Enrollment. "
            "Email intake is reserved for endorsements on an enrolled policy."
        )
    return resolved


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


def extract_email_payload(email, actor=None, *, profile_override=None):
    hints = email.processing_hints or {}
    provider = None
    hinted_provider_id = hints.get("ai_provider_id")
    if hinted_provider_id:
        provider = (
            AIProviderConfig.objects.filter(
                pk=hinted_provider_id,
                is_active=True,
                allow_sensitive_data=True,
            )
            .order_by("priority", "id")
            .first()
        )
        if provider:
            capabilities = {
                str(item).strip().lower()
                for item in (provider.task_capabilities or [])
            }
            if "email_extraction" not in capabilities:
                provider = None

    provider = provider or select_provider(
        sensitive=True,
        capability="email_extraction",
    )
    if not provider:
        raise RuntimeError(
            "No active AI provider allows sensitive data and has the email_extraction capability."
        )

    hinted_policy = _resolve_policy({}, hints, email)
    product = hinted_policy.product_type if hinted_policy else "MEDICAL"
    profile = profile_override or select_profile(
        AIExtractionProfile.Task.EMAIL_EXTRACTION,
        product=product,
        transaction_type=str(hints.get("transaction_type") or ""),
    )
    prompt = _email_prompt(email, hints)
    try:
        raw, duration_ms = generate_json(
            provider,
            system_prompt=_profile_prompt(profile),
            user_prompt=prompt,
        )
        normalized = normalize_ai_payload(raw, field_aliases=profile.field_aliases if profile else None)
        if not profile_override:
            known_type = TRANSACTION_ALIASES.get(str(normalized.get("transaction_type") or "").upper())
            specialized = select_profile(AIExtractionProfile.Task.EMAIL_EXTRACTION, product=product, transaction_type=known_type or "")
            if specialized and specialized.applicable_transaction_type and (not profile or specialized.pk != profile.pk):
                profile = specialized
                raw, extra_duration = generate_json(provider, system_prompt=_profile_prompt(profile),
                    user_prompt=_email_prompt(email, {**hints, "transaction_type": known_type}))
                duration_ms += extra_duration
                normalized = normalize_ai_payload(raw, field_aliases=profile.field_aliases)
        _log_interaction(
            actor=actor,
            provider=provider,
            profile=profile,
            email=email,
            normalized=normalized,
            duration_ms=duration_ms,
            succeeded=True,
        )
        return normalized, provider, profile, raw
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


def _add_ai_members(tx, payload, *, source="email_body"):
    confidence = _confidence(payload.get("confidence"))
    return merge_member_rows(
        tx,
        payload.get("members") or [],
        source=source,
        confidence=confidence,
    )

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
    normalized = normalize_ai_payload(raw, field_aliases=profile.field_aliases if profile else None)
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
    documents = []
    attachment_map = {}

    for attachment in email.attachments.all().order_by("pk"):
        existing = tx.source_documents.filter(source_hash=attachment.sha256).first()
        if existing:
            attachment.processing_state = (
                InboundEmailAttachment.State.PROCESSED
                if existing.processed
                else InboundEmailAttachment.State.REVIEW
            )
            attachment.extracted_payload = existing.extracted_payload
            attachment.processing_error = existing.processing_error
            attachment.save(
                update_fields=[
                    "processing_state",
                    "extracted_payload",
                    "processing_error",
                    "updated_at",
                ]
            )
            continue

        ticket_attachment = _copy_attachment_to_ticket(tx, attachment, actor)
        source = SourceDocument(
            transaction=tx,
            ticket_attachment=ticket_attachment,
            original_name=attachment.original_name,
            content_type=attachment.content_type or "",
            size=attachment.size,
            document_kind="EMAIL_ATTACHMENT",
            processing_state=SourceDocument.State.RECEIVED,
            processed=False,
            source_hash=attachment.sha256,
            uploaded_by=actor,
        )
        attachment.file.open("rb")
        try:
            source.file.save(
                attachment.original_name,
                File(attachment.file),
                save=False,
            )
            source.save()
        finally:
            attachment.file.close()

        attachment.processing_state = InboundEmailAttachment.State.PROCESSING
        attachment.processing_error = ""
        attachment.save(
            update_fields=[
                "processing_state",
                "processing_error",
                "updated_at",
            ]
        )
        documents.append(source)
        attachment_map[source.pk] = attachment

    if documents:
        process_source_bundle(tx, documents, actor=actor)
        for document in documents:
            document.refresh_from_db()
            attachment = attachment_map[document.pk]
            attachment.processing_state = (
                InboundEmailAttachment.State.PROCESSED
                if document.processed
                else InboundEmailAttachment.State.REVIEW
            )
            attachment.extracted_payload = document.extracted_payload
            attachment.processing_error = document.processing_error
            attachment.save(
                update_fields=[
                    "processing_state",
                    "extracted_payload",
                    "processing_error",
                    "updated_at",
                ]
            )


def _classification_confidence(payload):
    return _confidence(payload.get("confidence"))


def _classification_minimum():
    try:
        value = Decimal(str(os.getenv("TPA_EMAIL_CLASSIFICATION_MIN_CONFIDENCE", "0.75")))
    except (InvalidOperation, TypeError, ValueError):
        value = Decimal("0.75")
    if value <= 1:
        value *= 100
    return value


def _notify_review_staff(policy, email, message):
    if not policy:
        return
    users = []
    seen = set()
    for access in policy.access_entries.filter(
        active=True,
    ).select_related("user"):
        user = access.user
        if not user or not user.is_active or user.pk in seen:
            continue
        if access.can_approve or access.can_process:
            users.append(user)
            seen.add(user.pk)
    for user in users:
        Notification.objects.create(
            user=user,
            kind="update",
            title=f"TPA email needs review: {email.subject}"[:160],
            body=str(message)[:500],
            link=f"/portal/tpa/inbound-emails/{email.pk}/",
        )


def _normalize_refund_basis(value):
    normalized = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "FULL": MemberTransaction.RefundBasis.FULL,
        "FULL_REFUND": MemberTransaction.RefundBasis.FULL,
        "PRO_RATA": MemberTransaction.RefundBasis.PRO_RATA,
        "PRORATA": MemberTransaction.RefundBasis.PRO_RATA,
        "PRO_RATA_REFUND": MemberTransaction.RefundBasis.PRO_RATA,
    }
    return aliases.get(normalized, MemberTransaction.RefundBasis.NONE)


def process_inbound_email(email, actor):
    if email.transaction_id and email.processing_state == InboundEmail.State.PROCESSED:
        return email.transaction

    email.processing_state = InboundEmail.State.PROCESSING
    email.processing_stage = "CLASSIFICATION"
    email.processing_error = ""
    email.save(
        update_fields=[
            "processing_state",
            "processing_stage",
            "processing_error",
            "updated_at",
        ]
    )

    try:
        payload, provider, profile, raw_ai_output = extract_email_payload(
            email,
            actor=actor,
        )
        email.raw_ai_output = raw_ai_output
        email.ai_provider_name = provider.name or provider.provider
        email.ai_model_name = provider.model_name or ""
        email.save(
            update_fields=[
                "raw_ai_output",
                "ai_provider_name",
                "ai_model_name",
                "updated_at",
            ]
        )
        classification = str(
            payload.get("classification")
            or payload.get("transaction_type")
            or ""
        ).strip().upper()
        confidence = _classification_confidence(payload)
        email.classification = classification
        email.classification_confidence = confidence
        email.ai_extracted_payload = payload
        email.ai_confidence = confidence

        is_endorsement = payload.get("is_endorsement_request")
        if is_endorsement is False or classification in {
            "NOT_ENDORSEMENT",
            "UNRELATED",
            "IGNORED",
        }:
            email.processing_state = InboundEmail.State.IGNORED
            email.processing_stage = "CLASSIFIED"
            email.processed_at = timezone.now()
            email.processing_error = ""
            email.save(
                update_fields=[
                    "raw_ai_output",
                    "ai_extracted_payload",
                    "ai_confidence",
                    "classification",
                    "classification_confidence",
                    "processing_state",
                    "processing_stage",
                    "processing_error",
                    "processed_at",
                    "updated_at",
                ]
            )
            return None

        if (
            is_endorsement is None
            or classification in {"NEEDS_REVIEW", "UNCERTAIN"}
            or confidence is None
            or confidence < _classification_minimum()
        ):
            email.processing_state = InboundEmail.State.REVIEW
            email.processing_stage = "CLASSIFICATION"
            email.processing_error = (
                "Email classification is incomplete or below the configured confidence threshold."
            )
            email.save(
                update_fields=[
                    "raw_ai_output",
                    "ai_extracted_payload",
                    "ai_confidence",
                    "classification",
                    "classification_confidence",
                    "processing_state",
                    "processing_stage",
                    "processing_error",
                    "updated_at",
                ]
            )
            return None

        if classification == "QUERY_REPLY":
            email.processing_state = InboundEmail.State.REVIEW
            email.processing_stage = "QUERY_MATCH"
            email.processing_error = (
                "Email was classified as a reply/query. Review and link it to the "
                "existing endorsement conversation if automatic reference matching is unavailable."
            )
            email.save(
                update_fields=[
                    "raw_ai_output",
                    "ai_extracted_payload",
                    "ai_confidence",
                    "classification",
                    "classification_confidence",
                    "processing_state",
                    "processing_stage",
                    "processing_error",
                    "updated_at",
                ]
            )
            return None

        hints = email.processing_hints or {}
        policy = _resolve_policy(payload, hints, email)
        if not policy:
            email.processing_state = InboundEmail.State.REVIEW
            email.processing_stage = "POLICY_MATCH"
            email.processing_error = (
                "No unique policy could be resolved from the email evidence."
            )
            email.save(
                update_fields=[
                    "raw_ai_output",
                    "ai_extracted_payload",
                    "ai_confidence",
                    "classification",
                    "classification_confidence",
                    "processing_state",
                    "processing_stage",
                    "processing_error",
                    "updated_at",
                ]
            )
            return None

        transaction_type = _resolve_transaction_type(payload, hints)
        if not transaction_type:
            email.processing_state = InboundEmail.State.REVIEW
            email.processing_stage = "CLASSIFICATION"
            email.processing_error = "No supported endorsement type could be resolved."
            email.save(
                update_fields=[
                    "raw_ai_output",
                    "ai_extracted_payload",
                    "ai_confidence",
                    "classification",
                    "classification_confidence",
                    "processing_state",
                    "processing_stage",
                    "processing_error",
                    "updated_at",
                ]
            )
            return None

        if policy.status != Policy.Status.ACTIVE:
            email.processing_state = InboundEmail.State.REVIEW
            email.processing_stage = "POLICY_MATCH"
            email.processing_error = (
                f"Policy {policy.policy_number} is {policy.get_status_display()} and "
                "cannot be processed automatically."
            )
            email.save(
                update_fields=[
                    "processing_state",
                    "processing_stage",
                    "processing_error",
                    "updated_at",
                ]
            )
            _notify_review_staff(policy, email, email.processing_error)
            return None

        authorized, authority, reason = sender_is_authorized(
            email,
            policy,
            transaction_type,
            actor=actor,
        )
        if not authorized:
            email.processing_state = InboundEmail.State.UNAUTHORIZED
            email.processing_stage = "SENDER_AUTHORITY"
            email.processing_error = reason
            email.save(
                update_fields=[
                    "raw_ai_output",
                    "ai_extracted_payload",
                    "ai_confidence",
                    "classification",
                    "classification_confidence",
                    "processing_state",
                    "processing_stage",
                    "processing_error",
                    "updated_at",
                ]
            )
            _notify_review_staff(policy, email, reason)
            return None

        effective_date = _as_date(
            hints.get("effective_date") or payload.get("effective_date"),
            fallback=email.received_at.date(),
        )
        refund_basis = _normalize_refund_basis(
            hints.get("refund_basis") or payload.get("refund_basis")
        )

        with transaction.atomic():
            if email.transaction_id:
                tx = email.transaction
            else:
                requester = (
                    authority.user
                    if authority is not None and authority.user_id
                    else actor
                )
                tx = MemberTransaction.objects.create(
                    sponsor=policy.sponsor,
                    insurer=policy.insurance_company,
                    policy=policy,
                    transaction_type=transaction_type,
                    classification=classification or transaction_type,
                    classification_confidence=confidence,
                    refund_basis=refund_basis,
                    expected_reactivation_date=(
                        _as_date(payload.get("temporary_until"))
                        if transaction_type == MemberTransaction.Type.MEMBER_SUSPEND
                        and payload.get("temporary_until")
                        else None
                    ),
                    physical_card_required=(
                        policy.physical_card_required
                        and transaction_type == MemberTransaction.Type.MEMBER_ADD
                    ),
                    source=MemberTransaction.Source.EMAIL,
                    effective_date=effective_date,
                    requester=requester,
                    requester_organization=(
                        authority.organization
                        if authority is not None
                        else policy.sponsor
                    ),
                    status=MemberTransaction.Status.DRAFT,
                    submitted_at=timezone.now(),
                    ai_summary=payload.get("summary") or email.subject,
                    ai_extraction_status="EXTRACTED",
                    remarks=payload.get("remarks") or "",
                    metadata={
                        "inbound_email_id": email.pk,
                        "ai_provider_id": provider.pk,
                        "ai_profile_id": profile.pk if profile else None,
                        "email_authority_id": authority.pk if authority else None,
                        "missing_information": payload.get("missing_information") or [],
                        "warnings": payload.get("warnings") or [],
                        "source_references": payload.get("source_references") or [],
                        "temporary_until": payload.get("temporary_until"),
                    },
                )
                email.transaction = tx

            _add_ai_members(
                tx,
                payload,
                source=f"email:{email.pk}:body",
            )
            create_ticket_for_transaction(tx, actor=actor)
            TransactionEvent.objects.bulk_create(
                [
                    TransactionEvent(
                        transaction=tx,
                        actor=actor,
                        event_type="office365_email_received" if email.provider == "office365_graph" else "email_received",
                        summary=f"Inbound email received: {email.subject or '(No subject)'}",
                        details={
                            "inbound_email_id": email.pk,
                            "provider": email.provider,
                            "sender": email.sender,
                            "received_at": email.received_at.isoformat(),
                        },
                    ),
                    TransactionEvent(
                        transaction=tx,
                        actor=actor,
                        event_type="email_classified",
                        summary=f"Email classified as {classification or transaction_type}",
                        details={"confidence": str(confidence) if confidence is not None else None},
                    ),
                    TransactionEvent(
                        transaction=tx,
                        actor=actor,
                        event_type="sender_authority_checked",
                        summary="Sender authority validated",
                        details={"authority_id": authority.pk if authority else None},
                    ),
                    TransactionEvent(
                        transaction=tx,
                        actor=actor,
                        event_type="policy_matched",
                        summary=f"Policy matched: {policy.policy_number}",
                    ),
                ]
            )

        email.processing_stage = "ATTACHMENT_EXTRACTION"
        email.save(update_fields=["processing_stage", "updated_at"])
        _process_attachments(tx, email, actor)

        email.processing_stage = "VALIDATION"
        email.save(update_fields=["processing_stage", "updated_at"])
        run_validation(tx, actor=actor)
        tx.refresh_from_db()

        attachment_review = email.attachments.exclude(
            processing_state=InboundEmailAttachment.State.PROCESSED
        ).exists()

        email.processing_state = (
            InboundEmail.State.REVIEW
            if attachment_review
            else InboundEmail.State.PROCESSED
        )
        email.processing_stage = "COMPLETE" if not attachment_review else "EVIDENCE_REVIEW"
        email.processing_error = (
            "One or more email attachments require review."
            if attachment_review
            else ""
        )
        email.processed_at = timezone.now()
        email.transaction = tx
        email.save(
            update_fields=[
                "raw_ai_output",
                "ai_extracted_payload",
                "ai_confidence",
                "classification",
                "classification_confidence",
                "processing_state",
                "processing_stage",
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
