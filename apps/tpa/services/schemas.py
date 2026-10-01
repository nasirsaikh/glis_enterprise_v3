"""Validated extraction contracts. Missing facts stay empty for intake review."""
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemberEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    employee_id: str | None = None
    member_id: str | None = None
    tpa_member_id: str | None = None
    card_number: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    relationship: str | None = None
    principal_employee_id: str | None = None
    principal_member_id: str | None = None
    national_id: str | None = None
    passport_number: str | None = None
    plan_code: str | None = None
    effective_date: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=100)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_scalar(cls, value: Any, info):
        if value is None or value == "":
            return None
        if isinstance(value, (date, datetime)):
            return value.isoformat()[:10]
        if isinstance(value, (str, int, float)):
            return value if info.field_name == "confidence" else str(value).strip()
        raise ValueError("A member field must be a scalar value.")


class MemberBundle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # Keep generation schema simple for Ollama/llama.cpp. Enforce the
    # operational row limit after generation so JSON-schema grammar
    # compilation does not expand a 2000-item repetition.
    members: list[MemberEvidence] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=100)

    @field_validator("members")
    @classmethod
    def validate_member_limit(cls, value):
        if len(value) > 2000:
            raise ValueError("A maximum of 2000 member records can be processed at once.")
        return value


class EmailEvidence(MemberBundle):
    is_endorsement_request: bool | None = None
    classification: str | None = None
    policy_number: str | None = None
    transaction_type: str | None = None
    transaction_reference: str | None = None
    effective_date: str | None = None
    refund_basis: str | None = None
    temporary_until: str | None = None
    remarks: str = ""
    summary: str = ""
    missing_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_references: list[Any] = Field(default_factory=list)


def missing_member_fields(payload, transaction_type=None):
    missing = []
    if transaction_type == "POLICY_CANCEL":
        return missing
    if not payload.get("members"):
        return ["members"]
    # Existing-member endorsements need an identity, rather than the full
    # demographic fields required for adding or enrolling a member.
    if transaction_type and transaction_type not in {"MEMBER_ADD", "NEW_POLICY_ENROLLMENT"}:
        for number, row in enumerate(payload["members"], 1):
            if not any(row.get(key) for key in ("employee_id", "member_id", "tpa_member_id", "card_number", "national_id", "passport_number")):
                missing.append(f"members[{number}].member_identifier")
        return missing
    for number, row in enumerate(payload["members"], 1):
        if not (row.get("full_name") or row.get("first_name")):
            missing.append(f"members[{number}].full_name")
        for field in ("date_of_birth", "gender", "relationship", "plan_code"):
            if row.get(field) in (None, ""):
                missing.append(f"members[{number}].{field}")
    return missing


def merge_recovered_payload(original, recovered):
    """Recover missing facts only when evidence has an unambiguous identity match."""
    rows = [
        dict(row) for row in original.get("members", [])
        if any(value not in (None, "") for key, value in row.items() if key != "confidence")
    ]
    if not rows:
        return recovered
    identity_keys = ("national_id", "passport_number", "employee_id", "member_id", "tpa_member_id")
    warnings = list(original.get("warnings", []))
    for incoming in recovered.get("members", []):
        matches = [
            row for row in rows
            if any(row.get(key) and incoming.get(key) and str(row[key]).strip().casefold() == str(incoming[key]).strip().casefold()
                   for key in identity_keys)
        ]
        if not matches:
            def name(row):
                return " ".join(str(row.get("full_name") or " ".join(str(row.get(part) or "") for part in ("first_name", "middle_name", "last_name"))).casefold().split())
            incoming_name = name(incoming)
            if len(incoming_name.split()) >= 2:
                matches = [row for row in rows if name(row) == incoming_name and (
                    not row.get("date_of_birth") or not incoming.get("date_of_birth")
                    or row["date_of_birth"] == incoming["date_of_birth"]
                )]
        if len(matches) != 1:
            warnings.append("Recovery row could not be matched uniquely; review the recovered evidence.")
            continue
        target = matches[0]
        # Conflicting identifiers indicate different people even if one ID matches.
        if any(target.get(key) and incoming.get(key) and str(target[key]).strip().casefold() != str(incoming[key]).strip().casefold()
               for key in identity_keys):
            warnings.append("Recovery identifiers conflict; existing member facts were preserved.")
            continue
        for key, value in incoming.items():
            if target.get(key) in (None, "") and value not in (None, ""):
                target[key] = value
    return {**original, "members": rows, "warnings": warnings}
