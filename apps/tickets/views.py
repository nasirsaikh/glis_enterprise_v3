import csv
import json
import re,html
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import bleach
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, F, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from apps.ai.models import AIInteraction, AISettings
from apps.ai.providers import get_provider
from apps.core.models import AuditLog
from services.access import TicketAccessPolicy
from services.dynamic_forms import DynamicTicketForm
from services.ticket_workflow import current_approval_sequence, decide_approval, initialize_approval_workflow, notify_users
from .forms import (
    TicketApprovalDecisionForm, TicketAssignmentForm, TicketCommentForm,
    TicketCreateStep1Form, TicketEditForm, TicketFilterForm, TicketIntakeForm,
    TicketReviewForm, TicketShareForm,
)
from .models import (
    Category, DynamicForm, Notification, Product, Project, SLAPolicy, SupportGroup,
    Ticket, TicketApproval, TicketAttachment, TicketComment, TicketDynamicData,
    TicketEvent, TicketShare,
)


RICH_TEXT_TAGS = ["p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "blockquote", "a", "img", "h2", "h3", "code"]
RICH_TEXT_ATTRIBUTES = {"a": ["href", "title", "target", "rel"], "img": ["src", "alt", "title"]}


def sanitize_rich_text(value):
    cleaned = bleach.clean(value or "", tags=RICH_TEXT_TAGS, attributes=RICH_TEXT_ATTRIBUTES, protocols=["http", "https", "mailto", "data"], strip=True)
    return re.sub(r'src=("|\')data:(?!image/(?:png|jpeg|gif|webp);base64,).*?\1', 'src=""', cleaned, flags=re.I)


def _apply_ticket_filters(qs, data):
    if data.get("q"):
        term = data["q"]
        qs = qs.filter(Q(reference__icontains=term) | Q(subject__icontains=term) | Q(description__icontains=term) | Q(requester__email__icontains=term))
    for key in ("status", "priority", "project", "category"):
        if data.get(key):
            qs = qs.filter(**{key: data[key]})
    if data.get("sla") == "overdue":
        qs = qs.filter(resolution_due_at__lt=timezone.now()).exclude(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED])
    elif data.get("sla") == "at_risk":
        qs = qs.filter(resolution_due_at__range=(timezone.now(), timezone.now() + timedelta(hours=2)))
    return qs


def _jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(x) for x in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _validate_wizard_attachments(request, specs, form):
    for spec in specs:
        uploads = request.FILES.getlist(spec.get("name", ""))
        minimum = int(spec.get("min_count", 1 if spec.get("required") else 0))
        maximum = int(spec.get("max_count", 10))
        if len(uploads) < minimum:
            form.add_error(None, spec.get("required_message") or f"Please attach {spec.get('label', spec.get('name'))}.")
        if len(uploads) > maximum:
            form.add_error(None, spec.get("max_count_message") or f"No more than {maximum} files are allowed for {spec.get('label')}.")
        allowed = {ext.lower() for ext in spec.get("allowed_extensions", [])}
        for upload in uploads:
            if allowed and Path(upload.name).suffix.lower() not in allowed:
                form.add_error(None, spec.get("invalid_type_message") or f"{upload.name} has an unsupported file type.")
            if upload.size > int(spec.get("max_size_mb", 10)) * 1024 * 1024:
                form.add_error(None, f"{upload.name} exceeds the allowed file size.")


