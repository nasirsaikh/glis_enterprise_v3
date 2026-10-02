from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
import json
import re
from html import unescape

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
from .access import visible_policies
from .document_intake import process_source_bundle
from .email_reprocessing import validate_email_reprocessing
from .email_evidence import html_to_text, member_rows_from_html
from .extraction import canonical_member, normalize_ai_payload, select_profile, select_provider
from .intake import import_member_spreadsheet
from .member_merge import merge_member_rows
from .prompts import profile_guidance
from .schemas import EmailEvidence
from .ticketing import create_ticket_for_transaction
from .workflow import run_validation


TRANSACTION_ALIASES = {
    "CLAIM": "CLAIM",
    "CLAIM REQUEST": "CLAIM",
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
        "MEMBER_SUSPEND, MEMBER_REACTIVATE, POLICY_CANCEL, NEW_POLICY_ENROLLMENT, CLAIM, QUERY_REPLY, NOT_ENDORSEMENT or NEEDS_REVIEW. "
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
        f"Email received date (resolve today/tomorrow against this date): {timezone.localdate(email.received_at).isoformat()}\n"
        f"Subject: {email.subject}\n"
        f"From: {email.sender}\n"
        f"To: {email.recipient}\n\n"
        "Attachment names: " + ", ".join(email.attachments.values_list("original_name", flat=True)) + "\n\n"
        "Email body:\n"
        f"{html_to_text(email.body_html) or unescape(email.body_text or '')}"
        + "\n\nMember table records (preserve empty cells and identifiers):\n"
        + json.dumps(member_rows_from_html(email.body_html), ensure_ascii=False)
    )


