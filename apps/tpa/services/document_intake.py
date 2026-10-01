import csv
import hashlib
import io
import mimetypes
from pathlib import Path

from django.core.exceptions import ValidationError

from apps.ai.models import AIExtractionProfile, AIInteraction
from apps.ai.runtime import generate_json, generate_text

from ..models import ExtractionAttempt, MemberAction, SourceDocument, TransactionEvent
from .extraction import canonical_member, normalize_ai_payload, select_profile, select_provider
from .intake import normalize_member_row
from .member_merge import merge_member_rows
from .prompts import profile_guidance
from .email_evidence import member_rows_from_html, read_email_evidence
from .schemas import MemberBundle, missing_member_fields, merge_recovered_payload
from .document_fallback import docling_text


SUPPORTED_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".eml",
    ".msg",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _confidence_percent(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 1:
        number *= 100
    return max(0.0, min(number, 100.0))


def _read_bytes(field):
    field.open("rb")
    try:
        return field.read()
    finally:
        field.close()


def _read_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def _read_xlsx(data):
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if not headers:
        return []
    headers = [str(value or "").strip() for value in headers]
    return [
        {headers[index]: value for index, value in enumerate(row)}
        for row in rows
        if any(value not in (None, "") for value in row)
    ]


def _read_xls(data):
    try:
        import xlrd
    except ImportError as exc:
        raise ValidationError("Legacy .xls upload requires xlrd.") from exc

    workbook = xlrd.open_workbook(file_contents=data)
    sheet = workbook.sheet_by_index(0)
    if sheet.nrows < 1:
        return []
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    rows = []
    for row_index in range(1, sheet.nrows):
        raw = {
            headers[col]: sheet.cell_value(row_index, col)
            for col in range(sheet.ncols)
        }
        if any(value not in (None, "") for value in raw.values()):
            rows.append(raw)
    return rows


def _structured_rows(name, data):
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        return _read_csv(data)
    if suffix == ".xlsx":
        return _read_xlsx(data)
    if suffix == ".xls":
        return _read_xls(data)
    raise ValidationError("Not a structured member file.")


def _member_prompt(tx, evidence_text):
    plans = list(
        tx.policy.plans.filter(is_active=True)
        .order_by("code")
        .values("code", "name", "default_sum_insured")
    )
    return (
        f"Policy Number: {tx.policy.policy_number}\n"
        f"Transaction Type: {tx.transaction_type}\n"
        f"Effective Date: {tx.effective_date.isoformat()}\n"
        f"Valid Plans: {plans}\n\n"
        "The following text was extracted from one or more related insurance documents. "
        "Treat all sections as one evidence bundle. Combine front/back ID pages and related "
        "documents when they describe the same member. Do not calculate premium and do not "
        "invent missing values.\n\n"
        f"{evidence_text}"
    )


def _system_prompt(profile):
    base = (
        "You map insurance endorsement evidence into canonical member JSON. "
        "Return JSON only with top-level key 'members'. Each member can contain "
        "employee_id, member_id, tpa_member_id, card_number, first_name, middle_name, last_name, full_name, "
        "date_of_birth, gender, relationship, principal_employee_id, principal_member_id, "
        "national_id, passport_number, plan_code, effective_date and confidence. "
        "Use PRINCIPAL/SPOUSE/CHILD/OTHER for relationship. Use YYYY-MM-DD dates. "
        "Never calculate premium, eligibility, STP or approval."
    )
    if not profile:
        return base
    return base + "\n\n" + profile_guidance(profile)


def _map_evidence_text(tx, evidence_text, actor=None):
    # OCR and semantic mapping are deliberately separate stages. A vision OCR
    # model such as GLM-OCR may return {"ocr_text": ...}; it must never be used
    # as the text-to-member-JSON mapper.
    provider = (
        select_provider(
            vision=False,
            sensitive=True,
            capability="member_field_mapping",
        )
        or select_provider(
            vision=False,
            sensitive=True,
            capability="structured_header_mapping",
        )
        or select_provider(
            vision=False,
            sensitive=True,
            capability="email_extraction",
        )
        or select_provider(
            vision=False,
            sensitive=True,
            capability="document_extraction",
        )
    )
    if not provider:
        raise RuntimeError(
            "OCR succeeded, but no active non-vision text AI provider is configured "
            "for member JSON mapping. Configure a text model such as qwen2.5:7b with "
            "Supports vision disabled, Allow sensitive data enabled, and the "
            "member_field_mapping capability."
        )

    profile = select_profile(
        AIExtractionProfile.Task.MEMBER_FIELD_MAPPING,
        product=tx.policy.product_type,
        transaction_type=tx.transaction_type,
    )
    system_prompt = _system_prompt(profile)
    user_prompt = _member_prompt(tx, evidence_text)
    duration_ms = 0
    try:
        payload, duration_ms = generate_json(
            provider, system_prompt=system_prompt, user_prompt=user_prompt,
            response_schema=MemberBundle.model_json_schema(),
        )
        normalized = normalize_ai_payload(payload, field_aliases=profile.field_aliases if profile else None)
        if not normalized["members"]:
            raise ValueError("The mapper returned no populated member fields.")
    except (TypeError, ValueError) as first_error:
        retry_prompt = (
            user_prompt
            + "\n\nIMPORTANT CORRECTION: The previous response was not canonical member JSON. "
            "Return JSON only in exactly this shape: "
            '{"members":[{"employee_id":null,"member_id":null,"first_name":null,'
            '"middle_name":null,"last_name":null,"full_name":null,'
            '"date_of_birth":null,"gender":null,"relationship":null,'
            '"principal_employee_id":null,"principal_member_id":null,'
            '"national_id":null,"passport_number":null,"plan_code":null,'
            '"effective_date":null,"confidence":0.0}],"confidence":0.0}. '
            "Do not return ocr_text, page_count, commentary or markdown."
        )
        retry_payload, retry_duration = generate_json(
            provider,
            system_prompt=system_prompt,
            user_prompt=retry_prompt,
            response_schema=MemberBundle.model_json_schema(),
        )
        duration_ms += retry_duration
        try:
            normalized = normalize_ai_payload(retry_payload, field_aliases=profile.field_aliases if profile else None)
            if not normalized["members"]:
                raise ValueError("The mapper returned no populated member fields.")
        except (TypeError, ValueError) as retry_error:
            received_keys = (
                ", ".join(sorted(str(key) for key in retry_payload.keys()))
                if isinstance(retry_payload, dict)
                else type(retry_payload).__name__
            )
            raise ValueError(
                f"Text mapping provider '{provider.name}' ({provider.model_name or provider.provider}) "
                "did not return canonical member JSON after retry. "
                f"Received: {received_keys or 'empty payload'}."
            ) from retry_error

    AIInteraction.objects.create(
        user=actor,
        ticket=tx.ticket,
        purpose="tpa_document_mapping",
        provider=f"{provider.provider}:{provider.model_name or provider.name}",
        request_summary={
            "transaction_reference": tx.reference,
            "policy_number": tx.policy.policy_number,
            "profile_id": profile.pk if profile else None,
            "evidence_characters": len(evidence_text),
        },
        response=normalized,
        confidence=(
            (_confidence_percent(normalized.get("confidence")) or 0) / 100
        ),
        duration_ms=max(duration_ms, 0),
        succeeded=True,
    )
    return normalized, provider, profile, duration_ms


def _ocr_image(tx, content, mime_type):
    provider = select_provider(
        vision=True,
        sensitive=True,
        capability="document_extraction",
    )
    if not provider:
        raise RuntimeError(
            "No active vision AI provider allows sensitive data and has document_extraction capability."
        )
    is_glm_ocr = "glm-ocr" in (provider.model_name or "").lower()
    text, duration_ms = generate_text(
        provider,
        system_prompt="" if is_glm_ocr else (
            "Transcribe the visible insurance document faithfully. Preserve labels, values, "
            "names, identifiers, dates, numbers, MRZ lines and table relationships. "
            "Do not infer missing values and do not return JSON."
        ),
        user_prompt="Text Recognition:" if is_glm_ocr else (
            "Text Recognition: return concise OCR text only. This document may be one page "
            "of a multi-file member evidence bundle."
        ),
        images=[{"bytes": content, "mime_type": mime_type}],
    )
    if not text.strip():
        raise RuntimeError("Vision/OCR provider returned no readable text.")
    return text, provider, duration_ms


def _pdf_text_or_ocr(tx, content):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    embedded = "\n".join(page.extract_text() or "" for page in reader.pages)
    if embedded.strip():
        return embedded, "PDF_TEXT", len(reader.pages)

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "Scanned PDF OCR requires PyMuPDF and a vision-capable AI provider."
        ) from exc

    doc = fitz.open(stream=content, filetype="pdf")
    page_text = []
    for page_number, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        text, _, _ = _ocr_image(tx, pix.tobytes("png"), "image/png")
        page_text.append(f"--- PDF PAGE {page_number} ---\n{text}")
    return "\n\n".join(page_text), "PDF_VISION_OCR", len(doc)