@login_required
def dashboard(request):
    qs = TicketAccessPolicy.visible_queryset(request.user)
    now = timezone.now()
    resolved_month = qs.filter(resolved_at__year=now.year, resolved_at__month=now.month).count()
    open_qs = qs.exclude(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED])
    first_tat = qs.filter(first_responded_at__isnull=False).aggregate(value=Avg(F("first_responded_at") - F("created_at")))["value"]
    resolution_tat = qs.filter(resolved_at__isnull=False).aggregate(value=Avg(F("resolved_at") - F("created_at")))["value"]
    resolved_with_sla = qs.filter(resolved_at__isnull=False, resolution_due_at__isnull=False)
    resolved_with_sla_count = resolved_with_sla.count()
    sla_met = resolved_with_sla.filter(resolved_at__lte=F("resolution_due_at")).count()
    metrics = {
        "open": open_qs.count(),
        "assigned": open_qs.filter(Q(assignee=request.user) | Q(assignees=request.user)).distinct().count(),
        "overdue": qs.filter(resolution_due_at__lt=now).exclude(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED]).count(),
        "resolved_month": resolved_month,
        "first_response_tat": round(first_tat.total_seconds() / 3600, 1) if first_tat else 0,
        "resolution_tat": round(resolution_tat.total_seconds() / 3600, 1) if resolution_tat else 0,
        "sla_attainment": round((sla_met / resolved_with_sla_count) * 100, 1) if resolved_with_sla_count else 100,
    }
    by_status = list(qs.values("status").annotate(total=Count("id")).order_by("status"))
    by_priority = list(qs.values("priority").annotate(total=Count("id")).order_by("priority"))
    by_category = list(qs.values(label=F("category__name_en")).annotate(total=Count("id")).order_by("-total")[:10])
    by_product = list(qs.values(label=F("product__name_en")).annotate(total=Count("id")).order_by("-total")[:10])
    by_project = list(qs.values(label=F("project__name_en")).annotate(total=Count("id")).order_by("-total")[:10])
    by_assignee = list(qs.values(label=F("assignees__first_name")).annotate(total=Count("id", distinct=True)).order_by("-total")[:10])
    for row in by_assignee:
        row["label"] = row["label"] or "Unassigned"
    daily_open = list(qs.filter(created_at__gte=now - timedelta(days=13)).annotate(day=TruncDate("created_at")).values("day").annotate(total=Count("id")).order_by("day"))
    chart_data = {"status": by_status, "priority": by_priority, "category": by_category, "product": by_product, "project": by_project, "assignee": by_assignee, "daily_open": daily_open}
    return render(request, "portal/dashboard.html", {"metrics": metrics, "chart_data": chart_data, "recent_tickets": qs[:7], "attention": qs.filter(Q(priority="critical") | Q(resolution_due_at__lt=now + timedelta(hours=2)))[:6]})


@login_required
def ticket_list(request):
    qs = TicketAccessPolicy.visible_queryset(request.user)
    if request.GET.get("owner") == "me":
        qs = qs.filter(requester=request.user)
    if request.GET.get("scope") == "group":
        qs = qs.filter(groups__members=request.user).distinct()
    form = TicketFilterForm(request.GET)
    if form.is_valid():
        data = form.cleaned_data        
        if not data.get("status"):
            qs = qs.exclude(status="closed")
        qs = _apply_ticket_filters(qs, data)        
    allowed_sorts = {"created_at", "-created_at", "priority", "-priority", "status", "resolution_due_at", "-resolution_due_at"}
    qs = qs.order_by(request.GET.get("sort") if request.GET.get("sort") in allowed_sorts else "-created_at")
    page = Paginator(qs, min(int(request.GET.get("page_size", 20)), 100)).get_page(request.GET.get("page"))
    template = "tickets/partials/table.html" if request.htmx else "tickets/list.html"
    return render(request, template, {"filter_form": form, "page_obj": page})


