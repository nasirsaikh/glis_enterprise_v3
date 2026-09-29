import json

from apps.ai.models import AIExtractionProfile, AIProviderConfig


CANONICAL_MEMBER_FIELDS = (
    "employee_id",
    "member_id",
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


def canonical_member(data):
    return {key: (data or {}).get(key) for key in CANONICAL_MEMBER_FIELDS}


def normalize_ai_payload(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, list):
        payload = {"members": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("members"), list):
        raise ValueError("AI response did not contain the required members array.")

    return {
        "policy_number": payload.get("policy_number"),
        "transaction_type": payload.get("transaction_type"),
        "effective_date": payload.get("effective_date"),
        "summary": payload.get("summary") or "",
        "confidence": payload.get("confidence"),
        "members": [canonical_member(row) for row in payload["members"]],
    }


def select_provider(*, vision=False, sensitive=False, capability=None):
    qs = AIProviderConfig.objects.filter(is_active=True)
    if vision:
        qs = qs.filter(supports_vision=True)
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
    return product_profile or qs.filter(
        applicable_product="",
        applicable_transaction_type="",
    ).first()