def _create_actions(tx, rows, *, confidence=None, source="document"):
    return merge_member_rows(
        tx,
        rows,
        source=source,
        confidence=_confidence_percent(confidence),
    )

def create_source_documents(tx, uploaded_files, actor=None):
    documents = []
    for uploaded in uploaded_files:
        if uploaded.size > MAX_UPLOAD_BYTES:
            raise ValidationError(f"{uploaded.name} exceeds the 10 MB upload limit.")
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValidationError(
                f"{uploaded.name}: unsupported file type. Use CSV, XLSX, XLS, PDF, PNG, JPG, JPEG or WEBP."
            )

        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)

        source_hash = digest.hexdigest()
        document = SourceDocument.objects.filter(
            transaction=tx,
            source_hash=source_hash,
        ).order_by("-pk").first()
        if document is None:
            document = SourceDocument.objects.create(
                transaction=tx,
                file=uploaded,
                original_name=uploaded.name,
                content_type=getattr(uploaded, "content_type", "")
                or mimetypes.guess_type(uploaded.name)[0]
                or "",
                size=uploaded.size,
                document_kind="MEMBER_SOURCE",
                extraction_method="",
                processing_state=SourceDocument.State.RECEIVED,
                processed=False,
                source_hash=source_hash,
                uploaded_by=actor,
            )
        documents.append(document)
    return documents


