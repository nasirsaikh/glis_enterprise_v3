import hashlib
import uuid
from collections import Counter
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.ai.models import AIProviderConfig
from apps.tickets.models import TicketAttachment

from .forms import (
    BenefitPlanSetupForm,
    InboundEmailForm,
    MemberLookupRowForm,
    MemberRowForm,
    MemberUploadForm,
    PolicyEnrollmentForm,
    QueryMessageForm,
    QueryRaiseForm,
    SourceBundleUploadForm,
    TPAProcessingRowForm,
    TransactionForm,
)
from .models import (
    InboundEmail,
    BenefitPlan,
    InboundEmailAttachment,
    Member,
    MemberAction,
    MemberTransaction,
    Policy,
    PolicyAccess,
    TPAOrganization,
    TransactionEvent,
    TransactionQuery,
    TransactionQueryMessage,
)
from .services.access import (
    can_access_tpa,
    can_approve_tpa_transaction,
    can_create_endorsement,
    can_create_policy_enrollment,
    can_create_tpa_transaction,
    can_process_tpa_transaction,
    visible_policies,
    visible_transactions,
)
from .services.ai_intake import process_inbound_email
from .services.document_intake import create_source_documents, process_source_bundle
from .services.intake import import_member_spreadsheet
from .services.sample_data import build_sample_csv, build_sample_xlsx, sample_member_rows
from .services.ticketing import create_ticket_for_transaction
from .services.validation import validate_action
from .services.workflow import (
    approve_transaction,
    complete_tpa_transaction,
    post_query_message,
    raise_tpa_query,
    resolve_tpa_query,
    run_validation,
    start_tpa_processing,
    sync_from_ticket_approval,
    update_tpa_action,
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
    status_rows = list(
        txs.values("status")
        .annotate(total=models.Count("id"))
        .order_by("-total", "status")
    )
    source_rows = list(
        txs.values("source")
        .annotate(total=models.Count("id"))
        .order_by("-total", "source")
    )
    status_labels = dict(MemberTransaction.Status.choices)
    source_labels = dict(MemberTransaction.Source.choices)

    source_documents = list(tx.source_documents.all().order_by("-created_at"))
    for document in source_documents:
        payload = document.extracted_payload or {}
        result_count = payload.get("bundle_members_created")
        if result_count is None:
            result_count = payload.get("rows_created")
        document.result_count = result_count

    context = {
        "status_chart": [
            {
                "label": status_labels.get(row["status"], row["status"]),
                "value": row["total"],
            }
            for row in status_rows
        ],
        "source_chart": [
            {
                "label": source_labels.get(row["source"], row["source"]),
                "value": row["total"],
            }
            for row in source_rows
        ],
        "active_sponsors": TPAOrganization.objects.filter(
            organization_type__in=[
                TPAOrganization.Type.INDIVIDUAL,
                TPAOrganization.Type.CORPORATE,
            ],
            is_active=True,
            sponsored_policies__in=policies,
        ).distinct().count(),
        "active_policies": policies.filter(status=Policy.Status.ACTIVE).count(),
        "active_members": Member.objects.filter(
            enrollments__policy__in=policies,
            enrollments__enrollment_status="active",
        ).distinct().count(),
        "open_transactions": txs.exclude(
            status__in=[
                MemberTransaction.Status.PROCESSED,
                MemberTransaction.Status.COMPLETED,
                MemberTransaction.Status.REJECTED,
                MemberTransaction.Status.CANCELLED,
                MemberTransaction.Status.FAILED,
            ]
        ).count(),
        "needs_information": txs.filter(
            status__in=[
                MemberTransaction.Status.NEEDS_INFORMATION,
                MemberTransaction.Status.TPA_QUERY,
            ]
        ).count(),
        "pending_approval": txs.filter(status="pending_approval").count(),
        "stp_rate": round(
            (txs.filter(stp_eligible=True).count() / txs.count() * 100), 1
        ) if txs.exists() else 0,
        "ai_provider_count": AIProviderConfig.objects.filter(
            is_active=True,
            allow_sensitive_data=True,
        ).count(),
        "inbound_review": (
            InboundEmail.objects.filter(
                processing_state=InboundEmail.State.REVIEW,
            ).count()
            if (
                request.user.is_superuser
                or request.user.has_perm("tpa.configure_tpa")
            )
            else InboundEmail.objects.filter(
                processing_state=InboundEmail.State.REVIEW,
            ).filter(
                models.Q(created_by=request.user)
                | models.Q(transaction_id__in=txs.values_list("pk", flat=True))
            ).distinct().count()
        ),
        "transactions": txs[:50],
    }
    return render(request, "tpa/dashboard.html", context)


@login_required
def user_guide(request):
    _require_tpa_access(request.user)
    return render(request, "tpa/user_guide.html")


@login_required
def inbound_email_list(request):
    _require_tpa_access(request.user)
    visible_tx_ids = visible_transactions(request.user).values_list("pk", flat=True)
    emails = InboundEmail.objects.select_related(
        "transaction",
        "transaction__policy",
    )
    if not (
        request.user.is_superuser
        or request.user.has_perm("tpa.configure_tpa")
    ):
        emails = emails.filter(
            models.Q(created_by=request.user)
            | models.Q(transaction_id__in=visible_tx_ids)
        )
    emails = emails.distinct().order_by("-received_at", "-pk")
    return render(
        request,
        "tpa/inbound_email_list.html",
        {"emails": emails[:200]},
    )


@login_required
def inbound_email_create(request):
    _require_tpa_access(request.user)
    if not can_create_tpa_transaction(request.user):
        raise PermissionDenied(
            "You do not have permission to create TPA inbound email transactions."
        )

    form = InboundEmailForm(
        request.POST or None,
        request.FILES or None,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        email = form.save(commit=False)
        email.created_by = request.user
        email.provider = email.provider or "manual"
        email.provider_message_id = (
            email.provider_message_id
            or f"manual-{uuid.uuid4()}"
        )
        policy = form.cleaned_data.get("policy")
        ai_provider = form.cleaned_data.get("ai_provider")
        email.processing_hints = {
            "ai_provider_id": ai_provider.pk if ai_provider else None,
            "policy_id": policy.pk if policy else None,
            "policy_number": policy.policy_number if policy else "",
            "transaction_type": form.cleaned_data.get("transaction_type") or "",
            "effective_date": (
                form.cleaned_data["effective_date"].isoformat()
                if form.cleaned_data.get("effective_date")
                else ""
            ),
        }

        files = form.cleaned_data.get("attachments") or []
        email.attachment_metadata = [
            {
                "name": uploaded.name,
                "content_type": getattr(uploaded, "content_type", ""),
                "size": uploaded.size,
            }
            for uploaded in files
        ]
        email.save()

        for uploaded in files:
            digest = hashlib.sha256()
            for chunk in uploaded.chunks():
                digest.update(chunk)
            uploaded.seek(0)
            InboundEmailAttachment.objects.create(
                inbound_email=email,
                file=uploaded,
                original_name=uploaded.name,
                content_type=getattr(uploaded, "content_type", "") or "",
                size=uploaded.size,
                sha256=digest.hexdigest(),
            )

        if form.cleaned_data.get("process_with_ai"):
            try:
                tx = process_inbound_email(email, request.user)
                messages.success(
                    request,
                    f"Inbound email processed. TPA transaction {tx.reference} created.",
                )
            except Exception as exc:
                messages.warning(
                    request,
                    f"Inbound email saved but needs review: {exc}",
                )
        else:
            messages.success(request, "Inbound email saved.")

        return redirect("tpa:inbound_email_detail", email_id=email.pk)

    return render(
        request,
        "tpa/inbound_email_form.html",
        {"form": form},
    )


@login_required
def inbound_email_detail(request, email_id):
    _require_tpa_access(request.user)
    visible_tx_ids = visible_transactions(request.user).values_list("pk", flat=True)
    email_qs = InboundEmail.objects.select_related(
        "transaction",
        "transaction__policy",
    ).prefetch_related("attachments")
    if not (
        request.user.is_superuser
        or request.user.has_perm("tpa.configure_tpa")
    ):
        email_qs = email_qs.filter(
            models.Q(created_by=request.user)
            | models.Q(transaction_id__in=visible_tx_ids)
        )
    email = get_object_or_404(email_qs, pk=email_id)
    return render(
        request,
        "tpa/inbound_email_detail.html",
        {"email": email},
    )


@login_required
def inbound_email_process(request, email_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    email = get_object_or_404(
        InboundEmail,
        pk=email_id,
    )
    if not (
        request.user.is_superuser
        or request.user.has_perm("tpa.configure_tpa")
        or email.created_by_id == request.user.pk
        or (
            email.transaction_id
            and visible_transactions(request.user).filter(
                pk=email.transaction_id
            ).exists()
        )
    ):
        raise PermissionDenied

    try:
        tx = process_inbound_email(email, request.user)
        messages.success(
            request,
            f"AI processing completed. Transaction {tx.reference} is {tx.get_status_display()}.",
        )
    except Exception as exc:
        messages.error(request, f"AI processing requires review: {exc}")
    return redirect("tpa:inbound_email_detail", email_id=email.pk)


@login_required
def policy_enrollment_list(request):
    _require_tpa_access(request.user)
    policies = visible_policies(request.user).prefetch_related("plans", "transactions")
    if not (
        request.user.is_superuser
        or request.user.has_perm("tpa.configure_tpa")
    ):
        policies = policies.filter(
            models.Q(access_entries__user=request.user)
            | models.Q(transactions__requester=request.user)
        ).distinct()
    policies = policies.order_by("-created_at")
    rows = []
    for policy in policies:
        enrollment_tx = (
            policy.transactions.filter(
                transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT
            )
            .order_by("-created_at")
            .first()
        )
        rows.append({"policy": policy, "transaction": enrollment_tx})
    return render(
        request,
        "tpa/policy_enrollment_list.html",
        {"policy_rows": rows},
    )


@login_required
def policy_enrollment_create(request):
    _require_tpa_access(request.user)
    if not can_create_policy_enrollment(request.user):
        raise PermissionDenied(
            "You do not have permission to perform initial policy enrollment."
        )

    form = PolicyEnrollmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            policy = Policy.objects.create(
                sponsor=form.cleaned_data["sponsor"],
                insurance_company=form.cleaned_data["insurance_company"],
                tpa_organization=form.cleaned_data.get("tpa_organization"),
                policy_number=form.cleaned_data["policy_number"],
                policy_name=form.cleaned_data["policy_name"],
                start_date=form.cleaned_data["start_date"],
                expiry_date=form.cleaned_data["expiry_date"],
                status=Policy.Status.DRAFT,
                product_type="MEDICAL",
                currency=form.cleaned_data["currency"].upper(),
                stp_enabled=form.cleaned_data["stp_enabled"],
                premium_calculation_enabled=True,
                allowed_backdating_days=form.cleaned_data[
                    "allowed_backdating_days"
                ],
                configuration={"initial_setup": True},
            )
            BenefitPlan.objects.create(
                policy=policy,
                code=form.cleaned_data["plan_code"].upper(),
                name=form.cleaned_data["plan_name"],
                annual_premium=form.cleaned_data["annual_premium"],
                default_sum_insured=form.cleaned_data.get(
                    "default_sum_insured"
                ),
                premium_configuration={"method": "PRORATA"},
                is_active=True,
            )
            PolicyAccess.objects.update_or_create(
                organization=policy.sponsor,
                policy=policy,
                user=request.user,
                defaults={
                    "can_view": True,
                    "can_view_members": True,
                    "can_create_enrollment": True,
                    "can_create_endorsement": True,
                    "can_view_premium": True,
                    "can_approve": True,
                    "can_process": True,
                    "active": True,
                },
            )
            tx = MemberTransaction.objects.create(
                sponsor=policy.sponsor,
                insurer=policy.insurance_company,
                policy=policy,
                transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT,
                source=MemberTransaction.Source.PORTAL,
                effective_date=policy.start_date,
                requester=request.user,
                requester_organization=policy.sponsor,
                status=MemberTransaction.Status.DRAFT,
                remarks="Initial policy enrollment and member census setup.",
                metadata={"initial_policy_setup": True},
            )
            TransactionEvent.objects.create(
                transaction=tx,
                actor=request.user,
                event_type="policy_enrollment_created",
                summary="Initial policy enrollment created",
            )

        messages.success(
            request,
            "Policy setup created. Add plans and the initial member census, then submit for validation.",
        )
        return redirect("tpa:transaction_detail", reference=tx.reference)

    return render(
        request,
        "tpa/policy_enrollment_form.html",
        {"form": form},
    )


@login_required
def policy_plan_add(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(
        visible_transactions(request.user),
        reference=reference,
        transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT,
    )
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Plan setup is closed after initial enrollment leaves intake.")

    form = BenefitPlanSetupForm(request.POST, policy=tx.policy)
    if form.is_valid():
        plan = form.save(commit=False)
        plan.policy = tx.policy
        plan.code = form.cleaned_data["code"].upper()
        plan.premium_configuration = {"method": "PRORATA"}
        plan.save()
        messages.success(request, f"Benefit plan {plan.code} added.")
    else:
        messages.error(
            request,
            "; ".join(
                error
                for errors in form.errors.values()
                for error in errors
            ),
        )
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_list(request):
    _require_tpa_access(request.user)
    endorsements = visible_transactions(request.user).exclude(
        transaction_type=MemberTransaction.Type.NEW_POLICY_ENROLLMENT
    )
    return render(
        request,
        "tpa/transaction_list.html",
        {"transactions": endorsements},
    )


@login_required
def transaction_create(request):
    _require_tpa_access(request.user)
    if not can_create_endorsement(request.user):
        raise PermissionDenied("You do not have permission to create TPA endorsements.")

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

        if tx.transaction_type in {
            tx.Type.NEW_POLICY_ENROLLMENT,
            tx.Type.MEMBER_ADD,
        }:
            principal_reference = ""
            principal_action_id = str(display_data.get("principal_action_id") or "").strip()
            principal_member_id = str(display_data.get("principal_member_id") or "").strip()
            principal_employee_id = str(display_data.get("principal_employee_id") or "").strip()

            if principal_action_id.isdigit():
                principal_reference = f"action:{principal_action_id}"
            elif principal_member_id:
                if principal_member_id.isdigit():
                    principal_reference = f"member:{principal_member_id}"
                else:
                    principal_member = Member.objects.filter(
                        tpa_member_id=principal_member_id
                    ).first()
                    if principal_member:
                        principal_reference = f"member:{principal_member.pk}"
            elif principal_employee_id:
                principal_action = next(
                    (
                        item
                        for item in actions
                        if item.pk != action.pk
                        and str(
                            {
                                **(item.submitted_data or {}),
                                **(item.extracted_data or {}),
                                **(item.corrected_data or {}),
                            }.get("employee_id")
                            or ""
                        ).strip()
                        == principal_employee_id
                        and str(
                            {
                                **(item.submitted_data or {}),
                                **(item.extracted_data or {}),
                                **(item.corrected_data or {}),
                            }.get("relationship")
                            or ""
                        ).upper()
                        == Member.Relationship.PRINCIPAL
                    ),
                    None,
                )
                if principal_action:
                    principal_reference = f"action:{principal_action.pk}"
                else:
                    principal_member = Member.objects.filter(
                        employee_id=principal_employee_id,
                        relationship=Member.Relationship.PRINCIPAL,
                        enrollments__policy=tx.policy,
                        enrollments__enrollment_status="active",
                    ).first()
                    if principal_member:
                        principal_reference = f"member:{principal_member.pk}"

            action.edit_form = MemberRowForm(
                transaction=tx,
                initial={
                    **display_data,
                    "principal_reference": principal_reference,
                },
            )
        elif tx.transaction_type in {
            tx.Type.MEMBER_TERMINATE,
            tx.Type.MEMBER_DELETE,
        }:
            action.edit_form = MemberLookupRowForm(initial=display_data)
        else:
            action.edit_form = None

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
        "source_upload_form": SourceBundleUploadForm(),
        "plan_form": (
            BenefitPlanSetupForm(policy=tx.policy)
            if tx.transaction_type == tx.Type.NEW_POLICY_ENROLLMENT
            else None
        ),
        "initial_setup": tx.transaction_type == tx.Type.NEW_POLICY_ENROLLMENT,
        "source_documents": source_documents,
        "open_query": tx.queries.filter(
            status=TransactionQuery.Status.OPEN
        ).select_related("ticket").prefetch_related(
            "messages__sender",
            "messages__ticket_comment",
            "messages__ticket_comment__attachments",
        ).first(),
        "query_history": tx.queries.select_related(
            "ticket",
            "raised_by",
            "resolved_by",
        ).prefetch_related(
            "messages__sender",
            "messages__ticket_comment",
            "messages__ticket_comment__attachments",
        ),
        "query_raise_form": QueryRaiseForm(),
        "query_message_form": QueryMessageForm(),
        "can_start_tpa": (
            tx.status == tx.Status.SENT_TO_TPA
            and can_process_tpa_transaction(request.user, tx)
        ),
        "can_tpa_process": can_process_tpa_transaction(request.user, tx),
    }
    return render(request, "tpa/transaction_detail.html", context)


@login_required
def transaction_upload_sources(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Source upload is closed for this transaction.")

    form = SourceBundleUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(
            request,
            "; ".join(
                error
                for errors in form.errors.values()
                for error in errors
            ),
        )
        return redirect("tpa:transaction_detail", reference=reference)

    try:
        documents = create_source_documents(
            tx,
            form.cleaned_data["source_files"],
            actor=request.user,
        )
        actions = process_source_bundle(tx, documents, actor=request.user)
        if tx.submitted_at:
            tx.status = tx.Status.PENDING_VALIDATION
            tx.save(update_fields=["status", "updated_at"])
            run_validation(tx, actor=request.user)
        messages.success(
            request,
            f"{len(documents)} source file(s) processed; {len(actions)} member row(s) created.",
        )
    except (ValidationError, RuntimeError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("tpa:transaction_detail", reference=reference)


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
def transaction_edit_member(request, reference, action_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member correction is closed for this transaction.")

    action = get_object_or_404(tx.member_actions, pk=action_id)
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
            "Member correction was not saved: "
            + "; ".join(
                error
                for errors in form.errors.values()
                for error in errors
            ),
        )
        return redirect("tpa:transaction_detail", reference=reference)

    before = {
        **(action.submitted_data or {}),
        **(action.extracted_data or {}),
        **(action.corrected_data or {}),
    }
    corrected = _serialize_form_data(form.cleaned_data)
    action.corrected_data = corrected
    action.save(update_fields=["corrected_data", "updated_at"])
    TransactionEvent.objects.create(
        transaction=tx,
        actor=request.user,
        event_type="member_row_corrected",
        summary=f"Member row {action.row_number or action.pk} corrected",
        details={
            "action_id": action.pk,
            "before": before,
            "after": corrected,
        },
    )

    if tx.status == tx.Status.DRAFT:
        validate_action(action)
    else:
        run_validation(tx, actor=request.user)

    messages.success(
        request,
        f"Member row {action.row_number or action.pk} corrected and revalidated.",
    )
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
    if tx.status in {
        tx.Status.PROCESSED,
        tx.Status.COMPLETED,
        tx.Status.REJECTED,
        tx.Status.CANCELLED,
        tx.Status.FAILED,
    }:
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
def transaction_tpa_start(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    try:
        start_tpa_processing(tx, request.user)
        messages.success(request, "TPA processing started.")
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_tpa_action(request, reference, action_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    action = get_object_or_404(tx.member_actions, pk=action_id)
    form = TPAProcessingRowForm(request.POST)
    if form.is_valid():
        try:
            update_tpa_action(
                action,
                request.user,
                card_number=form.cleaned_data["card_number"],
                effective_date=form.cleaned_data["effective_date"],
                amount=form.cleaned_data["amount"],
            )
            messages.success(request, "TPA member processing data updated.")
        except (PermissionError, ValueError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(
            request,
            "; ".join(
                error
                for errors in form.errors.values()
                for error in errors
            ),
        )
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_raise_query(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    form = QueryRaiseForm(request.POST)
    if form.is_valid():
        try:
            raise_tpa_query(
                tx,
                request.user,
                form.cleaned_data["subject"],
                form.cleaned_data["message"],
            )
            messages.warning(
                request,
                "TPA query raised. The conversation is available below in this workflow step.",
            )
        except (PermissionError, ValueError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Enter a query subject and message.")
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_query_message(request, reference, query_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    query = get_object_or_404(
        tx.queries.select_related(
            "transaction",
            "transaction__ticket",
            "ticket",
        ),
        pk=query_id,
        status=TransactionQuery.Status.OPEN,
    )
    form = QueryMessageForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            comment = post_query_message(
                query,
                request.user,
                form.cleaned_data["message"],
            )
            for uploaded in form.cleaned_data.get("attachments") or []:
                TicketAttachment.objects.create(
                    ticket=query.ticket,
                    comment=comment,
                    uploaded_by=request.user,
                    file=uploaded,
                    original_name=uploaded.name,
                    content_type=getattr(uploaded, "content_type", "")
                    or "application/octet-stream",
                    size=uploaded.size,
                    is_restricted=True,
                    scan_status="clean",
                    source_field="tpa_query_chat",
                )
            messages.success(request, "Query message sent.")
        except (PermissionError, ValueError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Enter a query message.")
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_resolve_query(request, reference, query_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    query = get_object_or_404(tx.queries, pk=query_id)
    try:
        resolve_tpa_query(query, request.user)
        messages.success(request, "Query resolved and TPA processing resumed.")
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_tpa_complete(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    try:
        complete_tpa_transaction(tx, request.user)
        tx.refresh_from_db()
        messages.success(
            request,
            "TPA processing completed. Member/policy records have been updated.",
        )
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("tpa:transaction_detail", reference=reference)


@login_required
def transaction_process(request, reference):
    """Backward-compatible endpoint; finalization must use the full TPA completion gate."""
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    try:
        complete_tpa_transaction(tx, request.user)
        tx.refresh_from_db()
        if tx.status == tx.Status.COMPLETED:
            messages.success(request, "TPA transaction completed successfully.")
        else:
            messages.error(
                request,
                "Processing completed with row errors. Review the row results.",
            )
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("tpa:transaction_detail", reference=reference)
