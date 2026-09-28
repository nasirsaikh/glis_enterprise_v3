from collections import Counter
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    MemberLookupRowForm,
    MemberRowForm,
    MemberUploadForm,
    TransactionForm,
)
from .models import Member, MemberAction, MemberTransaction, Policy, TPAOrganization, TransactionEvent
from .services.access import (
    can_access_tpa,
    can_approve_tpa_transaction,
    can_create_tpa_transaction,
    can_process_tpa_transaction,
    visible_policies,
    visible_transactions,
)
from .services.intake import import_member_spreadsheet
from .services.sample_data import build_sample_csv, build_sample_xlsx, sample_member_rows
from .services.ticketing import create_ticket_for_transaction
from .services.validation import validate_action
from .services.workflow import (
    approve_transaction,
    process_transaction,
    run_validation,
    sync_from_ticket_approval,
)


INTAKE_EDITABLE_STATUSES = {
    MemberTransaction.Status.DRAFT,
    MemberTransaction.Status.PENDING_VALIDATION,
    MemberTransaction.Status.NEEDS_INFORMATION,
    MemberTransaction.Status.VALIDATION_FAILED,
}


def _require_tpa_access(user):
    if not can_access_tpa(user):
        raise PermissionDenied("You do not have permission to access TPA Member Management.")


def _serialize_form_data(cleaned_data):
    data = {}
    for key, value in cleaned_data.items():
        if isinstance(value, date):
            data[key] = value.isoformat()
        elif value is not None:
            data[key] = str(value).strip()
        else:
            data[key] = ""
    return data


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
        messages.success(
            request,
            "Transaction created. Add member rows or upload a spreadsheet, then submit for validation.",
        )
        return redirect("tpa:transaction_detail", reference=tx.reference)
    return render(request, "tpa/transaction_form.html", {"form": form})


@login_required
def transaction_detail(request, reference):
    _require_tpa_access(request.user)
    tx = get_object_or_404(
        visible_transactions(request.user).prefetch_related(
            "member_actions", "events", "source_documents"
        ),
        reference=reference,
    )

    if tx.status == tx.Status.PENDING_APPROVAL and tx.ticket_id:
        tx = sync_from_ticket_approval(tx, actor=request.user)

    actions = list(tx.member_actions.all().order_by("row_number", "pk"))
    for action in actions:
        display_data = {
            **(action.submitted_data or {}),
            **(action.extracted_data or {}),
            **(action.corrected_data or {}),
        }
        action.display_first_name = display_data.get("first_name") or "—"
        action.display_last_name = display_data.get("last_name") or ""
        action.display_employee_id = display_data.get("employee_id") or "—"
        action.display_plan_code = display_data.get("plan_code") or "—"

    valid_count = sum(a.validation_status == MemberAction.Result.VALID for a in actions)
    warning_count = sum(a.validation_status == MemberAction.Result.WARNING for a in actions)
    error_count = sum(a.validation_status == MemberAction.Result.ERROR for a in actions)
    success_count = valid_count + warning_count
    success_rate = round((success_count / len(actions)) * 100, 1) if actions else 0

    error_codes = Counter()
    for action in actions:
        for item in action.validation_errors or []:
            error_codes[item.get("code") or "OTHER"] += 1

    quality_chart = [
        {"label": "Valid", "value": valid_count},
        {"label": "Warnings", "value": warning_count},
        {"label": "Errors", "value": error_count},
    ]
    error_chart = [
        {"label": code.replace("_", " ").title(), "value": count}
        for code, count in error_codes.most_common(8)
    ]

    is_add = tx.transaction_type in {
        tx.Type.NEW_POLICY_ENROLLMENT,
        tx.Type.MEMBER_ADD,
    }
    member_form = (
        MemberRowForm(transaction=tx)
        if is_add
        else MemberLookupRowForm()
    )

    context = {
        "tx": tx,
        "actions": actions,
        "events": tx.events.all(),
        "member_form": member_form,
        "upload_form": MemberUploadForm(),
        "can_edit_intake": tx.status in INTAKE_EDITABLE_STATUSES
        and tx.transaction_type != tx.Type.POLICY_CANCEL,
        "can_approve": can_approve_tpa_transaction(request.user, tx),
        "can_process": can_process_tpa_transaction(request.user, tx),
        "ticket_approval_pending": bool(
            tx.ticket_id and tx.ticket.approval_state == "pending"
        ),
        "valid_count": valid_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "success_rate": success_rate,
        "quality_chart": quality_chart,
        "error_chart": error_chart,
        "sample_rows": sample_member_rows(tx),
    }
    return render(request, "tpa/transaction_detail.html", context)


