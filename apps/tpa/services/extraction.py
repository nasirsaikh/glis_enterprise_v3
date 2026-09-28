import json
from apps.ai.models import AIProviderConfig, AIExtractionProfile

CANONICAL_MEMBER_FIELDS=(
    "employee_id","member_id","first_name","middle_name","last_name","full_name",
    "date_of_birth","gender","relationship","principal_employee_id","national_id",
    "passport_number","plan_code","effective_date",
)

def canonical_member(data):
    return {key:(data or {}).get(key) for key in CANONICAL_MEMBER_FIELDS}

def normalize_ai_payload(payload):
    if isinstance(payload,str):
        payload=json.loads(payload)
    if isinstance(payload,list):
        payload={"members":payload}
    if not isinstance(payload,dict) or not isinstance(payload.get("members"),list):
        raise ValueError("AI response did not contain the required members array.")
    return {"members":[canonical_member(row) for row in payload["members"]]}

def select_provider(*, vision=False, sensitive=False, capability=None):
    qs=AIProviderConfig.objects.filter(is_active=True)
    if vision: qs=qs.filter(supports_vision=True)
    if sensitive: qs=qs.filter(allow_sensitive_data=True)
    if capability:
        candidates=[p for p in qs.order_by("priority","id") if capability in (p.task_capabilities or [])]
        return candidates[0] if candidates else None
    return qs.order_by("priority","id").first()

def select_profile(task, *, product="", transaction_type=""):
    qs=AIExtractionProfile.objects.filter(task=task,is_active=True).prefetch_related("examples").order_by("priority","id")
    exact=qs.filter(applicable_product=product,applicable_transaction_type=transaction_type).first()
    if exact: return exact
    product_profile=qs.filter(applicable_product=product,applicable_transaction_type="").first()
    return product_profile or qs.filter(applicable_product="",applicable_transaction_type="").first()
