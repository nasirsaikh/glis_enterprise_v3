import csv
import hashlib
import io
import mimetypes
from pathlib import Path

from django.core.exceptions import ValidationError

from apps.ai.models import AIExtractionProfile
from apps.ai.runtime import generate_json, generate_text

from ..models import MemberAction, SourceDocument
from .extraction import normalize_ai_payload, select_profile, select_provider
from .intake import normalize_member_row


SUPPORTED_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


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
        "employee_id, member_id, first_name, middle_name, last_name, full_name, "
        "date_of_birth, gender, relationship, principal_employee_id, principal_member_id, "
        "national_id, passport_number, plan_code, effective_date and confidence. "
        "Use PRINCIPAL/SPOUSE/CHILD/OTHER for relationship. Use YYYY-MM-DD dates. "
        "Never calculate premium, eligibility, STP or approval."
    )
    if not profile:
        return base
    examples = []
    for example in profile.examples.filter(is_active=True)[:5]:
        examples.append(
            f"Example input:\n{example.input_text}\nExpected output:\n{example.expected_output}"
        )
    return "\n\n".join(
        value
        for value in [
            base,
            profile.system_prompt,
            profile.instructions,
            "\n\n".join(examples),
        ]
        if value
    )


def _map_evidence_text(tx, evidence_text):
    provider = (
        select_provider(sensitive=True, capability="member_field_mapping")
        or select_provider(sensitive=True, capability="document_extraction")
    )
    if not provider:
        raise RuntimeError(
            "No active text AI provider allows sensitive data and has member_field_mapping "
            "or document_extraction capability."
        )
    profile = select_profile(
        AIExtractionProfile.Task.MEMBER_FIELD_MAPPING,
        product=tx.policy.product_type,
        transaction_type=tx.transaction_type,
    )
    payload, duration_ms = generate_json(
        provider,
        system_prompt=_system_prompt(profile),
        user_prompt=_member_prompt(tx, evidence_text),
    )
    return normalize_ai_payload(payload), provider, profile, duration_ms


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
    text, duration_ms = generate_text(
        provider,
        system_prompt=(
            "Transcribe the visible insurance document faithfully. Preserve labels, values, "
            "names, identifiers, dates, numbers, MRZ lines and table relationships. "
            "Do not infer missing values and do not return JSON."
        ),
        user_prompt=(
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


def _create_actions(tx, rows, *, confidence=None):
    last_row = (
        tx.member_actions.order_by("-row_number")
        .values_list("row_number", flat=True)
        .first()
        or 0
    )
    created = []
    for offset, row in enumerate(rows, start=1):
        normalized = normalize_member_row(row)
        for key in (
            "employee_id",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "relationship",
            "plan_code",
            "national_id",
            "passport_number",
            "principal_employee_id",
            "principal_member_id",
        ):
            if key in row and row.get(key) not in (None, ""):
                normalized[key] = str(row.get(key)).strip()

        row_confidence = row.get("confidence", confidence)
        try:
            row_confidence = float(row_confidence)
            if row_confidence <= 1:
                row_confidence *= 100
        except (TypeError, ValueError):
            row_confidence = confidence

        if not any(value not in (None, "") for value in normalized.values()):
            continue

        created.append(
            MemberAction.objects.create(
                transaction=tx,
                action=tx.transaction_type,
                row_number=last_row + offset,
                extracted_data=normalized,
                corrected_data=normalized,
                extraction_confidence=row_confidence,
            )
        )
    return created


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
            source_hash=digest.hexdigest(),
            uploaded_by=actor,
        )
        documents.append(document)
    return documents


def process_source_bundle(tx, documents, actor=None):
    created_actions = []
    evidence = []
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

        try:
            if suffix in {".csv", ".xlsx", ".xls"}:
                raw_rows = _structured_rows(document.original_name, content)
                actions = _create_actions(tx, raw_rows, confidence=100)
                created_actions.extend(actions)
                document.extraction_method = "STRUCTURED_IMPORT"
                document.extracted_payload = {
                    "rows_created": len(actions),
                    "format": suffix.lstrip("."),
                }
                document.extraction_confidence = 100
                document.processing_state = SourceDocument.State.PROCESSED
                document.processed = True

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

    if evidence:
        try:
            mapped, provider, profile, _ = _map_evidence_text(
                tx,
                "\n\n".join(evidence),
            )
            ai_provider = provider
            ai_profile = profile
            actions = _create_actions(
                tx,
                mapped.get("members") or [],
                confidence=mapped.get("confidence"),
            )
            created_actions.extend(actions)
            for document in documents:
                if (
                    document.processed
                    and document.extraction_method in {"PDF_TEXT", "PDF_VISION_OCR", "VISION_OCR"}
                ):
                    payload = dict(document.extracted_payload or {})
                    payload["bundle_members_created"] = len(actions)
                    payload["ai_provider"] = provider.name
                    payload["ai_profile"] = profile.name if profile else ""
                    document.extracted_payload = payload
                    document.ai_profile = profile
                    document.save(
                        update_fields=[
                            "extracted_payload",
                            "ai_profile",
                            "updated_at",
                        ]
                    )
        except Exception as exc:
            for document in documents:
                if document.extraction_method in {"PDF_TEXT", "PDF_VISION_OCR", "VISION_OCR"}:
                    document.processing_state = SourceDocument.State.REVIEW
                    document.processed = False
                    document.processing_error = (
                        f"Document OCR succeeded but member JSON mapping failed: {exc}"
                    )
                    document.save(
                        update_fields=[
                            "processing_state",
                            "processed",
                            "processing_error",
                            "updated_at",
                        ]
                    )

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