@login_required
def ticket_detail(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    comments = (ticket.comments.select_related("author").prefetch_related("attachments"))    
    if not TicketAccessPolicy.can_view_internal_notes(request.user, ticket):
        comments = comments.filter(is_internal=False)
    dynamic_values = getattr(ticket, "dynamic_data", None)
    if dynamic_values and not TicketAccessPolicy.can_view_sensitive(request.user, ticket):
        dynamic_values = dict(dynamic_values.values)
        for key in ticket.dynamic_data.sensitive_keys:
            if key in dynamic_values:
                dynamic_values[key] = "••••••"
    current_sequence = current_approval_sequence(ticket)
    actionable_approvals = ticket.approvals.filter(approver=request.user, status="pending", step__sequence=current_sequence).select_related("step") if current_sequence is not None else []
    return render(request, "tickets/detail.html", {
        "ticket": ticket, "comments": comments, "comment_form": TicketCommentForm(),
        "dynamic_values": dynamic_values, "can_edit": TicketAccessPolicy.can_edit(request.user, ticket),
        "can_view_sensitive": TicketAccessPolicy.can_view_sensitive(request.user, ticket),
        "can_take_over": TicketAccessPolicy.can_take_over(request.user, ticket),
        "can_assign": TicketAccessPolicy.can_assign(request.user, ticket),
        "can_share": TicketAccessPolicy.can_share(request.user, ticket),
        "assignment_form": TicketAssignmentForm(ticket=ticket),
        "share_form": TicketShareForm(user=request.user),
        "actionable_approvals": actionable_approvals,
        "approval_form": TicketApprovalDecisionForm(),
        "attachment_specs": _attachment_specs_for(ticket),
    })


# @login_required
# @require_POST
# @transaction.atomic
# def add_comment(request, reference):
#     ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
#     form = TicketCommentForm(request.POST)
#     if form.is_valid():
#         if form.cleaned_data.get("is_internal") and not TicketAccessPolicy.can_view_internal_notes(request.user, ticket):
#             return HttpResponse("Internal notes are restricted.", status=403)
#         comment = form.save(commit=False)
#         comment.ticket, comment.author = ticket, request.user
#         comment.body = sanitize_rich_text(comment.body)
#         comment.save()
#         if request.user.pk != ticket.requester_id and not ticket.first_responded_at:
#             ticket.first_responded_at = timezone.now()
#             ticket.save(update_fields=["first_responded_at", "updated_at"])
#         TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="comment", summary="Internal note added" if comment.is_internal else "Comment added")
#         if not comment.is_internal:
#             recipients = [ticket.requester] if request.user.pk != ticket.requester_id else list(ticket.assignees.all())
#             notify_users(recipients, ticket=ticket, kind="update", title=f"New update on {ticket.reference}", body=bleach.clean(comment.body, tags=[], strip=True), send_email_message=ticket.category.send_update_email)
#         AuditLog.record(request=request, action="ticket.comment", instance=ticket, summary="Added an internal note" if comment.is_internal else "Added a public comment")
#         return render(request, "tickets/partials/comment.html", {"comment": comment})
#     return render(request, "tickets/partials/comment_form.html", {"ticket": ticket, "comment_form": form}, status=422)

import html
import re
from pathlib import Path

import bleach

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import AuditLog

from services.access import TicketAccessPolicy
from services.ticket_workflow import notify_users

from .forms import TicketCommentForm
from .models import (
    Ticket,
    TicketAttachment,
    TicketEvent,
)


def _rich_text_is_blank(value):
    plain_text = bleach.clean(
        value or "",
        tags=[],
        strip=True,
    )

    plain_text = html.unescape(plain_text)
    plain_text = plain_text.replace("\xa0", " ")
    plain_text = re.sub(r"\s+", " ", plain_text).strip()

    return not bool(plain_text)

def _get_comment_allowed_extensions(category):
    return {
        f".{extension.strip().lower().lstrip('.')}"
        for extension in (category.comment_attachment_extensions or "").split(",")
        if extension.strip()
    }


def _validate_comment_attachments(ticket, uploads):
    category = ticket.category
    uploads = list(uploads)

    errors = []

    # Upload completely disabled for this category.
    if not category.comment_attachment_required:
        if uploads:
            errors.append("File upload is disabled for this category.")
        return errors

    # Attachment enabled AND required.
    if not uploads:
        errors.append("Please attach at least one document.")
        return errors

    max_count = category.comment_attachment_max_count or 0
    max_size_mb = category.comment_attachment_max_size_mb or 0
    max_size_bytes = max_size_mb * 1024 * 1024

    allowed_extensions = _get_comment_allowed_extensions(category)

    if max_count and len(uploads) > max_count:
        errors.append(
            f"Maximum {max_count} file"
            f"{'s' if max_count != 1 else ''} are allowed per comment."
        )

    for upload in uploads:
        filename = upload.name or "Unnamed file"
        extension = Path(filename).suffix.lower()

        if upload.size <= 0:
            errors.append(f"{filename}: the uploaded file is empty.")
            continue

        if allowed_extensions and extension not in allowed_extensions:
            errors.append(
                f"{filename}: {extension or 'unknown'} file type is not allowed."
            )

        if max_size_bytes and upload.size > max_size_bytes:
            errors.append(
                f"{filename}: maximum allowed file size is {max_size_mb} MB."
            )

    return errors


@login_required
@require_POST
@transaction.atomic
def add_comment(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user),reference=reference,)
    form = TicketCommentForm(request.POST)
    uploads = list(request.FILES.getlist("attachments"))
    def htmx_error_response():
        response = render(
            request,
            "tickets/partials/comment_errors.html",
            {
                "ticket": ticket,
                "comment_form": form,
            },
        )

        response["HX-Retarget"] = "#comment-form-errors"
        response["HX-Reswap"] = "innerHTML"

        return response

    # ---------------------------------------------------------
    # Standard Django form validation
    # ---------------------------------------------------------
    if not form.is_valid():
        if request.headers.get("HX-Request"):
            return htmx_error_response()
        return redirect("portal:ticket_detail",reference=ticket.reference,)

    body = form.cleaned_data.get("body", "")
    if _rich_text_is_blank(body):
        form.add_error("body","Please enter a message before posting.",)
        if request.headers.get("HX-Request"):
            return htmx_error_response()
        messages.error(request,"Please enter a message before posting.",)
        return redirect("portal:ticket_detail",reference=ticket.reference,)
    is_internal = bool(form.cleaned_data.get("is_internal"))
    selected_status = form.cleaned_data.get("status")

    if (is_internal and not TicketAccessPolicy.can_view_internal_notes(request.user,ticket,)):
        return HttpResponse("Internal notes are restricted.",status=403,)

    attachment_errors = _validate_comment_attachments(ticket,uploads,)
    if attachment_errors:
        for error in attachment_errors:
            form.add_error(None, error)
        if request.headers.get("HX-Request"):
            return htmx_error_response()
        for error in attachment_errors:
            messages.error(request, error)
        return redirect("portal:ticket_detail",reference=ticket.reference,)
    comment = form.save(commit=False)
    comment.ticket = ticket
    comment.author = request.user
    comment.body = sanitize_rich_text(comment.body)
    if selected_status:
        comment.status = selected_status
    comment.save()

    status_changed = False
    if selected_status and selected_status != ticket.status:
        status_changed = True
        ticket.status = selected_status
        if selected_status == Ticket.Status.RESOLVED:
            ticket.resolved_at = timezone.now()
            ticket.closed_at = None
        elif selected_status == Ticket.Status.CLOSED:
            ticket.closed_at = timezone.now()
            if not ticket.resolved_at:
                ticket.resolved_at = timezone.now()

        else:
            ticket.resolved_at = None
            ticket.closed_at = None
        ticket.save()
    # ---------------------------------------------------------
    # Comment-specific attachments
    # ---------------------------------------------------------
    for upload in uploads:
        attachment = TicketAttachment(
            ticket=ticket,
            comment=comment,
            uploaded_by=request.user,
            file=upload,
            original_name=upload.name,
            content_type=getattr(upload,"content_type","application/octet-stream",),
            size=upload.size,
            is_restricted=comment.is_internal,
            source_field="comment",
        )
        attachment.full_clean()
        attachment.save()

    if (request.user.pk != ticket.requester_id and not ticket.first_responded_at):
        ticket.first_responded_at = timezone.now()
        ticket.save(update_fields=["first_responded_at","updated_at",])

    summary = ("Internal note added" if comment.is_internal else "Comment added")

    if uploads: summary += (f" with {len(uploads)} attachment {'s' if len(uploads) != 1 else ''}")
    TicketEvent.objects.create(
        ticket=ticket,
        actor=request.user,
        event_type="comment",
        summary=summary,
        details={
            "comment_id": comment.pk,
            "attachment_count": len(uploads),
            "is_internal": comment.is_internal,
        },
    )

    # ---------------------------------------------------------
    # Notifications
    # ---------------------------------------------------------
    if not comment.is_internal:
        if request.user.pk != ticket.requester_id:
            recipients = [ticket.requester]
        else:
            recipients = list(ticket.assignees.all())

        recipients = [
            user
            for user in recipients
            if user.pk != request.user.pk
        ]

        if recipients:
            notify_users(
                recipients,
                ticket=ticket,
                kind="update",
                title=f"New update on {ticket.reference}",
                body=bleach.clean(
                    comment.body,
                    tags=[],
                    strip=True,
                ),
                send_email_message=(
                    ticket.category.send_update_email
                ),
            )

    # ---------------------------------------------------------
    # Audit
    # ---------------------------------------------------------
    AuditLog.record(request=request,action="ticket.comment",instance=ticket,summary=summary,)

    if request.headers.get("HX-Request"):
        comment = (
            TicketComment.objects
            .select_related("author")
            .prefetch_related("attachments")
            .get(pk=comment.pk)
        )
        response = render(
            request,
            "tickets/partials/comment.html",
            {
                "ticket": ticket,
                "comment": comment,
            },
        )

        response["HX-Retarget"] = "#comment-list"
        response["HX-Reswap"] = "beforeend"
        response["HX-Trigger"] = "ticketCommentPosted"
        if status_changed:
            response["HX-Refresh"] = "true"        
        return response

    return redirect(
        "portal:ticket_detail",
        reference=ticket.reference,
    )