def _recover_explicit_email_header(email, payload, hints):
    """Recover clear request headers independently of member JSON mapping.

    Contradictory/negative requests and multiple policy/type matches stay with
    the classifier for review. This never supplies sender authority or approval.
    """
    text = f"{email.subject}\n{html_to_text(email.body_html) or unescape(email.body_text or '')}"
    # The request precedes the member table and any quoted correspondence.
    header = re.split(r"employee[_ ](?:id|no)|\bFrom:\s|\bSent:\s", text, maxsplit=1, flags=re.I)[0][:3000]
    if re.search(r"\b(?:do not|don't|not to|should not|if|whether)\b", header, re.I):
        return payload
    patterns = {
        "MEMBER_ADD": r"\b(?:addition|add (?:new )?members?)\b",
        "MEMBER_DELETE": r"\b(?:deletion|delete members?|remove members?)\b",
        "MEMBER_TERMINATE": r"\b(?:termination|terminate members?)\b",
        "MEMBER_SUSPEND": r"\b(?:suspension|suspend members?|temporary deactivation)\b",
        "MEMBER_REACTIVATE": r"\b(?:reactivation|reactivate members?)\b",
        "MEMBER_UPDATE": r"\b(?:demographic (?:change|update)|update member details)\b",
        "POLICY_CANCEL": r"\b(?:policy cancellation|cancel (?:the )?policy)\b",
    }
    matches = [key for key, pattern in patterns.items() if re.search(pattern, header, re.I)]
    policy_matches = [p for p in Policy.objects.filter(status=Policy.Status.ACTIVE)
                      if re.search(r"(?<![\w/-])" + re.escape(p.policy_number) + r"(?![\w/-])", header, re.I)]
    if len(matches) != 1 or len(policy_matches) != 1 or payload.get("is_endorsement_request") is False:
        return payload
    request_type = matches[0]
    ai_type = str(payload.get("transaction_type") or payload.get("classification") or "").upper()
    if ai_type not in {"", "NEEDS_REVIEW", "UNCERTAIN", request_type}:
        return payload
    if hints.get("transaction_type") and hints["transaction_type"] != request_type:
        return payload
    explicit_policy = policy_matches[0]
    if hints.get("policy_id") and str(hints["policy_id"]) != str(explicit_policy.pk):
        return payload
    if any(str(number).strip().casefold() != explicit_policy.policy_number.casefold()
           for number in (payload.get("policy_number"), hints.get("policy_number")) if number):
        return payload
    complete_ai_header = (payload.get("is_endorsement_request") is True and ai_type == request_type
                          and payload.get("policy_number") == explicit_policy.policy_number)
    payload = {**payload, "is_endorsement_request": True,
               "policy_number": explicit_policy.policy_number,
               "transaction_type": request_type, "classification": request_type}
    if not complete_ai_header:
        payload["classification_source"] = "EXPLICIT_EMAIL_HEADER"
    if not payload.get("effective_date"):
        relative = re.search(r"\beffective(?:\s+(?:from|on))?\s+(today|tomorrow)\b", header, re.I)
        if relative:
            payload["effective_date"] = (timezone.localdate(email.received_at) + timedelta(
                days=int(relative.group(1).lower() == "tomorrow")
            )).isoformat()
        else:
            explicit_date = re.search(r"\beffective(?:\s+(?:from|on|date))?\s*[:=-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", header, re.I)
            value = _as_date(explicit_date.group(1)) if explicit_date else None
            if value:
                payload["effective_date"] = value.isoformat()
    return payload


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
                supports_vision=False,
            )
            .exclude(model_name__icontains="glm-ocr")
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
        vision=False,
        sensitive=True,
        capability="email_extraction",
    )
    if not provider:
        raise RuntimeError(
            "No active text AI provider allows sensitive data and has the email_extraction capability. "
            "Use a text model such as qwen2.5:7b with Supports vision disabled; GLM-OCR is only for document OCR."
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
        duration_ms = 0
        for attempt in range(2):
            try:
                raw, elapsed = generate_json(
                    provider, system_prompt=_profile_prompt(profile),
                    user_prompt=prompt if attempt == 0 else prompt + "\nThe previous extraction did not match the schema. Return every available field as JSON and leave unknown values null.",
                    response_schema=EmailEvidence.model_json_schema(),
                )
                duration_ms += elapsed
                normalized = normalize_ai_payload(raw, field_aliases=profile.field_aliases if profile else None, require_members=False)
                break
            except (TypeError, ValueError):
                if attempt == 1:
                    raise
        if not profile_override:
            known_type = TRANSACTION_ALIASES.get(str(normalized.get("transaction_type") or "").upper())
            specialized = select_profile(AIExtractionProfile.Task.EMAIL_EXTRACTION, product=product, transaction_type=known_type or "")
            if specialized and specialized.applicable_transaction_type and (not profile or specialized.pk != profile.pk):
                profile = specialized
                raw, extra_duration = generate_json(provider, system_prompt=_profile_prompt(profile),
                    user_prompt=_email_prompt(email, {**hints, "transaction_type": known_type}),
                    response_schema=EmailEvidence.model_json_schema())
                duration_ms += extra_duration
                normalized = normalize_ai_payload(raw, field_aliases=profile.field_aliases, require_members=False)
        table_rows = member_rows_from_html(email.body_html)
        if table_rows:
            normalized["members"] = [canonical_member(row, profile.field_aliases if profile else None) for row in table_rows]
        normalized = _recover_explicit_email_header(email, normalized, hints)
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
        response_schema=EmailEvidence.model_json_schema(),
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


def _process_attachments(tx, email, actor, *, reprocess=False):
    documents = []
    attachment_map = {}

    for attachment in email.attachments.all().order_by("pk"):
        existing = tx.source_documents.filter(source_hash=attachment.sha256).first()
        if existing and not reprocess and existing.processed and existing.processing_state == SourceDocument.State.PROCESSED:
            attachment.processing_state = InboundEmailAttachment.State.PROCESSED
            attachment.extracted_payload = existing.extracted_payload
            attachment.processing_error = ""
            attachment.save(update_fields=[
                "processing_state", "extracted_payload", "processing_error", "updated_at",
            ])
            continue

        if existing:
            source = existing
            source.processed = False
            source.save(update_fields=["processed", "updated_at"])
        else:
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
                if document.processed and document.processing_state == SourceDocument.State.PROCESSED
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


def process_inbound_email(email, actor, *, force=False):
    # Claim the latest record so concurrent admin/scheduler requests cannot
    # both start extraction or create an endorsement for the same email.
    with transaction.atomic():
        InboundEmail.objects.select_for_update().get(pk=email.pk)
        email.refresh_from_db()
        if not force and (email.transaction_id or email.ticket_id) and email.processing_state == InboundEmail.State.PROCESSED:
            return email.transaction if email.transaction_id else email.ticket
        if force:
            validate_email_reprocessing(email, actor)
        if email.processing_state == InboundEmail.State.PROCESSING:
            raise ValueError("This email is already being processed.")
        email.processing_state = InboundEmail.State.PROCESSING
        email.processing_stage = "CLASSIFICATION"
        email.processing_error = ""
        email.processed_at = None
        email.save(update_fields=[
            "processing_state", "processing_stage", "processing_error",
            "processed_at", "updated_at",
        ])

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
        if (is_endorsement is False and classification not in {"CLAIM", "NEW_POLICY_ENROLLMENT"}) or classification in {
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

        classification_is_complete = (
            (is_endorsement is True or classification in {"CLAIM", "NEW_POLICY_ENROLLMENT"})
            and classification not in {"", "NEEDS_REVIEW", "UNCERTAIN"}
            and bool(payload.get("policy_number"))
            and bool(payload.get("transaction_type") or payload.get("classification"))
        )
        confidence_is_acceptable = (
            classification_is_complete and (
                confidence is None or payload.get("classification_source") == "EXPLICIT_EMAIL_HEADER"
            )
        ) or (
            confidence is not None and confidence >= _classification_minimum()
        )

        if (
            (is_endorsement is None and classification not in {"CLAIM", "NEW_POLICY_ENROLLMENT"})
            or classification in {"NEEDS_REVIEW", "UNCERTAIN"}
            or not confidence_is_acceptable
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
        if policy and payload.get('members'):
            from .benefit_plans import resolve_member_plan
            payload['members'] = [resolve_member_plan(policy, row) for row in payload['members']]
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

        if actor and getattr(actor, "is_authenticated", False) and not visible_policies(actor).filter(pk=policy.pk).exists():
            email.processing_state = InboundEmail.State.UNAUTHORIZED
            email.processing_stage = "POLICY_ACCESS"
            email.processing_error = "The resolved policy is outside the processing user's authorized organizations."
            email.save(update_fields=["processing_state", "processing_stage", "processing_error", "updated_at"])
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

        allowed_statuses = {Policy.Status.DRAFT, Policy.Status.ACTIVE} if transaction_type == MemberTransaction.Type.NEW_POLICY_ENROLLMENT else {Policy.Status.ACTIVE}
        if policy.status not in allowed_statuses or (transaction_type == MemberTransaction.Type.NEW_POLICY_ENROLLMENT and policy.initial_enrollment_completed_at):
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

        if transaction_type == 'CLAIM':
            from services.business_requests import create_business_request
            from apps.tickets.models import TicketEvent
            from .email_evidence import html_to_text
            requester=authority.user if authority and authority.user_id else actor
            if requester is None:raise ValueError('Map an authorized requester to this sender.')
            with transaction.atomic():
                locked=InboundEmail.objects.select_for_update().get(pk=email.pk)
                if locked.ticket_id:return locked.ticket
                ticket=create_business_request(workflow_type='CLAIM',policy=policy,requester=requester,
                    subject=email.subject,description=email.body_text or html_to_text(email.body_html),payload=payload)
                for attachment in email.attachments.all():
                    linked=TicketAttachment(ticket=ticket,uploaded_by=requester,original_name=attachment.original_name,content_type=attachment.content_type,size=attachment.size,is_restricted=True)
                    attachment.file.open('rb')
                    try:linked.file.save(attachment.original_name,File(attachment.file),save=True)
                    finally:attachment.file.close()
                    attachment.processing_state=InboundEmailAttachment.State.PROCESSED
                    attachment.save(update_fields=['processing_state','updated_at'])
                email.ticket=ticket;email.processing_state=InboundEmail.State.PROCESSED;email.processing_stage='COMPLETE';email.processed_at=timezone.now();email.processing_error=''
                email.save(update_fields=['ticket','processing_state','processing_stage','processed_at','processing_error','ai_extracted_payload','classification','classification_confidence','ai_confidence','updated_at'])
                TicketEvent.objects.create(ticket=ticket,actor=requester,event_type='email_imported',summary='Authorized claim email imported',details={'email':email.pk,'authority':authority.pk if authority else None})
                return ticket

        effective_date = _as_date(
            hints.get("effective_date") or payload.get("effective_date"),
            fallback=timezone.localdate(email.received_at),
        )
        refund_basis = _normalize_refund_basis(
            hints.get("refund_basis") or payload.get("refund_basis")
        )

        with transaction.atomic():
            if email.transaction_id:
                tx = MemberTransaction.objects.select_for_update().get(pk=email.transaction_id)
                email.transaction = tx
                if force:
                    validate_email_reprocessing(email, actor)
                    if tx.policy_id != policy.pk or tx.transaction_type != transaction_type:
                        raise ValueError(
                            "The extracted policy or endorsement type differs from the linked "
                            "endorsement. Correct the email processing hints before retrying."
                        )
            else:
                requester = (
                    authority.user
                    if authority is not None and authority.user_id
                    else actor
                )
                tx = MemberTransaction.objects.create(
                    organization=policy.organization,
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
                        else policy.organization
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
                        event_type=("email_reprocessed" if force else (
                            "office365_email_received" if email.provider == "office365_graph" else "email_received"
                        )),
                        summary=f"Inbound email {'reprocessed' if force else 'received'}: {email.subject or '(No subject)'}",
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
        _process_attachments(tx, email, actor, reprocess=force)

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
