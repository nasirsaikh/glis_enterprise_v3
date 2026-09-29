from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_QUANTUM = Decimal("0.001")


def _decimal(value, default="0"):
    """Normalize model/config values before financial arithmetic."""
    if value in (None, ""):
        value = default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def calculate_member_premium(policy, plan, effective_date, end_date=None):
    if not policy.premium_calculation_enabled:
        return Decimal("0.000"), {"method": "DISABLED"}

    cfg = plan.premium_configuration or {}
    method = str(cfg.get("method", "PRORATA")).upper()
    annual = _decimal(plan.annual_premium)

    if method == "FULL":
        amount = annual
        snapshot = {
            "method": "FULL",
            "annual": str(annual),
        }
    elif method == "LUMP_SUM":
        amount = _decimal(cfg.get("amount"))
        snapshot = {
            "method": "LUMP_SUM",
            "amount": str(amount),
        }
    elif method == "PARTIAL":
        factor = _decimal(cfg.get("factor"), default="1")
        amount = annual * factor
        snapshot = {
            "method": "PARTIAL",
            "annual": str(annual),
            "factor": str(factor),
        }
    else:
        finish = end_date or policy.expiry_date
        covered_days = max((finish - effective_date).days + 1, 0)
        default_denominator = (policy.expiry_date - policy.start_date).days + 1
        denominator = _decimal(cfg.get("denominator", default_denominator))

        amount = (
            annual * Decimal(covered_days) / denominator
            if denominator > 0
            else Decimal("0")
        )
        snapshot = {
            "method": "PRORATA",
            "annual": str(annual),
            "covered_days": covered_days,
            "denominator": str(denominator),
        }

    amount = amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    snapshot["calculated_amount"] = str(amount)
    return amount, snapshot


def calculate_member_refund(enrollment, effective_date, refund_basis):
    """
    Deterministic refund calculation. Refund values are returned as negative
    transaction impact amounts so they reduce premium_after.
    """
    basis = str(refund_basis or "NONE").upper()
    original = _decimal(enrollment.premium_amount)
    if basis == "FULL":
        refund = original
        snapshot = {
            "method": "FULL_REFUND",
            "original_premium": str(original),
            "coverage_start_date": enrollment.coverage_start_date.isoformat(),
            "coverage_end_date": (
                enrollment.coverage_end_date.isoformat()
                if enrollment.coverage_end_date
                else enrollment.policy.expiry_date.isoformat()
            ),
            "effective_date": effective_date.isoformat(),
        }
    elif basis == "PRO_RATA":
        finish = enrollment.coverage_end_date or enrollment.policy.expiry_date
        start = enrollment.coverage_start_date
        total_days = max((finish - start).days + 1, 1)
        remaining_days = max((finish - effective_date).days + 1, 0)
        refund = original * Decimal(remaining_days) / Decimal(total_days)
        snapshot = {
            "method": "PRO_RATA_REFUND",
            "original_premium": str(original),
            "coverage_start_date": start.isoformat(),
            "coverage_end_date": finish.isoformat(),
            "effective_date": effective_date.isoformat(),
            "total_days": total_days,
            "remaining_days": remaining_days,
        }
    else:
        refund = Decimal("0")

        snapshot = {
            "method": "NO_REFUND",
            "original_premium": str(original),
            "effective_date": effective_date.isoformat(),
        }

    refund = refund.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    impact = -refund
    snapshot["refund_amount"] = str(refund)
    snapshot["calculated_amount"] = str(impact)
    return impact, snapshot