@login_required
def create_ticket(request, step=1):
    if step not in {1, 2, 3, 4}:
        raise Http404
    wizard = request.session.setdefault("ticket_wizard", {})
    if step > 1 and not wizard.get("selection"):
        return redirect("portal:create_ticket", step=1)
    if step == 1:
        initial = wizard.get("selection", {})
        form = TicketCreateStep1Form(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            wizard["selection"] = {key: form.cleaned_data[key].pk for key in ("project", "product", "category")}
            request.session.modified = True
            return redirect("portal:create_ticket", step=2)
        return render(request, "tickets/wizard/step1.html", {"form": form, "step": 1})

    category = get_object_or_404(Category, pk=wizard["selection"]["category"])
    dynamic_form = DynamicForm.objects.filter(category=category, is_active=True, active_version__isnull=False).select_related("active_version").first()
    schema = dynamic_form.active_version.schema if dynamic_form else {"fields": []}
    if step == 2:
        form = DynamicTicketForm(request.POST or None, schema=schema, user=request.user, initial=wizard.get("dynamic", {}))
        if request.method == "POST" and form.is_valid():
            wizard["dynamic"] = _jsonable(form.cleaned_data)
            request.session.modified = True
            return redirect("portal:create_ticket", step=3)
        return render(request, "tickets/wizard/step2.html", {"form": form, "step": 2, "category": category})

    ai_settings = AISettings.load()
    if step == 3:
        form = TicketIntakeForm(request.POST or None, questions=ai_settings.intake_questions, initial=wizard.get("answers", {}))
        if request.method == "POST" and form.is_valid():
            wizard["answers"] = form.cleaned_data
            payload = {"description": wizard.get("dynamic", {}).get("description", ""), "category": category.name_en, **form.cleaned_data}
            started = timezone.now()
            try:
                analysis = get_provider(ai_settings.provider).analyze_ticket(payload)
                succeeded, error = True, ""
            except Exception:
                analysis = {"summary": payload["description"], "suggested_priority": category.default_priority, "confidence": 0, "label": "AI unavailable — manual review required"}
                succeeded, error = False, "provider_unavailable"
            wizard["analysis"] = analysis
            AIInteraction.objects.create(user=request.user, purpose="ticket_intake", provider=ai_settings.provider, request_summary={"category": category.name_en}, response=analysis, confidence=analysis.get("confidence"), duration_ms=int((timezone.now() - started).total_seconds() * 1000), succeeded=succeeded, error_code=error)
            request.session.modified = True
            return redirect("portal:create_ticket", step=4)
        return render(request, "tickets/wizard/step3.html", {"form": form, "questions": ai_settings.intake_questions, "step": 3})

    analysis = wizard.get("analysis", {})
    initial = {"subject": f"{category.name_en} request", "description": wizard.get("dynamic", {}).get("description") or analysis.get("summary", ""), "priority": analysis.get("suggested_priority", category.default_priority)}
    form = TicketReviewForm(request.POST or None, initial=initial)
    attachment_specs = list(schema.get("attachments", {}).get("items", []))
    configured_names = {item.get("name") for item in attachment_specs}
    attachment_specs.extend(item for item in category.required_documents if item.get("name") not in configured_names)
    review_valid = False
    if request.method == "POST":
        review_valid = form.is_valid()
        _validate_wizard_attachments(request, attachment_specs, form)
        review_valid = review_valid and not form.errors
    if request.method == "POST" and review_valid:
        selection = wizard["selection"]
        sla = SLAPolicy.objects.filter(category_id=selection["category"], priority=form.cleaned_data["priority"], is_active=True).first()
        now = timezone.now()
        ticket = Ticket.objects.create(
            subject=form.cleaned_data["subject"], description=sanitize_rich_text(form.cleaned_data["description"]), requester=request.user,
            project_id=selection["project"], product_id=selection["product"], category_id=selection["category"],
            priority=form.cleaned_data["priority"], sla_policy=sla, ai_summary=analysis.get("summary", ""), ai_recommendations=analysis,
            first_response_due_at=now + timedelta(minutes=sla.first_response_minutes) if sla else None,
            resolution_due_at=now + timedelta(minutes=sla.resolution_minutes) if sla else None,
        )
        default_groups = list(category.default_groups.filter(is_active=True))
        if category.default_group and category.default_group not in default_groups:
            default_groups.append(category.default_group)
        ticket.groups.add(*default_groups)
        if category.default_user and category.default_user.is_active:
            ticket.assignee = category.default_user
            ticket.save(update_fields=["assignee", "updated_at"])
            ticket.assignees.add(category.default_user)
        sensitive = [spec["name"] for spec in schema.get("fields", []) if spec.get("sensitive")]
        TicketDynamicData.objects.create(ticket=ticket, form_version=dynamic_form.active_version if dynamic_form else None, values=wizard.get("dynamic", {}), sensitive_keys=sensitive)
        for spec in attachment_specs:
            for upload in request.FILES.getlist(spec.get("name", "")):
                attachment = TicketAttachment(ticket=ticket, uploaded_by=request.user, file=upload, original_name=upload.name, content_type=getattr(upload, "content_type", "application/octet-stream"), size=upload.size, is_restricted=bool(spec.get("restricted")), source_field=spec.get("name", ""))
                attachment.full_clean()
                attachment.save()
        TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="created", summary="Ticket submitted")
        initialize_approval_workflow(ticket)
        assignment_users = list(ticket.assignees.all())
        for group in ticket.groups.all():
            assignment_users.extend(group.members.all())
        notify_users(assignment_users, ticket=ticket, kind="assignment", title=f"New ticket assigned: {ticket.reference}", body=ticket.subject, send_email_message=category.send_initial_email)
        AuditLog.record(request=request, action="ticket.create", instance=ticket, summary=f"Created {ticket.reference}")
        request.session.pop("ticket_wizard", None)
        messages.success(request, f"{ticket.reference} was submitted successfully.")
        return redirect("portal:ticket_detail", reference=ticket.reference)
    return render(request, "tickets/wizard/step4.html", {"form": form, "step": 4, "wizard": wizard, "analysis": analysis, "category": category, "attachment_specs": attachment_specs})


