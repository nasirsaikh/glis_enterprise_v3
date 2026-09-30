import json

from apps.ai.models import AIExtractionProfile, AIProviderConfig
from .schemas import EmailEvidence, MemberEvidence


CANONICAL_MEMBER_FIELDS = (
    "employee_id",
    "member_id",
    "tpa_member_id",
    "card_number",
    "first_name",
    "middle_name",
    "last_name",
    "full_name",
    "date_of_birth",
    "gender",
    "relationship",
    "principal_employee_id",
    "principal_member_id",
    "national_id",
    "passport_number",
    "plan_code",
    "effective_date",
    "confidence",
)
EMAIL_FIELDS = ("policy_number", "transaction_type", "effective_date", "transaction_reference", "refund_basis", "temporary_until")


def apply_field_aliases(data, aliases):
    from .intake import _key
    mapped = dict(data)
    keyed = {_key(key): value for key, value in data.items()}
    for target, values in (aliases or {}).items():
        if mapped.get(target) not in (None, ""):
            continue
        if not isinstance(values, (list, str)):
            continue
        for alias in ([values] if isinstance(values, str) else values):
            value = keyed.get(_key(alias))
            if value not in (None, ""):
                mapped[target] = value
                break
    return mapped


def canonical_member(data, field_aliases=None):
    from .intake import ALIASES, _key, normalize_member_row
    if not isinstance(data, dict):
        raise ValueError("Each AI member row must be a JSON object.")
    mapped = apply_field_aliases(data, field_aliases)
    recognized = {_key(alias) for target, aliases in ALIASES.items() for alias in (target, *aliases)}
    if any(_key(key) in recognized and isinstance(value, (dict, list, tuple, set)) for key, value in mapped.items()):
        raise ValueError("A member field must be a scalar value.")
    MemberEvidence.model_validate({key: value for key, value in mapped.items() if key in CANONICAL_MEMBER_FIELDS})
    normalized = normalize_member_row(mapped)
    return {key: normalized.get(key, mapped.get(key)) for key in CANONICAL_MEMBER_FIELDS}


def normalize_ai_payload(payload, *, field_aliases=None):
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, list):
        payload = {"members": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("members"), list):
        raise ValueError("AI response did not contain the required members array.")
    payload = apply_field_aliases(payload, field_aliases)

    normalized = {
        "is_endorsement_request": payload.get("is_endorsement_request"),
        "classification": payload.get("classification") or payload.get("transaction_type"),
        "policy_number": payload.get("policy_number"),
        "transaction_type": payload.get("transaction_type") or payload.get("classification"),
        "transaction_reference": payload.get("transaction_reference"),
        "effective_date": payload.get("effective_date"),
        "refund_basis": payload.get("refund_basis"),
        "temporary_until": payload.get("temporary_until"),
        "remarks": payload.get("remarks") or "",
        "summary": payload.get("summary") or "",
        "confidence": payload.get("confidence"),
        "missing_information": list(payload.get("missing_information") or []),
        "warnings": list(payload.get("warnings") or []),
        "source_references": list(payload.get("source_references") or []),
        "members": [canonical_member(row, field_aliases) for row in payload["members"]],
    }
    return EmailEvidence.model_validate(normalized).model_dump(mode="json")


def select_provider(*, vision=None, sensitive=False, capability=None):
    qs = AIProviderConfig.objects.filter(is_active=True)
    if vision is True:
        qs = qs.filter(supports_vision=True)
    elif vision is False:
        qs = qs.filter(supports_vision=False)
    if sensitive:
        qs = qs.filter(allow_sensitive_data=True)

    providers = list(qs.order_by("priority", "id"))
    if capability:
        wanted = capability.strip().lower()
        providers = [
            provider
            for provider in providers
            if wanted
            in {
                str(item).strip().lower()
                for item in (provider.task_capabilities or [])
            }
        ]

    # TPA production processing is local-first: prefer Ollama whenever an
    # eligible Ollama provider exists, then fall back to configured test or
    # alternative providers. Explicit provider selections elsewhere are
    # still respected.
    providers.sort(
        key=lambda provider: (
            provider.provider != AIProviderConfig.Provider.OLLAMA,
            provider.priority,
            provider.pk,
        )
    )
    return providers[0] if providers else None


def select_profile(task, *, product="", transaction_type=""):
    qs = (
        AIExtractionProfile.objects.filter(task=task, is_active=True)
        .prefetch_related("examples")
        .order_by("priority", "id")
    )
    exact = qs.filter(
        applicable_product=product,
        applicable_transaction_type=transaction_type,
    ).first()
    if exact:
        return exact

    product_profile = qs.filter(
        applicable_product=product,
        applicable_transaction_type="",
    ).first()
    transaction_profile = qs.filter(applicable_product="", applicable_transaction_type=transaction_type).first()
    return transaction_profile or product_profile or qs.filter(
        applicable_product="",
        applicable_transaction_type="",
    ).first()
