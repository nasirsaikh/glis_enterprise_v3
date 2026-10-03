"""Policy-level aggregates, using one latest enrollment per member."""
from decimal import Decimal

from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum
from django.utils import timezone

from ..models import Member, MemberPolicyEnrollment, MemberTransaction, PolicyAccess
from .access import visible_transactions


def policy_dashboard(policy, user):
    today = timezone.localdate()
    latest = policy.enrollments.filter(member_id=OuterRef("member_id")).order_by(
        "-coverage_start_date", "-pk"
    ).values("pk")[:1]
    roster = policy.enrollments.filter(pk=Subquery(latest)).select_related("member", "benefit_plan")
    active = Q(enrollment_status=MemberPolicyEnrollment.Status.ACTIVE)
    totals = roster.aggregate(total=Count("pk"), active=Count("pk", filter=active))

    covered_roster = roster.none()
    if policy.status == policy.Status.ACTIVE and policy.start_date <= today <= policy.expiry_date:
        covered_roster = roster.filter(active, coverage_start_date__lte=today).filter(
            Q(coverage_end_date__isnull=True) | Q(coverage_end_date__gte=today)
        )
    covered = covered_roster.count()

    statuses = dict(roster.values_list("enrollment_status").annotate(total=Count("pk")))
    status_chart = [{"label": str(label), "total": statuses.get(code, 0)}
                    for code, label in MemberPolicyEnrollment.Status.choices]
    plans = list(roster.values("benefit_plan__code", "benefit_plan__name").annotate(
        total=Count("pk"), active=Count("pk", filter=active)
    ).order_by("benefit_plan__code"))
    for plan in plans:
        plan["inactive"] = plan["total"] - plan["active"]
    relationships = dict(roster.values_list("member__relationship").annotate(total=Count("pk")))
    endorsements = visible_transactions(user).filter(policy=policy).exclude(
        transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT
    )
    tx_totals = endorsements.aggregate(
        total=Count("pk", distinct=True), completed=Count("pk", distinct=True, filter=Q(status__in=["completed", "processed"])),
        last_completed_at=Max("processed_at"),
        open=Count("pk", distinct=True, filter=~Q(status__in=["completed", "processed", "rejected", "cancelled"])),
    )
    access = PolicyAccess.objects.filter(policy=policy, user=user, active=True, can_view=True)
    can_view_premium = user.is_superuser or user.has_perm("tpa.configure_tpa") or access.filter(can_view_premium=True).exists()
    can_view_members = (
        user.is_superuser
        or user.has_perm("tpa.configure_tpa")
        or user.has_perm("tpa.view_sensitive_member_data")
        or access.filter(can_view_members=True).exists()
    )

    member_roster = list(roster.order_by("member__first_name", "member__last_name", "member_id")) if can_view_members else []
    active_member_roster = [row for row in member_roster if row.enrollment_status == MemberPolicyEnrollment.Status.ACTIVE]
    inactive_member_roster = [row for row in member_roster if row.enrollment_status != MemberPolicyEnrollment.Status.ACTIVE]
    covered_ids = set(covered_roster.values_list("pk", flat=True)) if can_view_members else set()
    covered_member_roster = [row for row in member_roster if row.pk in covered_ids]

    return {
        "as_of": today, "total_members": totals["total"], "active_members": totals["active"],
        "inactive_members": totals["total"] - totals["active"], "covered_members": covered,
        "active_percentage": round(100 * totals["active"] / totals["total"], 1) if totals["total"] else 0,
        "status_chart": status_chart, "plan_rows": plans,
        "relationship_chart": [{"label": str(label), "total": relationships.get(code, 0)}
                               for code, label in Member.Relationship.choices],
        "endorsement_chart": [{"label": str(label), "total": count} for code, count in
                              endorsements.values_list("transaction_type").annotate(total=Count("pk", distinct=True))
                              for label in [dict(MemberTransaction.Type.choices).get(code, code)]],
        "endorsements": endorsements, "endorsement_totals": tx_totals,
        "can_view_members": can_view_members,
        "member_roster": member_roster,
        "active_member_roster": active_member_roster,
        "inactive_member_roster": inactive_member_roster,
        "covered_member_roster": covered_member_roster,
        "can_view_premium": can_view_premium,
        "active_premium": (roster.filter(active).aggregate(total=Sum("premium_amount"))["total"] or Decimal("0"))
                          if can_view_premium else None,
    }
