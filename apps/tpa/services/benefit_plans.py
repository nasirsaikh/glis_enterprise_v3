"""Resolve only unambiguous plan references within the selected policy."""
import re
import unicodedata


def _normalized(value):
    return ' '.join(re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', str(value or '')).casefold()).split())


def resolve_benefit_plan(policy, reference):
    value = str(reference or '').strip()
    plans = list(policy.plans.filter(is_active=True))
    normalized = _normalized(value)
    if not normalized:
        raise ValueError('Benefit plan is required.')
    # A business plan code wins over a numeric database ID with the same text.
    candidates = [plan for plan in plans if _normalized(plan.code) == normalized]
    if not candidates:
        candidates = [plan for plan in plans if _normalized(plan.name) == normalized
                      or _normalized(f'{plan.code} {plan.name}') == normalized]
    if not candidates and value.isdecimal():
        candidates = [plan for plan in plans if plan.pk == int(value)]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise ValueError('Benefit plan name is ambiguous. Select its exact code from the policy plans.')
    raise ValueError('Benefit plan does not match an active plan on this policy. Select its exact code or name.')


def resolve_member_plan(policy, row):
    row = dict(row)
    if row.get('plan_code'):
        try:
            plan = resolve_benefit_plan(policy, row['plan_code'])
        except ValueError:
            return row  # Validation reports the unmatched/ambiguous evidence.
        if row['plan_code'] != plan.code:
            row['source_plan_reference'] = row['plan_code']
            row['plan_code'] = plan.code
    return row
