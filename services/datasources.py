from collections.abc import Callable


class DataSourceRegistry:
    """Allowlisted, parameterized lookup handlers. Editable JSON never executes SQL."""

    _handlers: dict[str, Callable] = {}

    @classmethod
    def register(cls, key: str):
        def decorator(func: Callable):
            cls._handlers[key] = func
            return func
        return decorator

    @classmethod
    def choices(cls, key: str, *, user=None, params=None):
        if key not in cls._handlers:
            return []
        return cls._handlers[key](user=user, params=params or {})


@DataSourceRegistry.register("complaint_categories")
def complaint_categories(**kwargs):
    return [("motor_claim", "Motor · Claim complaint"), ("health_provider", "Health · Provider complaint"), ("service_delay", "Service · Delay complaint")]


@DataSourceRegistry.register("complaint_locations")
def complaint_locations(**kwargs):
    return [("muscat", "Muscat"), ("sohar", "Sohar"), ("salalah", "Salalah"), ("nizwa", "Nizwa")]


@DataSourceRegistry.register("complaint_reasons")
def complaint_reasons(**kwargs):
    return [("delay", "Processing delay"), ("communication", "Communication concern"), ("settlement", "Settlement concern"), ("service", "Service quality")]


@DataSourceRegistry.register("claim_lookup")
def claim_lookup(*, params, **kwargs):
    claim = str(params.get("claim_number", "")).upper()
    mocked = {
        "CLM-2026-1001": {"claim_number": "CLM-2026-1001", "policy_number": "P/100/1003/2026/00005", "insured_name": "Demo Customer", "product": "Motor Comprehensive", "nature_of_claim": "Accidental damage"},
        "CLM-2026-2002": {"claim_number": "CLM-2026-2002", "policy_number": "P/200/2001/2026/00117", "insured_name": "Demo Member", "product": "Group Medical", "nature_of_claim": "Outpatient treatment"},
    }
    return mocked.get(claim)