def process_source_bundle(tx, documents, actor=None):
    created_actions = []
    evidence = []
    recovery_sources = []
    ai_profile = None
    ai_provider = None

    tx.status = tx.Status.EXTRACTING
    tx.ai_extraction_status = "PROCESSING"
    tx.save(update_fields=["status", "ai_extraction_status", "updated_at"])

    for document in documents:
        document.processing_state = SourceDocument.State.PROCESSING
        document.processing_error = ""
        document.save(
            update_fields=["processing_state", "processing_error", "updated_at"]
        )
        suffix = Path(document.original_name).suffix.lower()
        content = _read_bytes(document.file)
        attempt = ExtractionAttempt.objects.create(
            source_document=document,
            stage="SOURCE_EXTRACTION",
            status=ExtractionAttempt.Status.STARTED,
        )

        try:
            if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
                recovery_sources.append((document, document.original_name, content))
            if suffix in {".csv", ".xlsx", ".xls"}:
                raw_rows = _structured_rows(document.original_name, content)

                # Structured files do not need OCR/Docling, but they still pass
                # through the same canonical member contract before persistence.
                # This applies aliases/normalization and Pydantic scalar validation
                # so spreadsheet columns cannot bypass the extraction contract.
                validated_rows = [
                    canonical_member(row)
                    for row in raw_rows
                    if any(value not in (None, "") for value in row.values())
                ]

                actions = _create_actions(
                    tx,
                    validated_rows,
                    confidence=100,
                    source=f"structured:{document.pk}:{document.original_name}",
                )
                created_actions.extend(actions)
                document.extraction_method = "STRUCTURED_IMPORT"
                document.extracted_payload = {
                    "rows_created": len(actions),
                    "format": suffix.lstrip("."),
                }
                document.extraction_confidence = 100
                document.processing_state = SourceDocument.State.PROCESSED
                document.processed = True

            elif suffix in {".eml", ".msg"}:
                message = read_email_evidence(document.original_name, content)
                text = message["body_text"]
                table_rows = member_rows_from_html(message["body_html"])
                attachments = message["attachments"]
                structured_attachment = any(Path(item["name"]).suffix.lower() in {".csv", ".xlsx", ".xls"} for item in attachments)
                if table_rows:
                    created_actions.extend(_create_actions(
                        tx, table_rows, source=f"email_table:{document.pk}",
                    ))
                elif not structured_attachment:
                    evidence.append(f"--- SOURCE EMAIL: {document.original_name} ---\n{text}")
                document.extraction_method = "OUTLOOK_MSG" if suffix == ".msg" else "EMAIL_MIME"
                document.extracted_payload = {
                    "email_subject": message["subject"], "email_from": message["sender"],
                    "email_to": message["recipient"], "body_text": text,
                    "body_members": table_rows,
                    "attachments": [item["name"] for item in attachments],
                }
                document.processing_state = SourceDocument.State.PROCESSED
                document.processed = True
                for item in attachments:
                    raw, name = item["content"], item["name"]
                    if not raw:
                        continue
                    inner_suffix = Path(name).suffix.lower()
                    if inner_suffix in {".csv", ".xlsx", ".xls"}:
                        created_actions.extend(_create_actions(
                            tx, _structured_rows(name, raw), confidence=100,
                            source=f"email_attachment:{document.pk}:{name}",
                        ))
                    elif inner_suffix in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
                        recovery_sources.append((document, name, raw))
                        try:
                            if inner_suffix == ".pdf":
                                inner_text, _, _ = _pdf_text_or_ocr(tx, raw)
                            else:
                                inner_text, provider, _ = _ocr_image(
                                    tx, raw, item["content_type"] or mimetypes.guess_type(name)[0] or "image/jpeg",
                                )
                                ai_provider = provider
                            evidence.append(f"--- EMAIL ATTACHMENT: {name} ---\n{inner_text}")
                        except Exception as exc:
                            document.processing_state = SourceDocument.State.REVIEW
                            document.processed = False
                            document.processing_error = f"{name}: {exc}"

            elif suffix == ".pdf":
                text, method, pages = _pdf_text_or_ocr(tx, content)
                evidence.append(
                    f"--- SOURCE: {document.original_name} ---\n{text}"
                )
                document.extraction_method = method
                document.extracted_payload = {
                    "ocr_text": text,
                    "page_count": pages,
                }
                document.processing_state = SourceDocument.State.PROCESSED
                document.processed = True

            else:
                mime_type = document.content_type or mimetypes.guess_type(
                    document.original_name
                )[0] or "image/jpeg"
                text, provider, _ = _ocr_image(tx, content, mime_type)
                ai_provider = provider
                evidence.append(
                    f"--- SOURCE: {document.original_name} ---\n{text}"
                )
                document.extraction_method = "VISION_OCR"
                document.extracted_payload = {"ocr_text": text}
                document.processing_state = SourceDocument.State.PROCESSED
                document.processed = True

            document.save(
                update_fields=[
                    "extraction_method",
                    "extracted_payload",
                    "extraction_confidence",
                    "processing_state",
                    "processed",
                    "processing_error",
                    "updated_at",
                ]
            )
            attempt.status = ExtractionAttempt.Status.SUCCESS
            attempt.provider = ai_provider if suffix not in {".csv", ".xlsx", ".xls"} else None
            attempt.model_name = (
                getattr(ai_provider, "model_name", "") if attempt.provider_id else ""
            )
            attempt.metadata = {
                "method": document.extraction_method,
                "source_hash": document.source_hash,
            }
            attempt.save(
                update_fields=[
                    "status",
                    "provider",
                    "model_name",
                    "metadata",
                    "updated_at",
                ]
            )
            TransactionEvent.objects.create(
                transaction=tx,
                actor=actor,
                event_type="evidence_extracted",
                summary=f"Evidence processed: {document.original_name}",
                details={
                    "source_document_id": document.pk,
                    "method": document.extraction_method,
                    "state": document.processing_state,
                },
            )

        except Exception as exc:
            document.processing_state = SourceDocument.State.REVIEW
            document.processed = False
            document.processing_error = str(exc)
            document.save(
                update_fields=[
                    "processing_state",
                    "processed",
                    "processing_error",
                    "updated_at",
                ]
            )
            attempt.status = ExtractionAttempt.Status.REVIEW
            attempt.error = str(exc)
            attempt.save(update_fields=["status", "error", "updated_at"])
            TransactionEvent.objects.create(
                transaction=tx,
                actor=actor,
                event_type="extraction_failed",
                summary=f"Evidence needs review: {document.original_name}",
                details={
                    "source_document_id": document.pk,
                    "error": str(exc),
                },
            )

    if evidence or recovery_sources:
        mapping_attempts = [
            ExtractionAttempt.objects.create(
                source_document=document,
                stage="JSON_MAPPING",
                status=ExtractionAttempt.Status.STARTED,
            )
            for document in documents
            if Path(document.original_name).suffix.lower() not in {".csv", ".xlsx", ".xls"}
        ]
        try:
            mapping_error = None
            mapped = {"members": []}
            try:
                mapped, provider, profile, _ = _map_evidence_text(tx, "\n\n".join(evidence), actor=actor)
            except Exception as exc:
                mapping_error = exc
            missing = missing_member_fields(mapped, tx.transaction_type)
            recovery_warnings = []
            recovered_documents = set()
            if (mapping_error or missing) and recovery_sources:
                recovered_text = []
                for source_document, name, raw in recovery_sources:
                    try:
                        recovered_text.append(f"--- LOCAL OCR RECOVERY: {name} ---\n{docling_text(name, raw)}")
                        recovered_documents.add(source_document.pk)
                    except Exception as exc:
                        recovery_warnings.append(f"{name}: {exc}")
                if recovered_text:
                    try:
                        repaired, provider, profile, _ = _map_evidence_text(
                            tx, "\n\n".join(evidence + recovered_text), actor=actor
                        )
                        # Fill only empty facts matched by stable member identifiers.
                        # An unmatched recovery row never overwrites an existing member.
                        mapped = merge_recovered_payload(mapped, repaired)
                        mapping_error = None
                    except Exception as exc:
                        recovery_warnings.append(f"Recovery mapping: {exc}")
            if mapping_error:
                if recovery_warnings:
                    raise RuntimeError(f"{mapping_error}. Local OCR recovery: " + "; ".join(recovery_warnings)) from mapping_error
                raise mapping_error
            missing = missing_member_fields(mapped, tx.transaction_type)
            recovery_warnings.extend(str(value) for value in mapped.get("warnings", []))
            if not mapped.get("members"):
                raise ValueError("No member data could be extracted; add readable evidence or enter the member manually.")
            for document in documents:
                if document.pk in recovered_documents:
                    document.extraction_method = "LOCAL_OCR_RECOVERY"
                    document.processed = True
                    document.processing_state = SourceDocument.State.PROCESSED
                    document.processing_error = ""
                if missing or recovery_warnings:
                    document.processing_state = SourceDocument.State.REVIEW
                    document.processing_error = "Missing fields: " + ", ".join(missing) if missing else ""
                    if recovery_warnings:
                        document.processing_error += "\n" + "\n".join(recovery_warnings)
                document.save(update_fields=["extraction_method", "processed", "processing_state", "processing_error", "updated_at"])

            ai_provider = provider
            ai_profile = profile
            actions = _create_actions(
                tx,
                mapped.get("members") or [],
                confidence=mapped.get("confidence"),
                source="document_bundle:" + ",".join(str(document.pk) for document in documents),
            )
            created_actions.extend(actions)
            for document in documents:
                if (
                    document.processed
                    and document.extraction_method in {"PDF_TEXT", "PDF_VISION_OCR", "VISION_OCR", "EMAIL_MIME", "OUTLOOK_MSG", "LOCAL_OCR_RECOVERY"}
                ):
                    payload = dict(document.extracted_payload or {})
                    payload["bundle_members_created"] = len(actions)
                    payload["ai_provider"] = provider.name
                    payload["ai_profile"] = profile.name if profile else ""
                    document.extracted_payload = payload
                    document.ai_profile = profile
                    document.extraction_confidence = _confidence_percent(
                        mapped.get("confidence")
                    )
                    document.save(
                        update_fields=[
                            "extracted_payload",
                            "ai_profile",
                            "extraction_confidence",
                            "updated_at",
                        ]
                    )
            for attempt in mapping_attempts:
                attempt.status = ExtractionAttempt.Status.SUCCESS
                attempt.provider = provider
                attempt.model_name = provider.model_name
                attempt.metadata = {
                    "profile_id": profile.pk if profile else None,
                    "members": len(actions),
                }
                attempt.raw_output = mapped
                attempt.save(
                    update_fields=[
                        "status",
                        "provider",
                        "model_name",
                        "metadata",
                        "raw_output",
                        "updated_at",
                    ]
                )
        except Exception as exc:
            for document in documents:
                if Path(document.original_name).suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                    previous_error = document.processing_error
                    prefix = "Document OCR succeeded but member JSON mapping failed" if document.processed else "Document extraction/recovery and member mapping failed"
                    document.processing_state = SourceDocument.State.REVIEW
                    document.processed = False
                    document.processing_error = "\n".join(filter(None, [previous_error, f"{prefix}: {exc}"]))
                    document.save(
                        update_fields=[
                            "processing_state",
                            "processed",
                            "processing_error",
                            "updated_at",
                        ]
                    )
            for attempt in mapping_attempts:
                attempt.status = ExtractionAttempt.Status.REVIEW
                attempt.error = str(exc)
                attempt.save(update_fields=["status", "error", "updated_at"])

    review_count = sum(
        1
        for document in documents
        if document.processing_state in {SourceDocument.State.REVIEW, SourceDocument.State.FAILED}
    )
    tx.ai_extraction_status = "REVIEW" if review_count else "EXTRACTED"
    tx.ai_summary = (
        f"{len(created_actions)} member row(s) extracted from {len(documents)} source file(s)."
    )
    tx.status = tx.Status.DRAFT
    tx.metadata = {
        **(tx.metadata or {}),
        "last_extraction": {
            "documents": len(documents),
            "rows_created": len(created_actions),
            "review_documents": review_count,
            "ai_provider": getattr(ai_provider, "name", ""),
            "ai_profile": getattr(ai_profile, "name", ""),
        },
    }
    tx.save(
        update_fields=[
            "ai_extraction_status",
            "ai_summary",
            "status",
            "metadata",
            "updated_at",
        ]
    )
    return created_actions
