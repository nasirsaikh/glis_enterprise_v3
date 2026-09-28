from datetime import date
from django.utils import timezone
from ..models import Member, MemberAction, MemberPolicyEnrollment, Policy

NON_BYPASSABLE={"POLICY_NOT_AUTHORIZED","POLICY_MISSING","PLAN_CROSS_POLICY","DUPLICATE_PROCESSED_TRANSACTION","CONCURRENCY_CONFLICT"}

def error(code, field, message, blocking=True):
    return {"code":code,"field":field,"message":message,"blocking":blocking,"non_bypassable":code in NON_BYPASSABLE}

def validate_action(action):
    tx=action.transaction
    data={**(action.extracted_data or {}), **(action.corrected_data or {})}
    errors=[]
    if tx.policy.status != Policy.Status.ACTIVE: errors.append(error("POLICY_NOT_ACTIVE","policy","Policy is not active."))
    if not (tx.policy.start_date <= tx.effective_date <= tx.policy.expiry_date): errors.append(error("EFFECTIVE_DATE_OUTSIDE_POLICY","effective_date","Effective date is outside the policy period."))
    if tx.effective_date < timezone.localdate() and (timezone.localdate()-tx.effective_date).days > tx.policy.allowed_backdating_days:
        errors.append(error("BACKDATING_LIMIT","effective_date","Effective date exceeds allowed backdating."))
    for field in ("first_name","last_name","date_of_birth","gender","relationship","plan_code"):
        if not data.get(field): errors.append(error("REQUIRED_FIELD",field,f"{field.replace('_',' ').title()} is required."))
    plan=tx.policy.plans.filter(code=data.get("plan_code"),is_active=True).first()
    if data.get("plan_code") and not plan: errors.append(error("INVALID_PLAN","plan_code","Plan does not exist or is inactive for this policy."))
    emp=(data.get("employee_id") or "").strip()
    nid=(data.get("national_id") or "").strip()
    if tx.transaction_type in {tx.Type.NEW_POLICY_ENROLLMENT,tx.Type.MEMBER_ADD}:
        if emp and MemberPolicyEnrollment.objects.filter(policy=tx.policy,enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,member__employee_id=emp).exists():
            errors.append(error("MEMBER_ALREADY_ACTIVE","employee_id","Member is already active under this policy."))
        if nid and MemberPolicyEnrollment.objects.filter(policy=tx.policy,enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,member__national_id=nid).exists():
            errors.append(error("DUPLICATE_NATIONAL_ID","national_id","National/Civil ID is already active under this policy."))
    action.validation_errors=errors
    action.validation_status=MemberAction.Result.ERROR if any(x["blocking"] for x in errors) else (MemberAction.Result.WARNING if errors else MemberAction.Result.VALID)
    action.save(update_fields=["validation_errors","validation_status","updated_at"])
    return errors

def validate_transaction(tx):
    actions=list(tx.member_actions.all())
    checks=0; passed=0
    for a in actions:
        validate_action(a); checks+=1
        if a.validation_status == MemberAction.Result.VALID: passed+=1
    tx.validation_score=100 if not checks else round((passed/checks)*100,2)
    tx.status=tx.Status.VALIDATION_FAILED if any(a.validation_status==MemberAction.Result.ERROR for a in actions) else tx.Status.PENDING_APPROVAL
    tx.save(update_fields=["validation_score","status","updated_at"])
    return actions
