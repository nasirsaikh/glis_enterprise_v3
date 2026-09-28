from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import TransactionForm
from .models import Member, MemberTransaction, Policy, TPAOrganization, TransactionEvent
from .services.access import (
    can_access_tpa,
    can_create_tpa_transaction,
    visible_policies,
    visible_transactions,
)
from .services.ticketing import create_ticket_for_transaction


def _require_tpa_access(user):
    if not can_access_tpa(user):
        raise PermissionDenied("You do not have permission to access TPA Member Management.")


@login_required
def dashboard(request):
    _require_tpa_access(request.user)
    policies = visible_policies(request.user)
    txs = visible_transactions(request.user)
    context = {
        "active_sponsors": TPAOrganization.objects.filter(
            organization_type="CORPORATE",
            is_active=True,
            sponsored_policies__in=policies,
        ).distinct().count(),
        "active_policies": policies.filter(status=Policy.Status.ACTIVE).count(),
        "active_members": Member.objects.filter(
            enrollments__policy__in=policies,
            enrollments__enrollment_status="active",
        ).distinct().count(),
        "open_transactions": txs.exclude(
            status__in=["processed", "rejected", "cancelled"]
        ).count(),
        "needs_information": txs.filter(status="needs_information").count(),
        "pending_approval": txs.filter(status="pending_approval").count(),
        "stp_rate": round(
            (txs.filter(stp_eligible=True).count() / txs.count() * 100), 1
        ) if txs.exists() else 0,
        "transactions": txs[:50],
    }
    return render(request, "tpa/dashboard.html", context)


@login_required
def user_guide(request):
    _require_tpa_access(request.user)
    return render(request, "tpa/user_guide.html")


@login_required
def transaction_list(request):
    _require_tpa_access(request.user)
    return render(
        request,
        "tpa/transaction_list.html",
        {"transactions": visible_transactions(request.user)},
    )


@login_required
def transaction_create(request):
    _require_tpa_access(request.user)
    if not can_create_tpa_transaction(request.user):
        raise PermissionDenied("You do not have permission to create TPA transactions.")

    form = TransactionForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        tx = form.save(commit=False)
        tx.sponsor = tx.policy.sponsor
        tx.insurer = tx.policy.insurance_company
        tx.requester = request.user
        access = tx.policy.access_entries.filter(
            user=request.user,
            active=True,
        ).select_related("organization").first()
        tx.requester_organization = access.organization if access else tx.policy.sponsor
        tx.save()
        TransactionEvent.objects.create(
            transaction=tx,
            actor=request.user,
            event_type="transaction_created",
            summary="Transaction created",
        )
        return redirect("tpa:transaction_detail", reference=tx.reference)
    return render(request, "tpa/transaction_form.html", {"form": form})


@login_required
def transaction_detail(request, reference):
    _require_tpa_access(request.user)
    tx = get_object_or_404(
        visible_transactions(request.user),
        reference=reference,
    )
    return render(
        request,
        "tpa/transaction_detail.html",
        {
            "tx": tx,
            "actions": tx.member_actions.all(),
            "events": tx.events.all(),
        },
    )


@login_required
def transaction_submit(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(
        visible_transactions(request.user),
        reference=reference,
    )
    if tx.status != tx.Status.DRAFT:
        return redirect("tpa:transaction_detail", reference=reference)

    tx.submitted_at = timezone.now()
    tx.status = tx.Status.PENDING_VALIDATION
    tx.save(update_fields=["submitted_at", "status", "updated_at"])
    create_ticket_for_transaction(tx, actor=request.user)
    TransactionEvent.objects.create(
        transaction=tx,
        actor=request.user,
        event_type="submitted",
        summary="Transaction submitted",
    )
    return redirect("tpa:transaction_detail", reference=reference)
