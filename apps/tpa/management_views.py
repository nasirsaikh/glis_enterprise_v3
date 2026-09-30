"""Policy overview, prompt coaching and editable draft metadata."""
import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from services.pagination import table_page
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.ai.models import AIExtractionProfile
from apps.ai.runtime import generate_json
from apps.core.models import AuditLog

from .forms import ExtractionPromptForm, PROMPT_TASKS, PromptExampleForm, PromptPreviewForm, TransactionDetailsForm
from .models import InboundEmail, MemberAction, MemberTransaction, TransactionEvent
from .services.access import can_edit_tpa_intake, visible_policies, visible_transactions
from .services.ai_intake import _profile_prompt
from .services.document_intake import _system_prompt
from .services.extraction import normalize_ai_payload, select_profile, select_provider
from .services.policy_dashboard import policy_dashboard
from .services.ticketing import close_transaction_ticket

EDITABLE_STATUSES = {MemberTransaction.Status.DRAFT, MemberTransaction.Status.PENDING_VALIDATION,
                     MemberTransaction.Status.NEEDS_INFORMATION, MemberTransaction.Status.VALIDATION_FAILED}


def can_manage_prompts(user):
    return user.is_authenticated and (user.is_superuser or user.has_perm("tpa.configure_tpa") or user.has_perm("ai.configure_ai"))


@login_required
def policy_enrollment_detail(request, policy_id):
    policy = get_object_or_404(visible_policies(request.user).select_related("tpa_organization"), pk=policy_id)
    data = policy_dashboard(policy, request.user)
    endorsements = data.pop("endorsements").annotate(member_count=Count("member_actions", distinct=True))
    status = request.GET.get("status", "")
    if status in MemberTransaction.Status.values:
        endorsements = endorsements.filter(status=status)
    else:
        status = ""
    query = request.GET.get("q", "").strip()
    if query:
        from django.db.models import Q
        endorsements = endorsements.filter(
            Q(reference__icontains=query) | Q(transaction_type__icontains=query)
            | Q(ticket__reference__icontains=query)
        )
    pagination = table_page(request, endorsements.order_by("-created_at", "-pk"))
    page = pagination["page_obj"]
    enrollment_tx = visible_transactions(request.user).filter(policy=policy, transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT).order_by("-created_at").first()
    return render(request, "tpa/policy_enrollment_detail.html", {
        **data, **pagination, "policy": policy, "endorsements": page, "enrollment_tx": enrollment_tx,
        "status_filter": status, "status_choices": MemberTransaction.Status.choices,
        "policy_chart_data": {**{key: data[key] for key in ["status_chart", "relationship_chart", "plan_rows", "endorsement_chart"]},
                              "active_chart": [{"label": "Active", "total": data["active_members"]}, {"label": "Inactive", "total": data["inactive_members"]}]},
    })


@login_required
def inbound_email_training(request):
    # Prompt profiles and examples are maintained in Django admin.
    if not can_manage_prompts(request.user):
        raise PermissionDenied("AI prompt configuration requires TPA or AI configuration permission.")
    return redirect("admin:ai_aiextractionprofile_changelist")


@login_required
@transaction.atomic
def transaction_edit_details(request, reference):
    tx = _editable_transaction(request, reference, lock=request.method == "POST")
    before = {key: str(getattr(tx, key) or "") for key in ["transaction_type", "effective_date", "refund_basis", "expected_reactivation_date", "remarks"]}
    form = TransactionDetailsForm(request.POST or None, instance=tx, user=request.user)
    if request.method == "POST" and form.is_valid():
        tx = form.save(commit=False)
        tx.status = tx.Status.DRAFT
        tx.validation_score = Decimal("0")
        tx.validation_completed_at = None
        tx.stp_eligible = False
        tx.stp_blockers = ["REVALIDATION_REQUIRED"]
        tx.validation_bypassed = False
        tx.validation_bypass_reason = ""
        tx.validation_bypassed_by = None
        tx.validation_bypassed_at = None
        tx.submitted_at = None
        tx.approved_at = None
        tx.approved_by = None
        tx.physical_card_required = tx.policy.physical_card_required and tx.transaction_type == tx.Type.MEMBER_ADD
        tx.premium_adjustment = Decimal("0")
        tx.premium_after = tx.premium_before
        tx.save()
        for row in tx.member_actions.all():
            for attr in ["submitted_data", "extracted_data", "corrected_data"]:
                values = dict(getattr(row, attr) or {})
                if str(values.get("effective_date") or "") == before["effective_date"]:
                    values["effective_date"] = tx.effective_date.isoformat()
                    setattr(row, attr, values)
            row.action = tx.transaction_type
            row.validation_status = MemberAction.Result.ERROR
            row.validation_errors = [{"code": "REVALIDATION_REQUIRED", "message": "Request details changed. Submit again to revalidate."}]
            row.calculated_premium = Decimal("0")
            row.calculation_snapshot = {}
            row.tpa_effective_date = None
            row.tpa_premium_amount = None
            row.tpa_override_reason = ""
            row.processing_status = ""
            row.processing_message = ""
            row.save()
        after = {key: str(getattr(tx, key) or "") for key in before}
        TransactionEvent.objects.create(transaction=tx, actor=request.user, event_type="details_updated", summary="Request details changed; validation is required again.", details={"before": before, "after": after})
        AuditLog.record(request=request, action="tpa.details_updated", instance=tx, summary=f"Request details updated: {tx.reference}", changes={"before": before, "after": after}, sensitivity="sensitive")
        messages.success(request, "Details saved. Review the member rows and submit again for validation.")
        url = reverse("tpa:transaction_detail", args=[tx.reference])
        if request.headers.get("HX-Request") == "true":
            return HttpResponse(headers={"HX-Redirect": url})
        return redirect(url)
    return render(request, "tpa/partials/transaction_details_form.html" if request.headers.get("HX-Request") == "true" else "tpa/transaction_details_form.html", {"tx": tx, "form": form})


@login_required
@require_POST
@transaction.atomic
def transaction_delete_draft(request, reference):
    tx = _editable_transaction(request, reference, lock=True)
    if (tx.status != tx.Status.DRAFT or tx.transaction_type == tx.Type.NEW_POLICY_ENROLLMENT
            or tx.member_actions.filter(processed_at__isnull=False).exists()):
        raise PermissionDenied("Only unprocessed draft endorsements can be deleted.")
    AuditLog.record(request=request, action="tpa.draft_deleted", instance=tx, summary=f"Draft endorsement deleted: {tx.reference}", changes={"reference": tx.reference, "policy": tx.policy.policy_number, "member_rows": tx.member_actions.count()})
    close_transaction_ticket(tx, request.user, reason=f"Draft endorsement {tx.reference} was deleted.")
    tx.source_emails.update(processing_state=InboundEmail.State.REVIEW, processing_error=f"Linked draft {tx.reference} was deleted. Review before reprocessing.")
    tx.delete()
    messages.success(request, f"Draft endorsement {reference} deleted.")
    url = reverse("tpa:transaction_list")
    if request.headers.get("HX-Request") == "true":
        return HttpResponse(headers={"HX-Redirect": url})
    return redirect(url)