@login_required
def transaction_sample_file(request, reference, kind, file_format):
    _require_tpa_access(request.user)
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)

    if kind not in {"valid", "errors"}:
        raise PermissionDenied("Unknown sample dataset.")
    if file_format not in {"csv", "xlsx"}:
        raise PermissionDenied("Unknown sample file format.")

    rows = sample_member_rows(tx, include_errors=(kind == "errors"))
    if file_format == "csv":
        payload = build_sample_csv(rows)
        content_type = "text/csv; charset=utf-8"
    else:
        payload = build_sample_xlsx(rows)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    filename = f"{tx.policy.policy_number}_tpa_{kind}_sample.{file_format}"
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def transaction_add_member(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member intake is closed for this transaction.")

    is_add = tx.transaction_type in {
        tx.Type.NEW_POLICY_ENROLLMENT,
        tx.Type.MEMBER_ADD,
    }
    form = (
        MemberRowForm(request.POST, transaction=tx)
        if is_add
        else MemberLookupRowForm(request.POST)
    )
    if not form.is_valid():
        messages.error(
            request,
            "Member row was not added: "
            + "; ".join(
                error
                for errors in form.errors.values()
                for error in errors
            ),
        )
        return redirect("tpa:transaction_detail", reference=reference)

    row_number = (
        tx.member_actions.order_by("-row_number")
        .values_list("row_number", flat=True)
        .first()
        or 0
    ) + 1
    action = MemberAction.objects.create(
        transaction=tx,
        action=tx.transaction_type,
        row_number=row_number,
        submitted_data=_serialize_form_data(form.cleaned_data),
        corrected_data=_serialize_form_data(form.cleaned_data),
    )

    if tx.status == tx.Status.DRAFT:
        validate_action(action)
    else:
        run_validation(tx, actor=request.user)

    messages.success(request, f"Member row {row_number} added.")
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_upload_members(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member intake is closed for this transaction.")

    form = MemberUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Select a CSV or XLSX member file.")
        return redirect("tpa:transaction_detail", reference=reference)

    try:
        created = import_member_spreadsheet(
            tx,
            form.cleaned_data["member_file"],
            actor=request.user,
        )
        if tx.status == tx.Status.DRAFT:
            for action in created:
                validate_action(action)
        else:
            run_validation(tx, actor=request.user)
        messages.success(request, f"{len(created)} member row(s) imported and checked.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))

    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_remove_member(request, reference, action_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member intake is closed for this transaction.")

    action = get_object_or_404(tx.member_actions, pk=action_id)
    action.delete()
    if tx.status != tx.Status.DRAFT:
        run_validation(tx, actor=request.user)
    messages.success(request, "Member row removed.")
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_submit(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if tx.status != tx.Status.DRAFT:
        return redirect("tpa:transaction_detail", reference=reference)

    tx.submitted_at = timezone.now()
    tx.status = tx.Status.PENDING_VALIDATION
    tx.save(update_fields=["submitted_at", "status", "updated_at"])
    create_ticket_for_transaction(tx, actor=request.user)
    run_validation(tx, actor=request.user)
    TransactionEvent.objects.create(
        transaction=tx,
        actor=request.user,
        event_type="submitted",
        summary="Transaction submitted",
    )
    messages.success(request, "Transaction submitted and validation completed.")
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_validate(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if tx.status == tx.Status.DRAFT:
        messages.error(request, "Submit the transaction before running workflow validation.")
        return redirect("tpa:transaction_detail", reference=reference)
    if tx.status in {tx.Status.PROCESSED, tx.Status.REJECTED, tx.Status.CANCELLED}:
        raise PermissionDenied("This transaction is closed.")

    run_validation(tx, actor=request.user)
    messages.success(request, "Validation rerun completed.")
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_approve(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    try:
        approve_transaction(tx, request.user)
        messages.success(request, "TPA transaction approved.")
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_process(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    try:
        process_transaction(tx, request.user)
        tx.refresh_from_db()
        if tx.status == tx.Status.PROCESSED:
            messages.success(request, "TPA transaction processed successfully.")
        else:
            messages.error(request, "Processing completed with row errors. Review the row results.")
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("tpa:transaction_detail", reference=reference)