@login_required
@require_GET
def product_options(request):
    products = Product.objects.filter(project_id=request.GET.get("project"), is_active=True)
    return render(request, "tickets/partials/options.html", {"objects": products, "placeholder": "Select a product"})


@login_required
@require_GET
def category_options(request):
    categories = Category.objects.filter(product_id=request.GET.get("product"), is_active=True)
    return render(request, "tickets/partials/options.html", {"objects": categories, "placeholder": "Select a category"})


@login_required
@require_GET
def global_search(request):
    term = request.GET.get("q", "").strip()
    tickets = TicketAccessPolicy.visible_queryset(request.user).filter(Q(reference__icontains=term) | Q(subject__icontains=term))[:8] if len(term) >= 2 else []
    return render(request, "tickets/partials/search_results.html", {"tickets": tickets, "term": term})


@login_required
def download_attachment(request, pk):
    attachment = get_object_or_404(TicketAttachment.objects.select_related("ticket"), pk=pk)
    if not TicketAccessPolicy.can_download_attachment(request.user, attachment):
        return HttpResponse("Attachment access denied.", status=403)
    if attachment.scan_status == "blocked":
        return HttpResponse("Attachment was blocked by security scanning.", status=423)
    return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_name)


@login_required
def export_tickets(request):
    qs = TicketAccessPolicy.visible_queryset(request.user)
    if request.GET.get("owner") == "me":
        qs = qs.filter(requester=request.user)
    if request.GET.get("scope") == "group":
        qs = qs.filter(groups__members=request.user).distinct()
    form = TicketFilterForm(request.GET)
    if form.is_valid():
        qs = _apply_ticket_filters(qs, form.cleaned_data)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="glis-tickets-{timezone.localdate():%Y%m%d}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Reference", "Subject", "Project", "Product", "Category", "Requester", "Assigned users", "Groups", "Priority", "Status", "Approval", "SLA state", "Created", "First response TAT hours", "Resolution TAT hours"])
    for ticket in qs.prefetch_related("assignees", "groups"):
        first_tat = (ticket.first_responded_at - ticket.created_at).total_seconds() / 3600 if ticket.first_responded_at else ""
        resolution_tat = (ticket.resolved_at - ticket.created_at).total_seconds() / 3600 if ticket.resolved_at else ""
        writer.writerow([
            ticket.reference, ticket.subject, ticket.project.name_en, ticket.product.name_en, ticket.category.name_en,
            ticket.requester.email, "; ".join(user.get_full_name() or user.email for user in ticket.assignees.all()),
            "; ".join(group.name for group in ticket.groups.all()), ticket.get_priority_display(), ticket.get_status_display(),
            ticket.get_approval_state_display(), ticket.sla_state, ticket.created_at.isoformat(),
            round(first_tat, 2) if first_tat != "" else "", round(resolution_tat, 2) if resolution_tat != "" else "",
        ])
    AuditLog.record(request=request, action="ticket.export", summary="Exported permitted ticket list")
    return response


