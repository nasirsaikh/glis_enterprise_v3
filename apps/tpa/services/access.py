from django.db.models import Q
from ..models import MemberTransaction, Policy

def visible_policies(user):
    qs=Policy.objects.select_related("sponsor","insurance_company")
    if not user.is_authenticated: return qs.none()
    if user.is_superuser or user.has_perm("tpa.configure_tpa"): return qs
    return qs.filter(Q(access_entries__user=user, access_entries__active=True, access_entries__can_view=True)).distinct()

def visible_transactions(user):
    qs=MemberTransaction.objects.select_related("policy","sponsor","insurer","ticket")
    if not user.is_authenticated: return qs.none()
    if user.is_superuser or user.has_perm("tpa.configure_tpa"): return qs
    return qs.filter(Q(requester=user)|Q(policy__access_entries__user=user,policy__access_entries__active=True,policy__access_entries__can_view=True)).distinct()
