import hashlib
import json
import uuid
from collections import Counter
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.ai.models import AIProviderConfig
from apps.tickets.models import TicketAttachment

from .forms import (
    BenefitPlanSetupForm,
    BulkCardSelectionForm,
    CardDispatchForm,
    InboundEmailForm,
    InitialBenefitPlanFormSet,
    MemberDemographicUpdateForm,
    MemberLookupRowForm,
    MemberRowForm,
    MemberUploadForm,
    PolicyEnrollmentForm,
    QueryMessageForm,
    QueryRaiseForm,
    SourceBundleUploadForm,
    TPAProcessingRowForm,
    TransactionForm,
    TransactionRejectionForm,
)
from .models import (
    InboundEmail,
    BenefitPlan,
    CardDispatch,
    InboundEmailAttachment,
    Member,
    MemberAction,
    MemberTransaction,
    Policy,
    PolicyAccess,
    SourceDocument,
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
    can_edit_tpa_intake,
    can_process_tpa_transaction,
    can_view_query_attachment,
    can_view_query_message,
    can_view_transaction_query,
    visible_policies,
    visible_shared_internal_messages,
    visible_transaction_queries,
    visible_transactions,
)
from .services.ai_intake import process_inbound_email
from .services.document_intake import create_source_documents, process_source_bundle
from .services.intake import import_member_spreadsheet
from .services.mailbox import mailbox_health, poll_inbound_mailbox
from .services.member_selection import (
    add_enrollments_to_transaction,
    populate_policy_cancellation,
    resolve_card_numbers,
    selectable_enrollments,
)
from .services.sample_data import build_sample_csv, build_sample_xlsx, sample_member_rows
from .services.ticketing import create_ticket_for_transaction
from .services.validation import validate_action
from .services.wizard import CLOSED_STATUSES, get_transaction_wizard
from .services.workflow import (
    approve_transaction,
    complete_tpa_transaction,
    post_query_message,
    raise_transaction_query,
    raise_tpa_query,
    reject_transaction,
    resolve_tpa_query,
    share_query_message_with_client,
    run_validation,
    start_tpa_processing,
    sync_from_ticket_approval,
    update_card_dispatch,
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


def _require_intake_edit(user, tx):
    if not can_edit_tpa_intake(user, tx):
        raise PermissionDenied("You have read-only access to this TPA transaction.")


def _is_htmx(request):
    return (
        request.headers.get("HX-Request", "").lower() == "true"
        and request.headers.get("HX-History-Restore-Request", "").lower() != "true"
    )


def _transaction_response(request, tx, *, step=None, forms=None):
    """Refresh the whole workspace, including status and navigation, in one swap."""
    tx.refresh_from_db()
    selected = step if step is not None else request.POST.get("wizard_step")
    if _is_htmx(request) or forms:
        return transaction_detail(
            request, tx.reference, selected_step=selected, form_overrides=forms
        )
    wizard = get_transaction_wizard(tx, request.user, selected)
    return redirect(wizard["step_url"])


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
    is_mail_admin = (
        request.user.is_superuser
        or request.user.has_perm("tpa.configure_tpa")
    )
    if not is_mail_admin:
        emails = emails.filter(
            models.Q(created_by=request.user)
            | models.Q(transaction_id__in=visible_tx_ids)
        )
    emails = emails.distinct().order_by("-received_at", "-pk")
    health = mailbox_health()
    health["awaiting_review"] = InboundEmail.objects.filter(
        processing_state__in=[
            InboundEmail.State.REVIEW,
            InboundEmail.State.UNAUTHORIZED,
        ]
    ).count()
    health["ignored"] = InboundEmail.objects.filter(
        processing_state=InboundEmail.State.IGNORED
    ).count()
    health["failed"] = InboundEmail.objects.filter(
        processing_state=InboundEmail.State.FAILED
    ).count()
    return render(
        request,
        "tpa/inbound_email_list.html",
        {
            "emails": emails[:200],
            "mailbox_health": health,
            "can_sync_mailbox": is_mail_admin,
        },
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
                if tx is not None:
                    messages.success(
                        request,
                        f"Inbound email processed. TPA transaction {tx.reference} created.",
                    )
                else:
                    email.refresh_from_db()
                    messages.warning(
                        request,
                        f"Inbound email retained with status {email.get_processing_state_display()}: "
                        f"{email.processing_error or email.classification or 'review required'}.",
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
        {
            "email": email,
            "can_view_ai_source": (
                request.user.is_superuser
                or request.user.has_perm("tpa.view_ai_source_data")
                or request.user.has_perm("tpa.configure_tpa")
            ),
        },
    )


@login_required
def inbound_email_attachment(request, email_id, attachment_id):
    _require_tpa_access(request.user)
    visible_tx_ids = visible_transactions(request.user).values_list("pk", flat=True)
    email_qs = InboundEmail.objects.all()
    if not (
        request.user.is_superuser
        or request.user.has_perm("tpa.configure_tpa")
    ):
        email_qs = email_qs.filter(
            models.Q(created_by=request.user)
            | models.Q(transaction_id__in=visible_tx_ids)
        )
    email = get_object_or_404(email_qs, pk=email_id)
    attachment = get_object_or_404(email.attachments, pk=attachment_id)
    attachment.file.open("rb")
    return FileResponse(
        attachment.file,
        as_attachment=True,
        filename=attachment.original_name,
        content_type=attachment.content_type or "application/octet-stream",
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
        if tx is not None:
            messages.success(
                request,
                f"AI processing completed. Transaction {tx.reference} is {tx.get_status_display()}.",
            )
        else:
            email.refresh_from_db()
            messages.warning(
                request,
                f"Email retained as {email.get_processing_state_display()}: "
                f"{email.processing_error or email.classification or 'review required'}.",
            )
    except Exception as exc:
        messages.error(request, f"AI processing requires review: {exc}")
    return redirect("tpa:inbound_email_detail", email_id=email.pk)


@login_required
def inbound_email_sync_now(request):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    if not (
        request.user.is_superuser
        or request.user.has_perm("tpa.configure_tpa")
    ):
        raise PermissionDenied("Mailbox synchronization requires TPA configuration authority.")
    try:
        result = poll_inbound_mailbox(actor=request.user)
        messages.success(
            request,
            "Mailbox synchronization completed: "
            f"created={result.get('created', 0)}, "
            f"processed={result.get('processed', 0)}, "
            f"review={result.get('review', 0)}, "
            f"ignored={result.get('ignored', 0)}, "
            f"skipped={result.get('skipped', 0)}.",
        )
    except Exception as exc:
        messages.error(request, f"Mailbox synchronization failed: {exc}")
    return redirect("tpa:inbound_email_list")


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

    form = PolicyEnrollmentForm(request.POST or None, user=request.user)
    uses_formset = request.method != "POST" or "plans-TOTAL_FORMS" in request.POST
    plan_formset = InitialBenefitPlanFormSet(
        request.POST if request.method == "POST" and uses_formset else None,
        prefix="plans",
        initial=(
            [{
                "code": "GOLD",
                "name": "Gold",
                "annual_premium": "0.000",
                "default_sum_insured": "",
                "is_active": True,
            }]
            if request.method != "POST"
            else None
        ),
    )

    form_valid = form.is_valid() if request.method == "POST" else False
    plans_valid = (
        plan_formset.is_valid()
        if request.method == "POST" and uses_formset
        else True
    )
    plan_rows = []
    if request.method == "POST" and form_valid and plans_valid:
        if uses_formset:
            for plan_form in plan_formset.forms:
                data = getattr(plan_form, "cleaned_data", {}) or {}
                if data.get("DELETE"):
                    continue
                if not str(data.get("code") or "").strip():
                    continue
                plan_rows.append(data)
        else:
            code = str(form.cleaned_data.get("plan_code") or "").strip()
            name = str(form.cleaned_data.get("plan_name") or "").strip()
            if code and name:
                plan_rows.append({
                    "code": code,
                    "name": name,
                    "description": "",
                    "annual_premium": form.cleaned_data.get("annual_premium") or 0,
                    "default_sum_insured": form.cleaned_data.get("default_sum_insured"),
                    "is_active": True,
                })

        if not plan_rows:
            form.add_error(None, "Add at least one benefit plan.")
        else:
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
                    allowed_backdating_days=form.cleaned_data["allowed_backdating_days"],
                    configuration={"initial_setup": True},
                )
                for plan_data in plan_rows:
                    BenefitPlan.objects.create(
                        policy=policy,
                        code=str(plan_data["code"]).strip().upper(),
                        name=str(plan_data["name"]).strip(),
                        description=str(plan_data.get("description") or "").strip(),
                        annual_premium=plan_data.get("annual_premium") or 0,
                        default_sum_insured=plan_data.get("default_sum_insured"),
                        premium_configuration={"method": "PRORATA"},
                        is_active=bool(plan_data.get("is_active", True)),
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
                f"Policy setup created with {len(plan_rows)} benefit plan(s). Add the initial member census, then submit for validation.",
            )
            if _is_htmx(request):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = (
                    reverse("tpa:transaction_detail", args=[tx.reference]) + "?step=policy_setup"
                )
                return response
            return redirect("tpa:transaction_detail", reference=tx.reference)

    creation_steps = [
        {"label": _("Policy & Routing"), "fields": [form[name] for name in [
            "sponsor", "insurance_company", "tpa_organization", "policy_number", "policy_name"
        ]]},
        {"label": _("Period & Rules"), "fields": [form[name] for name in [
            "start_date", "expiry_date", "currency", "stp_enabled", "allowed_backdating_days"
        ]]},
        {"label": _("Benefit Plans & Create"), "fields": [],
         "template": "tpa/partials/initial_benefit_plan_formset.html"},
    ]
    initial_step = next(
        (
            index
            for index, step in enumerate(creation_steps, 1)
            if any(field.errors for field in step["fields"])
        ),
        1,
    )
    if request.method == "POST" and uses_formset and (
        plan_formset.non_form_errors() or any(plan_form.errors for plan_form in plan_formset.forms)
    ):
        initial_step = 3
    context = {
        "form": form,
        "plan_formset": plan_formset,
        "creation_steps": creation_steps,
        "creation_initial_step": initial_step,
        "creation_form_id": "policy-enrollment-wizard",
        "creation_url": reverse("tpa:policy_enrollment_create"),
        "creation_cancel_url": reverse("tpa:policy_enrollment_list"),
    }
    return render(
        request,
        "components/creation_wizard_form.html" if _is_htmx(request)
        else "tpa/policy_enrollment_form.html",
        context,
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
    _require_intake_edit(request.user, tx)
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
        return _transaction_response(
            request, tx, step="policy_setup", forms={"plan_form": form}
        )
    return _transaction_response(request, tx, step="policy_setup")


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
        tx.physical_card_required = (
            tx.policy.physical_card_required
            and tx.transaction_type == MemberTransaction.Type.MEMBER_ADD
        )
        access = tx.policy.access_entries.filter(
            user=request.user,
            active=True,
        ).select_related("organization").first()
        tx.requester_organization = access.organization if access else tx.policy.sponsor
        tx.save()
        if tx.transaction_type == MemberTransaction.Type.POLICY_CANCEL:
            populate_policy_cancellation(tx)
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

    if request.method == "POST" and request.headers.get("HX-Request", "").lower() == "true":
        return render(request, "tpa/partials/transaction_wizard_form.html", {"form": form})
    return render(request, "tpa/transaction_form.html", {"form": form})

@login_required
def transaction_detail(request, reference, *, selected_step=None, form_overrides=None):
    _require_tpa_access(request.user)
    tx = get_object_or_404(
        visible_transactions(request.user).prefetch_related(
            "member_actions", "events", "source_documents"
        ),
        reference=reference,
    )

    if request.method == "GET" and tx.status == tx.Status.PENDING_APPROVAL and tx.ticket_id:
        tx = sync_from_ticket_approval(tx, actor=request.user)

    wizard = get_transaction_wizard(
        tx, request.user,
        selected_step if selected_step is not None else request.GET.get("step"),
    )
    if wizard["step_redirected"] and not _is_htmx(request):
        return redirect(wizard["step_url"])
    form_overrides = form_overrides or {}
    actions = list(tx.member_actions.all().order_by("row_number", "pk"))
    for action in actions:
        action.final_card_number = action.card_number or (
            action.member.tpa_member_id if action.member_id else "—"
        )
        action.final_member_status = (
            action.member.get_status_display() if action.member_id
            else action.processing_status or "—"
        )
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
                current_action=action,
                initial={
                    **display_data,
                    "principal_reference": principal_reference,
                },
            )
        elif tx.transaction_type == tx.Type.MEMBER_UPDATE:
            action.edit_form = MemberDemographicUpdateForm(initial=display_data)
        elif tx.transaction_type in {
            tx.Type.MEMBER_TERMINATE,
            tx.Type.MEMBER_DELETE,
            tx.Type.MEMBER_SUSPEND,
            tx.Type.MEMBER_REACTIVATE,
        }:
            action.edit_form = MemberLookupRowForm(initial=display_data)
        else:
            action.edit_form = None
        action.processing_form = TPAProcessingRowForm(
            initial={
                "card_number": action.card_number,
                "effective_date": action.tpa_effective_date or tx.effective_date,
                "amount": (action.tpa_premium_amount if action.tpa_premium_amount is not None
                           else action.calculated_premium),
                "override_reason": action.tpa_override_reason,
                "comments": action.processing_message,
            },
        )
        if form_overrides.get("edited_action_id") == action.pk:
            action.edit_form = form_overrides["edit_form"]
        if action.edit_form:
            action.edit_form.auto_id = f"id_edit_{action.pk}_%s"
        if form_overrides.get("processing_action_id") == action.pk:
            action.processing_form = form_overrides["processing_form"]
        action.processing_form.auto_id = f"id_tpa_{action.pk}_%s"
        for field in action.processing_form.fields.values():
            field.widget.attrs["form"] = f"tpa-row-{action.pk}"

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

    source_documents = list(tx.source_documents.all().order_by("-created_at"))
    for document in source_documents:
        payload = document.extracted_payload or {}
        result_count = payload.get("bundle_members_created")
        if result_count is None:
            result_count = payload.get("rows_created")
        document.result_count = result_count
        document.payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

    visible_query_threads = list(
        visible_transaction_queries(request.user, tx).order_by("-created_at")
    )
    for query in visible_query_threads:
        query.visible_messages = [
            message
            for message in query.messages.all()
            if can_view_query_message(request.user, message)
        ]
        query.can_reply = (
            tx.status not in CLOSED_STATUSES
            and query.status == TransactionQuery.Status.OPEN
            and can_view_transaction_query(request.user, query)
            and (
                can_approve_tpa_transaction(request.user, tx)
                or can_process_tpa_transaction(request.user, tx)
                or request.user.pk == tx.requester_id
                or query.selected_participants.filter(pk=request.user.pk).exists()
            )
        )
        query.reply_form = (
            form_overrides["query_message_form"]
            if form_overrides.get("reply_query_id") == query.pk
            else QueryMessageForm(prefix=f"query-{query.pk}")
        )
        # Distinct input IDs are needed for rich-text editors in each thread.
        if not (can_approve_tpa_transaction(request.user, tx)
                or can_process_tpa_transaction(request.user, tx)):
            query.reply_form.fields["audience"].choices = [
                choice for choice in TransactionQuery.Audience.choices
                if choice[0] != TransactionQuery.Audience.INSURER_TPA_INTERNAL
            ]
    shared_internal_messages = list(
        visible_shared_internal_messages(request.user, tx)
    )

    selectable_members = []
    uses_existing_members = tx.transaction_type in {
        tx.Type.MEMBER_UPDATE,
        tx.Type.MEMBER_DELETE,
        tx.Type.MEMBER_TERMINATE,
        tx.Type.MEMBER_SUSPEND,
        tx.Type.MEMBER_REACTIVATE,
    }
    if uses_existing_members:
        selectable_members = list(selectable_enrollments(tx))

    try:
        card_dispatch = tx.card_dispatch
    except CardDispatch.DoesNotExist:
        card_dispatch = None

    target_tat_hours = None
    if tx.ticket_id and tx.ticket.sla_policy_id:
        target_tat_hours = round(tx.ticket.sla_policy.resolution_minutes / 60, 1)
    sla_breached = None
    if tx.ticket_id and tx.ticket.resolution_due_at:
        sla_breached = (tx.processed_at or timezone.now()) > tx.ticket.resolution_due_at

    context = {
        **wizard,
        "tx": tx,
        "actions": actions,
        "events": tx.events.select_related("actor").all(),
        "recent_events": tx.events.select_related("actor").order_by("-created_at", "-pk")[:5],
        "target_tat_hours": target_tat_hours,
        "elapsed_tat_hours": round(
            ((tx.processed_at or timezone.now()) - tx.created_at).total_seconds() / 3600, 1
        ),
        "sla_breached": sla_breached,
        "approver_name": (tx.approved_by.get_full_name() or tx.approved_by.username
                          if tx.approved_by_id else "—"),
        "member_form": member_form,
        "bulk_card_form": BulkCardSelectionForm(),
        "selectable_members": selectable_members,
        "card_dispatch": card_dispatch,
        "card_dispatch_form": CardDispatchForm(instance=card_dispatch),
        "upload_form": MemberUploadForm(),
        "can_edit_intake": can_edit_tpa_intake(request.user, tx)
        and tx.status in INTAKE_EDITABLE_STATUSES
        and tx.transaction_type != tx.Type.POLICY_CANCEL,
        "can_approve": can_approve_tpa_transaction(request.user, tx),
        "can_process": can_process_tpa_transaction(request.user, tx),
        "can_submit_intake": can_edit_tpa_intake(request.user, tx)
        and tx.status in INTAKE_EDITABLE_STATUSES,
        "can_validate": tx.status in INTAKE_EDITABLE_STATUSES
        and tx.status != tx.Status.DRAFT
        and (
            can_edit_tpa_intake(request.user, tx)
            or can_approve_tpa_transaction(request.user, tx)
            or can_process_tpa_transaction(request.user, tx)
        ),
        "can_view_ai_source": (
            request.user.is_superuser
            or request.user.has_perm("tpa.view_ai_source_data")
            or request.user.has_perm("tpa.configure_tpa")
        ),
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
        "source_upload_form": SourceBundleUploadForm() if is_add else None,
        "requires_source_intake": is_add,
        "uses_existing_members": uses_existing_members,
        "plan_form": (
            BenefitPlanSetupForm(policy=tx.policy)
            if tx.transaction_type == tx.Type.NEW_POLICY_ENROLLMENT
            else None
        ),
        "initial_setup": tx.transaction_type == tx.Type.NEW_POLICY_ENROLLMENT,
        "source_documents": source_documents,
        "open_query": next(
            (
                query
                for query in visible_query_threads
                if query.status == TransactionQuery.Status.OPEN
            ),
            None,
        ),
        "query_history": visible_query_threads,
        "shared_internal_messages": shared_internal_messages,
        "query_raise_form": QueryRaiseForm(
            transaction=tx,
            initial={"purpose": TransactionQuery.Purpose.APPROVAL
                     if wizard["active_step"]["key"] == "approval"
                     else TransactionQuery.Purpose.TPA},
        ),
        "query_message_form": QueryMessageForm(),
        "rejection_form": TransactionRejectionForm(),
        "can_start_tpa": (
            tx.status == tx.Status.SENT_TO_TPA
            and can_process_tpa_transaction(request.user, tx)
        ),
        "can_tpa_process": can_process_tpa_transaction(request.user, tx),
        "source_emails": tx.source_emails.all(),
        "approval_events": tx.events.filter(
            event_type__in=["approval_rejected", "approval_synced", "approved",
                            "validation_completed", "sent_to_tpa"]
        ).select_related("actor"),
    }
    purpose = (TransactionQuery.Purpose.APPROVAL
               if wizard["active_step"]["key"] == "approval"
               else TransactionQuery.Purpose.TPA)
    context["query_history"] = [q for q in visible_query_threads if q.purpose == purpose]
    context["shared_internal_messages"] = [
        message for message in shared_internal_messages if message.query.purpose == purpose
    ]
    context["can_raise_query"] = tx.status not in CLOSED_STATUSES and (
        (purpose == TransactionQuery.Purpose.APPROVAL
         and tx.status == tx.Status.PENDING_APPROVAL and context["can_approve"])
        or (purpose == TransactionQuery.Purpose.TPA
            and tx.status in {tx.Status.TPA_IN_PROGRESS, tx.Status.TPA_QUERY}
            and context["can_tpa_process"])
    )
    context.update(form_overrides)
    response = render(
        request,
        "tpa/transaction/_workspace.html" if _is_htmx(request)
        else "tpa/transaction_detail.html",
        context,
    )
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    if _is_htmx(request):
        response["HX-Retarget"] = "#transaction-workspace"
        response["HX-Reswap"] = "outerHTML"
        response["HX-Push-Url" if request.method == "GET" else "HX-Replace-Url"] = wizard["step_url"]
    return response


@login_required
def transaction_upload_sources(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Source upload is closed for this transaction.")
    if tx.transaction_type not in {tx.Type.NEW_POLICY_ENROLLMENT, tx.Type.MEMBER_ADD}:
        raise PermissionDenied("Document/OCR member intake is available only for member addition workflows.")

    form = SourceBundleUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _transaction_response(
            request, tx, step="intake", forms={"source_upload_form": form}
        )

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
    return _transaction_response(request, tx, step='intake')


@login_required
def transaction_source_document(request, reference, document_id):
    _require_tpa_access(request.user)
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    document = get_object_or_404(tx.source_documents, pk=document_id)
    if not document.file:
        raise PermissionDenied("This source does not have a downloadable file.")
    document.file.open("rb")
    return FileResponse(
        document.file,
        as_attachment=True,
        filename=document.original_name,
        content_type=document.content_type or "application/octet-stream",
    )


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
    _require_intake_edit(request.user, tx)
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
        return _transaction_response(
            request, tx, step="intake",
            forms={"member_form": form, "reopen_modal": "manual-member"},
        )

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
        provenance=[
            {
                "source": "manual",
                "actor_id": request.user.pk,
                "at": timezone.now().isoformat(),
            }
        ],
    )

    if tx.status == tx.Status.DRAFT:
        validate_action(action)
    else:
        run_validation(tx, actor=request.user)

    messages.success(request, f"Member row {row_number} added.")
    return _transaction_response(request, tx, step="intake")


@login_required
def transaction_select_members(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member selection is closed for this transaction.")
    if tx.transaction_type not in {
        tx.Type.MEMBER_UPDATE,
        tx.Type.MEMBER_DELETE,
        tx.Type.MEMBER_TERMINATE,
        tx.Type.MEMBER_SUSPEND,
        tx.Type.MEMBER_REACTIVATE,
    }:
        raise PermissionDenied("This transaction does not select existing members.")

    selected_ids = [
        int(value)
        for value in request.POST.getlist("enrollment_ids")
        if str(value).isdigit()
    ]
    selected = list(selectable_enrollments(tx).filter(pk__in=selected_ids))
    if selected:
        add_enrollments_to_transaction(
            tx,
            selected,
            source=f"policy_selection:user:{request.user.pk}",
        )

    card_numbers = request.POST.get("card_numbers", "")
    if card_numbers.strip():
        result = resolve_card_numbers(tx, card_numbers)
        if result["matched"]:
            add_enrollments_to_transaction(
                tx,
                result["matched"],
                source=f"bulk_card_selection:user:{request.user.pk}",
            )
        if result["not_found"]:
            messages.warning(
                request,
                "Card numbers not found: " + ", ".join(result["not_found"]),
            )
        if result["inactive"]:
            messages.warning(
                request,
                "Inactive/ineligible card numbers: " + ", ".join(result["inactive"]),
            )
        if result["duplicates"]:
            messages.info(
                request,
                "Duplicate pasted card numbers ignored: " + ", ".join(result["duplicates"]),
            )

    saved_ids = set(
        int(value)
        for value in (tx.metadata or {}).get("selected_enrollment_ids", [])
        if str(value).isdigit()
    )
    saved_ids.update(item.pk for item in selected)
    if card_numbers.strip():
        saved_ids.update(item.pk for item in result["matched"])
    tx.metadata = {**(tx.metadata or {}), "selected_enrollment_ids": sorted(saved_ids)}
    tx.save(update_fields=["metadata", "updated_at"])

    for action in tx.member_actions.all():
        validate_action(action)
    messages.success(
        request,
        f"{tx.member_actions.count()} member row(s) are now in the endorsement.",
    )
    return _transaction_response(request, tx, step='intake')


@login_required
def transaction_reprocess_source(request, reference, document_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Evidence reprocessing is closed for this transaction.")
    document = get_object_or_404(tx.source_documents, pk=document_id)
    document.processing_state = SourceDocument.State.RECEIVED
    document.processing_error = ""
    document.processed = False
    document.save(
        update_fields=[
            "processing_state",
            "processing_error",
            "processed",
            "updated_at",
        ]
    )
    actions = process_source_bundle(tx, [document], actor=request.user)
    for action in actions:
        validate_action(action)
    TransactionEvent.objects.create(
        transaction=tx,
        actor=request.user,
        event_type="evidence_reprocessed",
        summary=f"Evidence reprocessed: {document.original_name}",
        details={"source_document_id": document.pk},
    )
    messages.success(
        request,
        f"Evidence reprocessed; {len(actions)} row(s) created or updated.",
    )
    return _transaction_response(request, tx, step='intake')


@login_required
def transaction_delete_source(request, reference, document_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Evidence deletion is closed for this transaction.")

    document = get_object_or_404(tx.source_documents, pk=document_id)
    if document.processing_state not in {
        SourceDocument.State.REVIEW,
        SourceDocument.State.FAILED,
    }:
        raise PermissionDenied("Only failed or review-required evidence can be deleted.")
    if document.ticket_attachment_id:
        raise PermissionDenied(
            "Email-linked evidence is preserved for audit. Reprocess or add supporting evidence instead."
        )

    original_name = document.original_name
    details = {
        "source_document_id": document.pk,
        "source_hash": document.source_hash,
        "processing_state": document.processing_state,
        "processing_error": document.processing_error,
    }
    stored_file = document.file
    document.delete()
    if stored_file:
        stored_file.delete(save=False)

    TransactionEvent.objects.create(
        transaction=tx,
        actor=request.user,
        event_type="failed_evidence_deleted",
        summary=f"Failed evidence deleted: {original_name}",
        details=details,
    )
    messages.success(request, f"Failed evidence removed: {original_name}.")
    return _transaction_response(request, tx, step='intake')


@login_required
def transaction_upload_members(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member intake is closed for this transaction.")

    form = MemberUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _transaction_response(
            request, tx, step="intake", forms={"upload_form": form}
        )

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

    return _transaction_response(request, tx, step='intake')


@login_required
def transaction_edit_member(request, reference, action_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member correction is closed for this transaction.")

    action = get_object_or_404(tx.member_actions, pk=action_id)
    is_add = tx.transaction_type in {
        tx.Type.NEW_POLICY_ENROLLMENT,
        tx.Type.MEMBER_ADD,
    }
    if is_add:
        form = MemberRowForm(request.POST, transaction=tx, current_action=action)
    elif tx.transaction_type == tx.Type.MEMBER_UPDATE:
        form = MemberDemographicUpdateForm(request.POST)
    else:
        form = MemberLookupRowForm(request.POST)
    if not form.is_valid():
        return _transaction_response(
            request, tx, step="intake",
            forms={"edit_form": form, "edited_action_id": action.pk,
                   "reopen_modal": f"edit-member-{action.pk}"},
        )

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
    return _transaction_response(request, tx, step='intake')


@login_required
def transaction_remove_member(request, reference, action_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Member intake is closed for this transaction.")

    action = get_object_or_404(tx.member_actions, pk=action_id)
    action.delete()
    if tx.status != tx.Status.DRAFT:
        run_validation(tx, actor=request.user)
    messages.success(request, "Member row removed.")
    return _transaction_response(request, tx, step='intake')


@login_required
def transaction_submit(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied

    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    _require_intake_edit(request.user, tx)
    if tx.status != tx.Status.DRAFT:
        return _transaction_response(request, tx, step='validation')

    if tx.transaction_type == tx.Type.POLICY_CANCEL and not tx.member_actions.exists():
        populate_policy_cancellation(tx)

    existing_member_types = {
        tx.Type.MEMBER_UPDATE,
        tx.Type.MEMBER_DELETE,
        tx.Type.MEMBER_TERMINATE,
        tx.Type.MEMBER_SUSPEND,
        tx.Type.MEMBER_REACTIVATE,
    }
    if tx.transaction_type in existing_member_types and not tx.member_actions.exists():
        saved_ids = [
            int(value)
            for value in (tx.metadata or {}).get("selected_enrollment_ids", [])
            if str(value).isdigit()
        ]
        if saved_ids:
            add_enrollments_to_transaction(
                tx,
                selectable_enrollments(tx).filter(pk__in=saved_ids),
                source=f"saved_policy_selection:user:{request.user.pk}",
            )

    if tx.transaction_type != tx.Type.POLICY_CANCEL and not tx.member_actions.exists():
        messages.error(
            request,
            "Select at least one existing member before continuing."
            if tx.transaction_type in existing_member_types
            else "At least one member is required before continuing.",
        )
        return _transaction_response(request, tx, step='intake')

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
    return _transaction_response(request, tx, step='validation')


@login_required
def transaction_validate(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if not (
        can_edit_tpa_intake(request.user, tx)
        or can_approve_tpa_transaction(request.user, tx)
        or can_process_tpa_transaction(request.user, tx)
    ):
        raise PermissionDenied(
            "Validation requires intake, approval or TPA processing authority."
        )
    if tx.status == tx.Status.DRAFT:
        messages.error(request, "Submit the transaction before running workflow validation.")
        return _transaction_response(request, tx, step='validation')
    if tx.status in {
        tx.Status.PROCESSED,
        tx.Status.COMPLETED,
        tx.Status.REJECTED,
        tx.Status.CANCELLED,
        tx.Status.FAILED,
    }:
        raise PermissionDenied("This transaction is closed.")
    if tx.status not in INTAKE_EDITABLE_STATUSES:
        raise PermissionDenied("Workflow validation is only available during intake and validation.")

    run_validation(tx, actor=request.user)
    messages.success(request, "Validation rerun completed.")
    return _transaction_response(request, tx, step='validation')


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
    return _transaction_response(request, tx, step='')


@login_required
def transaction_reject(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    form = TransactionRejectionForm(request.POST)
    if not form.is_valid():
        return _transaction_response(
            request, tx, step="approval",
            forms={"rejection_form": form, "reopen_modal": "reject-transaction"},
        )
    try:
        reject_transaction(tx, request.user, form.cleaned_data["reason"])
        messages.success(request, "TPA transaction rejected.")
    except (PermissionError, ValueError) as exc:
        form.add_error(None, str(exc))
        return _transaction_response(
            request, tx, step="approval",
            forms={"rejection_form": form, "reopen_modal": "reject-transaction"},
        )
    return _transaction_response(request, tx, step='approval')


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
    return _transaction_response(request, tx, step='tpa_processing')


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
                override_reason=form.cleaned_data.get("override_reason") or "",
                comments=form.cleaned_data.get("comments") or "",
            )
            messages.success(request, "TPA member processing data updated.")
        except (PermissionError, ValueError) as exc:
            form.add_error(None, str(exc))
    if form.errors:
        return _transaction_response(
            request, tx, step="tpa_processing",
            forms={"processing_form": form, "processing_action_id": action.pk},
        )
    return _transaction_response(request, tx, step='tpa_processing')


@login_required
def transaction_raise_query(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    form = QueryRaiseForm(request.POST, request.FILES, transaction=tx)
    if form.is_valid():
        try:
            query = raise_transaction_query(
                tx,
                request.user,
                form.cleaned_data["subject"],
                form.cleaned_data["message"],
                purpose=form.cleaned_data["purpose"],
                audience=form.cleaned_data["audience"],
                selected_participant_ids=[
                    user.pk
                    for user in form.cleaned_data.get("selected_participants") or []
                ],
            )
            initial_message = query.messages.select_related("ticket_comment").order_by(
                "created_at", "pk"
            ).first()
            if initial_message:
                for uploaded in form.cleaned_data.get("attachments") or []:
                    TicketAttachment.objects.create(
                        ticket=query.ticket,
                        comment=initial_message.ticket_comment,
                        uploaded_by=request.user,
                        file=uploaded,
                        original_name=uploaded.name,
                        content_type=getattr(uploaded, "content_type", "")
                        or "application/octet-stream",
                        size=uploaded.size,
                        is_restricted=True,
                        scan_status="pending",
                        source_field="tpa_query_chat",
                    )
            messages.warning(
                request,
                "Discussion opened inside this transaction.",
            )
        except (PermissionError, ValueError) as exc:
            form.add_error(None, str(exc))
    if form.errors:
        return _transaction_response(
            request, tx, forms={"query_raise_form": form, "query_form_open": True}
        )
    return _transaction_response(request, tx)


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
    prefix = f"query-{query.pk}" if f"query-{query.pk}-message" in request.POST else None
    form = QueryMessageForm(request.POST, request.FILES, prefix=prefix)
    if form.is_valid():
        try:
            query_message = post_query_message(
                query,
                request.user,
                form.cleaned_data["message"],
                audience=form.cleaned_data.get("audience") or None,
            )
            for uploaded in form.cleaned_data.get("attachments") or []:
                TicketAttachment.objects.create(
                    ticket=query.ticket,
                    comment=query_message.ticket_comment,
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
            form.add_error(None, str(exc))
    if form.errors:
        return _transaction_response(
            request, tx, forms={"query_message_form": form, "reply_query_id": query.pk}
        )
    return _transaction_response(request, tx)


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
    return _transaction_response(request, tx)


@login_required
def transaction_share_query_message(request, reference, message_id):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    query_message = get_object_or_404(
        TransactionQueryMessage.objects.select_related(
            "query",
            "query__transaction",
            "ticket_comment",
        ),
        pk=message_id,
        query__transaction=tx,
    )
    try:
        share_query_message_with_client(query_message, request.user)
        messages.success(request, "Selected internal message shared with the client.")
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return _transaction_response(request, tx)


@login_required
def transaction_query_attachment(request, reference, attachment_id):
    _require_tpa_access(request.user)
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    attachment = get_object_or_404(
        TicketAttachment.objects.select_related(
            "comment",
            "comment__tpa_query_message",
            "comment__tpa_query_message__query",
        ),
        pk=attachment_id,
        comment__tpa_query_message__query__transaction=tx,
    )
    query_message = attachment.comment.tpa_query_message
    if not can_view_query_attachment(request.user, query_message):
        raise PermissionDenied("You do not have access to this conversation attachment.")
    attachment.file.open("rb")
    return FileResponse(
        attachment.file,
        as_attachment=True,
        filename=attachment.original_name,
        content_type=attachment.content_type or "application/octet-stream",
    )


@login_required
def transaction_card_dispatch(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if not can_process_tpa_transaction(request.user, tx):
        raise PermissionDenied("Card dispatch updates require TPA processing authority.")
    if tx.status != tx.Status.CARD_DISPATCH:
        raise PermissionDenied("Card dispatch is not active for this transaction.")
    try:
        dispatch = tx.card_dispatch
    except CardDispatch.DoesNotExist:
        dispatch = CardDispatch(transaction=tx)

    form = CardDispatchForm(request.POST, instance=dispatch)
    if not form.is_valid():
        return _transaction_response(
            request, tx, step="card_dispatch", forms={"card_dispatch_form": form}
        )

    proof_attachment = None
    proof = request.FILES.get("proof")
    if proof:
        if not tx.ticket_id:
            create_ticket_for_transaction(tx, actor=request.user)
            tx.refresh_from_db(fields=["ticket"])
        proof_attachment = TicketAttachment.objects.create(
            ticket=tx.ticket,
            uploaded_by=request.user,
            file=proof,
            original_name=proof.name,
            content_type=getattr(proof, "content_type", "") or "application/octet-stream",
            size=proof.size,
            is_restricted=True,
            scan_status="clean",
            source_field="tpa_card_dispatch",
        )

    try:
        update_card_dispatch(
            tx,
            request.user,
            proof_attachment=proof_attachment,
            **form.cleaned_data,
        )
        tx.refresh_from_db()
        messages.success(
            request,
            "Card dispatch updated."
            if tx.status == tx.Status.CARD_DISPATCH
            else "Card delivery/collection completed and endorsement finalized.",
        )
    except (PermissionError, ValueError) as exc:
        form.add_error(None, str(exc))
        return _transaction_response(
            request, tx, step="card_dispatch", forms={"card_dispatch_form": form}
        )
    return _transaction_response(request, tx, step='')


@login_required
def transaction_card_dispatch_proof(request, reference):
    _require_tpa_access(request.user)
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    if not can_process_tpa_transaction(request.user, tx):
        raise PermissionDenied("Card dispatch proof requires TPA processing authority.")
    try:
        dispatch = tx.card_dispatch
    except CardDispatch.DoesNotExist:
        raise PermissionDenied("No card dispatch record exists for this transaction.")
    attachment = dispatch.proof_attachment
    if not attachment or not attachment.file:
        raise PermissionDenied("No card dispatch proof is available.")
    attachment.file.open("rb")
    return FileResponse(
        attachment.file,
        as_attachment=True,
        filename=attachment.original_name,
        content_type=attachment.content_type or "application/octet-stream",
    )


@login_required
def transaction_tpa_complete(request, reference):
    _require_tpa_access(request.user)
    if request.method != "POST":
        raise PermissionDenied
    tx = get_object_or_404(visible_transactions(request.user), reference=reference)
    try:
        complete_tpa_transaction(tx, request.user)
        tx.refresh_from_db()
        if tx.status == tx.Status.CARD_DISPATCH:
            messages.success(
                request,
                "TPA processing completed. Physical card dispatch/collection is now required.",
            )
        else:
            messages.success(
                request,
                "TPA processing completed. Member/policy records have been updated.",
            )
    except (PermissionError, ValueError) as exc:
        messages.error(request, str(exc))
    return _transaction_response(request, tx, step='')


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
    return _transaction_response(request, tx, step='')