@login_required
def edit_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_edit(request.user, ticket):
        return HttpResponse("Take over this ticket before editing it.", status=403)
    original_status = ticket.status
    form = TicketEditForm(request.POST or None, instance=ticket, user=request.user)
    dynamic = getattr(ticket, "dynamic_data", None)
    schema = dynamic.form_version.schema if dynamic and dynamic.form_version else {"fields": []}
    dynamic_form = DynamicTicketForm(request.POST or None, schema=schema, user=request.user, initial=dynamic.values if dynamic else {})
    if request.method == "POST" and form.is_valid() and dynamic_form.is_valid():
        updated = form.save(commit=False)
        if original_status == Ticket.Status.CLOSED and updated.status != Ticket.Status.CLOSED:
            allowed_until = ticket.closed_at + timedelta(days=ticket.category.reopen_allowed_days) if ticket.closed_at else timezone.now()
            if timezone.now() > allowed_until:
                form.add_error("status", "The administrator-defined reopen period has expired.")
            else:
                ticket.closed_at = None
                ticket.resolved_at = None
                TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="reopened", summary="Ticket reopened")
        if not form.errors:
            updated.description = sanitize_rich_text(updated.description)
            if updated.status == Ticket.Status.RESOLVED and not ticket.resolved_at:
                updated.resolved_at = timezone.now()
            if updated.status == Ticket.Status.CLOSED and not ticket.closed_at:
                updated.closed_at = timezone.now()
            updated.save()
            if dynamic:
                dynamic.values = _jsonable(dynamic_form.cleaned_data)
                dynamic.save(update_fields=["values", "updated_at"])
            TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="edited", summary="Ticket details updated", details={"status_from": original_status, "status_to": updated.status})
            AuditLog.record(request=request, action="ticket.edit", instance=ticket, summary=f"Updated {ticket.reference}")
            notify_users([ticket.requester], ticket=ticket, kind="update", title=f"Ticket updated: {ticket.reference}", body=ticket.subject, send_email_message=ticket.category.send_update_email)
            messages.success(request, "Ticket changes were saved.")
            return redirect("portal:ticket_detail", reference=ticket.reference)
    return render(request, "tickets/edit.html", {"ticket": ticket, "form": form, "dynamic_form": dynamic_form})


