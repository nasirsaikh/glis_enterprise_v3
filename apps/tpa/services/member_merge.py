from django.utils import timezone

from ..models import MemberAction
from .intake import normalize_member_row


IDENTIFIER_FIELDS = (
    "tpa_member_id",
    "employee_id",
    "national_id",
    "passport_number",
)


def _data(action):
    return {
        **(action.submitted_data or {}),
        **(action.extracted_data or {}),
        **(action.corrected_data or {}),
    }


def _normalize(row):
    normalized = normalize_member_row(row or {})
    if (row or {}).get("member_id") and not normalized.get("tpa_member_id"):
        normalized["tpa_member_id"] = str(row.get("member_id")).strip()
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
        "tpa_member_id",
    ):
        if key in (row or {}) and row.get(key) not in (None, ""):
            normalized[key] = str(row.get(key)).strip()
    return normalized


def _matches(action, normalized):
    current = _data(action)
    for field in IDENTIFIER_FIELDS:
        left = str(current.get(field) or "").strip().lower()
        right = str(normalized.get(field) or "").strip().lower()
        if left and right and left == right:
            return True
    # Names and DOB can identify a repeated extraction without an ID. Never
    # use this fallback when the available identifiers disagree.
    if any(current.get(field) and normalized.get(field) for field in IDENTIFIER_FIELDS):
        return False
    fields = ("first_name", "last_name", "date_of_birth")
    return all(
        str(current.get(field) or "").strip()
        and str(current.get(field)).strip().casefold() == str(normalized.get(field) or "").strip().casefold()
        for field in fields
    )


def merge_member_rows(
    tx,
    rows,
    *,
    source,
    confidence=None,
    submitted_rows=None,
):
    """
    Merge extracted rows into the transaction without silently overwriting
    corrected values. Matching is deterministic on canonical identifiers.
    """
    existing = list(tx.member_actions.all().order_by("row_number", "pk"))
    next_row = max([item.row_number or 0 for item in existing] or [0])
    created_or_updated = []

    for index, row in enumerate(rows or []):
        normalized = _normalize(row)
        if not any(value not in (None, "") for value in normalized.values()):
            continue

        matches = [action for action in existing if _matches(action, normalized)]
        action = matches[0] if len(matches) == 1 else None
        conflicts = []

        provenance_entry = {
            "source": source,
            "at": timezone.now().isoformat(),
            "identifiers": {
                key: normalized.get(key)
                for key in IDENTIFIER_FIELDS
                if normalized.get(key)
            },
        }

        if action:
            extracted = dict(action.extracted_data or {})
            corrected = dict(action.corrected_data or {})
            for key, value in normalized.items():
                if value in (None, ""):
                    continue
                existing_value = corrected.get(key)
                if existing_value in (None, ""):
                    corrected[key] = value
                elif str(existing_value).strip() != str(value).strip():
                    conflicts.append(
                        {
                            "field": key,
                            "kept": existing_value,
                            "incoming": value,
                            "source": source,
                        }
                    )
                if extracted.get(key) in (None, ""):
                    extracted[key] = value
            provenance_entry["conflicts"] = conflicts
            action.extracted_data = extracted
            action.corrected_data = corrected
            action.provenance = [*(action.provenance or []), provenance_entry]
            if confidence not in (None, "") and action.extraction_confidence is None:
                action.extraction_confidence = confidence
            action.save(
                update_fields=[
                    "extracted_data",
                    "corrected_data",
                    "provenance",
                    "extraction_confidence",
                    "updated_at",
                ]
            )
        else:
            next_row += 1
            if len(matches) > 1:
                provenance_entry["conflicts"] = [
                    {
                        "field": "member",
                        "kept": "",
                        "incoming": "",
                        "source": source,
                        "message": "Incoming row matched more than one existing row and requires review.",
                    }
                ]
            submitted = {}
            if submitted_rows and index < len(submitted_rows):
                submitted = submitted_rows[index] or {}
            action = MemberAction.objects.create(
                transaction=tx,
                action=tx.transaction_type,
                row_number=next_row,
                submitted_data=submitted,
                extracted_data=normalized,
                corrected_data=normalized,
                extraction_confidence=confidence,
                provenance=[provenance_entry],
            )
            existing.append(action)

        created_or_updated.append(action)

    return created_or_updated