@login_required
@require_POST
@transaction.atomic
def assign_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_assign(request.user, ticket):
        return HttpResponse("Assignment permission is required.", status=403)
    form = TicketAssignmentForm(request.POST, ticket=ticket)
    if not form.is_valid():
        messages.error(request, "Select valid groups or staff members.")
        return redirect("portal:ticket_detail", reference=reference)
    users, groups = list(form.cleaned_data["users"]), list(form.cleaned_data["groups"])
    if form.cleaned_data["replace_existing"]:
        ticket.assignees.set(users); ticket.groups.set(groups)
    else:
        ticket.assignees.add(*users); ticket.groups.add(*groups)
    ticket.assignee = ticket.assignees.order_by("first_name", "email").first()
    ticket.save(update_fields=["assignee", "updated_at"])
    TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="assignment", summary="Ticket assignment updated", details={"users": [user.email for user in ticket.assignees.all()], "groups": [group.name for group in ticket.groups.all()]})
    notify_users(list(ticket.assignees.all()), ticket=ticket, kind="assignment", title=f"Ticket assigned: {ticket.reference}", body=ticket.subject, send_email_message=ticket.category.send_update_email)
    messages.success(request, "Ticket assignment was updated.")
    return redirect("portal:ticket_detail", reference=reference)


@login_required
@require_POST
def unassign_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_assign(request.user, ticket):
        return HttpResponse("Assignment permission is required.", status=403)
    target = request.POST.get("target", "all")
    if target in {"users", "all"}:
        ticket.assignees.clear(); ticket.assignee = None; ticket.save(update_fields=["assignee", "updated_at"])
    if target in {"groups", "all"}:
        ticket.groups.clear()
    TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="unassigned", summary=f"Unassigned {target}")
    messages.success(request, f"{target.title()} assignment removed.")
    return redirect("portal:ticket_detail", reference=reference)


@login_required
@require_POST
def take_over_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_take_over(request.user, ticket):
        return HttpResponse("This ticket is not available for takeover.", status=403)
    ticket.assignees.add(request.user)
    if ticket.assignee_id is None:
        ticket.assignee = request.user
        ticket.save(update_fields=["assignee", "updated_at"])
    TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="takeover", summary=f"{request.user.get_full_name() or request.user.email} took over the ticket")
    messages.success(request, "You have taken over this ticket and can now act on it.")
    return redirect("portal:ticket_detail", reference=reference)


@login_required
@require_POST
def share_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_share(request.user, ticket):
        return HttpResponse("Share permission is required.", status=403)
    form = TicketShareForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, "Select a valid recipient and expiry period.")
        return redirect("portal:ticket_detail", reference=reference)
    share = TicketShare.objects.create(ticket=ticket, created_by=request.user, recipient=form.cleaned_data["recipient"], expires_at=timezone.now() + timedelta(days=form.cleaned_data["expires_in_days"]))
    link = request.build_absolute_uri(reverse("portal:shared_ticket", args=[share.token]))
    notify_users([share.recipient], ticket=ticket, kind="info", title=f"Ticket shared with you: {ticket.reference}", body=link, send_email_message=ticket.category.send_update_email)
    TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="shared", summary=f"Shared with {share.recipient.email}")
    messages.success(request, f"Secure link created for {share.recipient.email}: {link}")
    return redirect("portal:ticket_detail", reference=reference)


@login_required
def shared_ticket(request, token):
    share = get_object_or_404(TicketShare.objects.select_related("ticket", "recipient"), token=token, recipient=request.user, is_active=True, expires_at__gt=timezone.now())
    return redirect("portal:ticket_detail", reference=share.ticket.reference)


@login_required
@require_POST
def decide_ticket_approval(request, reference, approval_id):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    approval = get_object_or_404(TicketApproval.objects.select_related("ticket", "step"), pk=approval_id, ticket=ticket)
    form = TicketApprovalDecisionForm(request.POST)
    if form.is_valid():
        try:
            decide_approval(approval, approved=form.cleaned_data["decision"] == "approve", note=form.cleaned_data["note"], actor=request.user)
            messages.success(request, "Approval decision recorded.")
        except (PermissionError, ValueError) as exc:
            messages.error(request, str(exc))
    return redirect("portal:ticket_detail", reference=reference)


def _attachment_specs_for(ticket):
    specs = list(ticket.category.required_documents or [])
    dynamic = getattr(ticket, "dynamic_data", None)
    if dynamic and dynamic.form_version:
        existing = {item.get("name") for item in specs}
        specs.extend(item for item in dynamic.form_version.schema.get("attachments", {}).get("items", []) if item.get("name") not in existing)
    return specs


@login_required
@require_POST
def upload_attachments(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_edit(request.user, ticket):
        return HttpResponse("Take over this ticket before uploading files.", status=403)
    source_field = request.POST.get("source_field", "general")
    spec = next((item for item in _attachment_specs_for(ticket) if item.get("name") == source_field), None) or {"name": "general", "max_size_mb": 10, "max_count": 10, "allowed_extensions": [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"]}
    uploads = request.FILES.getlist("files")
    errors = []
    if len(uploads) > int(spec.get("max_count", 10)):
        errors.append("Too many files for this document field.")
    allowed = {item.lower() for item in spec.get("allowed_extensions", [])}
    for upload in uploads:
        if allowed and Path(upload.name).suffix.lower() not in allowed:
            errors.append(f"{upload.name}: unsupported file type.")
        if upload.size > int(spec.get("max_size_mb", 10)) * 1024 * 1024:
            errors.append(f"{upload.name}: exceeds {spec.get('max_size_mb', 10)} MB.")
    if errors:
        messages.error(request, " ".join(errors))
        return redirect("portal:ticket_detail", reference=reference)
    for upload in uploads:
        attachment = TicketAttachment(ticket=ticket, uploaded_by=request.user, file=upload, original_name=upload.name, content_type=getattr(upload, "content_type", "application/octet-stream"), size=upload.size, is_restricted=bool(spec.get("restricted")), source_field=source_field)
        attachment.full_clean(); attachment.save()
    if uploads:
        TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="attachment", summary=f"Uploaded {len(uploads)} document(s)")
    messages.success(request, f"Uploaded {len(uploads)} document(s).")
    return redirect("portal:ticket_detail", reference=reference)


@login_required
def notifications(request):
    page = Paginator(Notification.objects.filter(user=request.user), 30).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {"page_obj": page})


@login_required
@require_GET
def notification_feed(request):
    items = Notification.objects.filter(user=request.user)[:10]
    return JsonResponse({"unread": Notification.objects.filter(user=request.user, read_at__isnull=True).count(), "items": [{"id": item.pk, "title": item.title, "body": item.body, "link": item.link, "kind": item.kind, "created_at": item.created_at.isoformat(), "read": bool(item.read_at)} for item in items]})


@login_required
@require_POST
def mark_notifications_read(request):
    ids = request.POST.getlist("ids")
    queryset = Notification.objects.filter(user=request.user, read_at__isnull=True)
    if ids:
        queryset = queryset.filter(pk__in=ids)
    queryset.update(read_at=timezone.now())
    if request.headers.get("HX-Request"):
        return HttpResponse("")
    return redirect(request.POST.get("next") or "portal:notifications")
