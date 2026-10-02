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
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from apps.ai.models import AIInteraction, AISettings
from apps.ai.providers import get_provider
from apps.core.models import AuditLog
from services.access import TicketAccessPolicy
from services.tenancy import visible_notifications, visible_support_groups, visible_users
from services.dynamic_forms import DynamicTicketForm
from services.ticket_workflow import current_approval_sequence, decide_approval, initialize_approval_workflow, notify_users
from .forms import (
    TicketApprovalDecisionForm, TicketAssignmentForm, TicketCommentForm,
    TicketCreateStep1Form, TicketEditForm, TicketFilterForm, TicketIntakeForm,
    TicketReviewForm, TicketShareForm, UnifiedRequestForm, TicketParticipantForm, TicketApprovalRequestForm,
    TicketApprovalResubmitForm, DashboardFilterForm,
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


@login_required
@require_GET
def ticket_updates(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    response = JsonResponse({'reference':ticket.reference, 'revision':ticket.revision,
                             'status':ticket.get_status_display(), 'approval_state':ticket.get_approval_state_display()})
    response['Cache-Control'] = 'no-store'
    return response


def _apply_ticket_filters(qs, data):
    def selected(name):
        value = data.get(name)
        if not value:
            return []
        return [value] if isinstance(value, (str, int)) or hasattr(value, "_meta") else list(value)

    if data.get("q"):
        term = data["q"]
        qs = qs.filter(Q(reference__icontains=term) | Q(subject__icontains=term) | Q(description__icontains=term) | Q(requester__email__icontains=term))
    for key in ("status", "priority", "project", "category", "product", "approval_state", "policy", "requester", "visibility", "sla_policy"):
        if selected(key):
            qs = qs.filter(**{key + "__in": selected(key)})
    if selected("organization"):
        qs = qs.filter(
            Q(organization__in=selected("organization")) | Q(organization_participants__organization__in=selected("organization"),organization_participants__can_view=True) | Q(organization__isnull=True,requester__profile__organizations__in=selected("organization"))
        ).distinct()
    if selected("organization_type"):
        qs = qs.filter(Q(organization__organization_type__in=selected("organization_type")) | Q(organization_participants__organization__organization_type__in=selected("organization_type"), organization_participants__can_view=True) | Q(organization__isnull=True, requester__profile__organizations__organization_type__in=selected("organization_type"))).distinct()
    if selected("sla"):
        now = timezone.now()
        active = ~Q(status__in=[Ticket.Status.CLOSED, Ticket.Status.RESOLVED, Ticket.Status.PENDING_CUSTOMER])
        sla_conditions = {
            "overdue": active & Q(resolution_due_at__lt=now),
            "at_risk": active & Q(resolution_due_at__gte=now, resolution_due_at__lt=now + timedelta(hours=2)),
            "healthy": active & (Q(resolution_due_at__isnull=True) | Q(resolution_due_at__gte=now + timedelta(hours=2))),
            "paused": Q(status=Ticket.Status.PENDING_CUSTOMER),
            "resolved": Q(status=Ticket.Status.RESOLVED), "closed": Q(status=Ticket.Status.CLOSED),
        }
        condition = Q(pk__in=[])
        for state in selected("sla"):
            condition |= sla_conditions[state]
        qs = qs.filter(condition)
    if selected("group"):
        qs = qs.filter(groups__in=selected("group")).distinct()
    if selected("assignee"):
        qs = qs.filter(Q(assignee__in=selected("assignee")) | Q(assignees__in=selected("assignee"))).distinct()
    if selected("approver"):
        qs = qs.filter(approvals__approver__in=selected("approver")).distinct()
    if selected("request_type"):
        qs = qs.filter(project__request_type__in=selected("request_type"))
    if data.get("date_from"):
        qs = qs.filter(created_at__date__gte=data["date_from"])
    if data.get("date_to"):
        qs = qs.filter(created_at__date__lte=data["date_to"])
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


def _validate_wizard_attachments(request, specs, form, category=None):
    if category and category.creation_attachment_required and not any(request.FILES.getlist(item.get("name", "")) for item in specs):
        form.add_error(None, "Please attach at least one document when creating this ticket.")
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
            if upload.size <= 0:
                form.add_error(None, f"{upload.name}: the uploaded file is empty.")
            if allowed and Path(upload.name).suffix.lower() not in allowed:
                form.add_error(None, spec.get("invalid_type_message") or f"{upload.name} has an unsupported file type.")
            if upload.size > int(spec.get("max_size_mb", 10)) * 1024 * 1024:
                form.add_error(None, f"{upload.name} exceeds the allowed file size.")


@login_required
def dashboard(request):
    qs = TicketAccessPolicy.visible_queryset(request.user)
    form = DashboardFilterForm(request.GET, user=request.user)
    if form.is_valid():
        qs = _apply_ticket_filters(qs, form.cleaned_data)
    else:
        qs = qs.none()
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
    by_status = list(qs.values("status").annotate(total=Count("id", distinct=True)).order_by("status"))
    by_priority = list(qs.values("priority").annotate(total=Count("id", distinct=True)).order_by("priority"))
    by_category = list(qs.values(label=F("category__name_en")).annotate(total=Count("id", distinct=True)).order_by("-total")[:10])
    by_product = list(qs.values(label=F("product__name_en")).annotate(total=Count("id", distinct=True)).order_by("-total")[:10])
    by_project = list(qs.values(label=F("project__name_en")).annotate(total=Count("id", distinct=True)).order_by("-total")[:10])
    by_assignee = list(
        qs.values("assignees__first_name", "assignees__last_name", "assignees__email")
        .annotate(total=Count("id", distinct=True))
        .order_by("-total")[:10]
    )
    for row in by_assignee:
        full_name = " ".join(
            value for value in (row.get("assignees__first_name"), row.get("assignees__last_name")) if value
        ).strip()
        row["label"] = full_name or row.get("assignees__email") or "Unassigned"
    daily_open = list(qs.filter(created_at__gte=now - timedelta(days=13)).annotate(day=TruncDate("created_at")).values("day").annotate(total=Count("id", distinct=True)).order_by("day"))
    chart_data = {"status": by_status, "priority": by_priority, "category": by_category, "product": by_product, "project": by_project, "assignee": by_assignee, "daily_open": daily_open}
    return render(request, "portal/dashboard.html", {"filter_form": form, "metrics": metrics, "chart_data": chart_data, "recent_tickets": qs[:7], "attention": open_qs.filter(Q(priority="critical") | Q(resolution_due_at__lt=now + timedelta(hours=2)))[:6]})


@login_required
def ticket_list(request):
    base_qs = TicketAccessPolicy.visible_queryset(request.user)
    if request.GET.get("owner") == "me":base_qs=base_qs.filter(requester=request.user)
    if request.GET.get("scope") == "group":base_qs=base_qs.filter(groups__members=request.user).distinct()
    form = TicketFilterForm(request.GET,user=request.user)
    if form.is_valid():
        data=form.cleaned_data
        if not data.get("status"):base_qs=base_qs.exclude(status="closed")
        base_qs=_apply_ticket_filters(base_qs,data)

    task_filter = Q(project__request_type='task') | Q(task_item__is_deleted=False)
    counts = {row['project__request_type']:row['total'] for row in base_qs.values('project__request_type').annotate(total=Count('pk',distinct=True))}
    counts['task']=base_qs.filter(task_filter).count()
    counts['service']=base_qs.filter(project__request_type='service',task_item__isnull=True).count()
    workflow_tabs = [{'key':'all','label':_('All'),'count':base_qs.count()}] + [{'key':key,'label':label,'count':counts.get(key,0)} for key,label in Project.RequestType.choices]
    ticket_tab = {'tickets':'service','tasks':'task'}.get(request.GET.get('tab'),request.GET.get('tab','all'))
    qs=base_qs
    if ticket_tab=='task':qs=qs.filter(task_filter).select_related('task_item')
    elif ticket_tab=='service':qs=qs.filter(project__request_type='service',task_item__isnull=True)
    elif ticket_tab in Project.RequestType.values:qs=qs.filter(project__request_type=ticket_tab)
    else:ticket_tab='all'
    service_ticket_count,task_ticket_count=counts['service'],counts['task']


    allowed_sorts = {"created_at", "-created_at", "priority", "-priority", "status", "resolution_due_at", "-resolution_due_at"}
    qs = qs.order_by(request.GET.get("sort") if request.GET.get("sort") in allowed_sorts else "-created_at")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    pagination_query = request.GET.copy()
    pagination_query.pop("page", None)
    template = "tickets/partials/table.html" if request.htmx else "tickets/list.html"
    return render(
        request,
        template,
        {
            "filter_form": form,
            "page_obj": page,
            "ticket_tab": ticket_tab,
            "workflow_tabs": workflow_tabs,
            "pagination_query": pagination_query.urlencode(),
            "service_ticket_count": service_ticket_count,
            "task_ticket_count": task_ticket_count,
        },
    )


@login_required
def ticket_detail(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    comments = ticket.comments.select_related("author__profile").prefetch_related("attachments")
    if not TicketAccessPolicy.can_view_internal_notes(request.user, ticket):
        comments = comments.filter(is_internal=False)
    dynamic_values = getattr(ticket, "dynamic_data", None)
    if dynamic_values and not TicketAccessPolicy.can_view_sensitive(request.user, ticket):
        dynamic_values = dict(dynamic_values.values)
        for key in ticket.dynamic_data.sensitive_keys:
            if key in dynamic_values:
                dynamic_values[key] = "••••••"
    current_sequence = current_approval_sequence(ticket)
    actionable_approvals = ticket.approvals.filter(Q(step__isnull=True) | Q(step__sequence=current_sequence), approver=request.user, status="pending").select_related("step")
    if ticket.status == Ticket.Status.CLOSED or ticket.approval_state != "pending":
        actionable_approvals = actionable_approvals.none()
    events = list(ticket.events.select_related("actor__profile").exclude(event_type="comment"))
    from services.ticket_notifications import event_visible
    events = [event for event in events if event_visible(event, request.user)]
    conversation = [{"comment": comment, "created_at": comment.created_at, "pk": comment.pk} for comment in comments]
    can_view_sensitive = TicketAccessPolicy.can_view_sensitive(request.user, ticket)
    for event in events:
        if can_view_sensitive:
            event.display_details = json.dumps(event.details, indent=2, ensure_ascii=False) if event.details else ""
        else:
            safe_details = {key: value for key, value in event.details.items() if key in {"note", "previous_note", "step", "approval_state", "status_from", "status_to", "changed_fields", "attachment_count"}}
            event.display_details = json.dumps(safe_details, indent=2, ensure_ascii=False) if safe_details else ""
        conversation.append({"event": event, "created_at": event.created_at, "pk": event.pk})
    conversation.sort(key=lambda item: (item["created_at"], item["pk"], bool(item.get("event"))))
    from services.ticket_lifecycle import reopen_deadline
    context = {
        "ticket": ticket, "comments": comments, "conversation": conversation, "ticket_recent_events": events[:5],
        "comment_form": TicketCommentForm(ticket=ticket, user=request.user),
        "can_comment": TicketAccessPolicy.can_comment(request.user, ticket),
        "can_close": TicketAccessPolicy.can_close(request.user, ticket),
        "can_reopen": TicketAccessPolicy.can_reopen(request.user, ticket),
        "reopen_deadline": reopen_deadline(ticket),
        "can_resubmit_approval": TicketAccessPolicy.can_resubmit_approval(request.user, ticket),
        "approval_resubmit_form": TicketApprovalResubmitForm(),
        "dynamic_values": dynamic_values, "can_edit": TicketAccessPolicy.can_edit(request.user, ticket),
        "can_view_sensitive": TicketAccessPolicy.can_view_sensitive(request.user, ticket),
        "can_take_over": TicketAccessPolicy.can_take_over(request.user, ticket),
        "can_assign": TicketAccessPolicy.can_assign(request.user, ticket),
        "can_share": TicketAccessPolicy.can_share(request.user, ticket),
        "assignment_form": TicketAssignmentForm(ticket=ticket, user=request.user),
        "share_form": TicketShareForm(user=request.user,ticket=ticket),
        "can_release": TicketAccessPolicy.can_release(request.user,ticket),
        "participant_form": TicketParticipantForm(ticket=ticket,user=request.user),
        "approval_request_form": TicketApprovalRequestForm(ticket=ticket,user=request.user),
        "tagged_participants": ticket.tagged_participants.filter(is_active=True).select_related("user"),
        "actionable_approvals": actionable_approvals,
        "approval_form": TicketApprovalDecisionForm(),
        "attachment_specs": _attachment_specs_for(ticket),
    }
    if hasattr(ticket,'tpa_transaction'):
        from apps.tpa.views import transaction_detail
        workflow_context = transaction_detail(request,ticket.tpa_transaction.reference,embedded=True)
        if request.headers.get('HX-Request','').lower()=='true' and request.headers.get('HX-History-Restore-Request','').lower()!='true':
            response=render(request,'tpa/transaction/_workspace.html',workflow_context)
            response['HX-Retarget']='#transaction-workspace'
            response['HX-Reswap']='outerHTML'
            response['HX-Push-Url']=workflow_context['step_url']
            patch_vary_headers(response,['HX-Request','HX-History-Restore-Request'])
            return response
        if workflow_context['step_redirected']:
            return redirect(workflow_context['step_url'])
        context.update(workflow_context)
        context['embedded_workflow']=True
        context['ticket']=ticket
    response=render(request,'tickets/detail.html',context)
    patch_vary_headers(response,['HX-Request','HX-History-Restore-Request'])
    return response






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

    if category.comment_attachment_required and not uploads:
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
    ticket = Ticket.objects.select_for_update().select_related("category").get(pk=ticket.pk)
    if not TicketAccessPolicy.can_comment(request.user, ticket):
        return HttpResponse("Comments are limited to the creator and their team while approval is outstanding. Closed tickets must be reopened first.", status=403)
    if request.POST.get("is_internal") and not TicketAccessPolicy.can_view_internal_notes(request.user, ticket):
        return HttpResponse("Internal notes are restricted.", status=403)
    status = request.POST.get('status')
    if status and status != ticket.status and status != Ticket.Status.CLOSED and (not TicketAccessPolicy.can_edit(request.user,ticket) or hasattr(ticket,'tpa_transaction') or ticket.approval_state in {"pending", "rejected", "needs_info"}):
        return HttpResponse('Use the authorized workflow action to change status.',status=403)
    if status == Ticket.Status.CLOSED and not TicketAccessPolicy.can_close(request.user, ticket):
        return HttpResponse("You cannot close this ticket.", status=403)
    form_data = request.POST.copy()
    if status == ticket.status:
        form_data["status"] = ""
    form = TicketCommentForm(form_data, ticket=ticket, user=request.user)
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
    status_changed = bool(selected_status and selected_status != ticket.status)
    if status_changed:
        from services.ticket_lifecycle import update_status
        try:
            update_status(ticket, selected_status, request.user)
        except PermissionError as exc:
            return HttpResponse(str(exc), status=403)
        except ValueError as exc:
            return HttpResponse(str(exc), status=409)
    comment.status = ticket.status
    comment.save()
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

        recipients.extend(tag.user for tag in ticket.tagged_participants.filter(is_active=True).select_related("user"))
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

def _ticket_wizard_frontier(wizard):
    if "selection" not in wizard:
        return 1
    if "dynamic" not in wizard:
        return 2
    if "analysis" not in wizard:
        return 3
    return 4


def _render_ticket_wizard(request, template, context):
    wizard = request.session.get("ticket_wizard", {})
    frontier = _ticket_wizard_frontier(wizard)
    is_htmx = (request.headers.get("HX-Request", "").lower() == "true"
               and request.headers.get("HX-History-Restore-Request", "").lower() != "true")
    context["wizard_layout"] = "components/fragment.html" if is_htmx else "base_portal.html"
    context["workflow_steps"] = [
        {"key": str(index), "label": label, "icon": icon,
         "url": reverse("portal:create_ticket", args=[index]),
         "active": index == context["step"], "accessible": index <= frontier,
         "completed": index < frontier,
         "has_error": index == context["step"] and bool(context["form"].errors)}
        for index, (label, icon) in enumerate([
            (_("Service"), "bi-signpost-split"), (_("Details"), "bi-ui-checks"),
            (_("Clarify"), "bi-stars"), (_("Review"), "bi-check2-square"),
        ], 1)
    ]
    response = render(request, template, context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    if is_htmx:
        response["HX-Push-Url"] = reverse("portal:create_ticket", args=[context["step"]])
    return response


@login_required
@transaction.atomic
def create_ticket(request, step=1):
    if step not in {1, 2, 3, 4}:
        raise Http404
    wizard = request.session.setdefault("ticket_wizard", {})
    frontier = _ticket_wizard_frontier(wizard)
    if step > frontier:
        return redirect("portal:create_ticket", step=frontier)

    if step == 1:
        initial = wizard.get("selection", {})
        form = TicketCreateStep1Form(request.POST or None,initial=initial,user=request.user,)
        if request.method == "POST" and form.is_valid():
            selection = {key: form.cleaned_data[key].pk for key in ("project", "product", "category")}
            selection.update({key: form.cleaned_data[key].pk if form.cleaned_data.get(key) else None for key in ("organization", "policy")})
            if wizard.get("selection") != selection:
                for key in ("dynamic", "answers", "analysis"):
                    wizard.pop(key, None)
            wizard["selection"] = selection
            request.session.modified = True
            return redirect("portal:create_ticket",step=2,)
        return _render_ticket_wizard(
            request,"tickets/wizard/step1.html",{"form": form,"step": 1,},)

    selection_form = TicketCreateStep1Form(wizard["selection"], user=request.user)
    if not selection_form.is_valid():
        request.session.pop("ticket_wizard", None)
        return redirect("portal:create_ticket", step=1)
    category = selection_form.cleaned_data["category"]
    dynamic_form = DynamicForm.objects.filter(category=category, is_active=True, active_version__isnull=False).select_related("active_version").first()
    schema = dynamic_form.active_version.schema if dynamic_form else {"fields": []}
    if step == 2:
        form = DynamicTicketForm(request.POST or None, schema=schema, user=request.user, initial=wizard.get("dynamic", {}))
        if request.method == "POST" and form.is_valid():
            values = _jsonable(form.cleaned_data)
            if wizard.get("dynamic") != values:
                for key in ("answers", "analysis"):
                    wizard.pop(key, None)
            wizard["dynamic"] = values
            request.session.modified = True
            return redirect("portal:create_ticket", step=3)
        return _render_ticket_wizard(request, "tickets/wizard/step2.html", {"form": form, "step": 2, "category": category})

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
        return _render_ticket_wizard(request, "tickets/wizard/step3.html", {"form": form, "questions": ai_settings.intake_questions, "step": 3})

    analysis = wizard.get("analysis", {})
    initial = {"subject": f"{category.name_en} request", "description": wizard.get("dynamic", {}).get("description") or analysis.get("summary", ""), "priority": analysis.get("suggested_priority", category.default_priority)}
    form = TicketReviewForm(request.POST or None, initial=initial)
    attachment_specs = list(schema.get("attachments", {}).get("items", []))
    configured_names = {item.get("name") for item in attachment_specs}
    attachment_specs.extend(item for item in category.required_documents if item.get("name") not in configured_names)
    attachment_specs.append({"name": "creation_attachments", "label": "Supporting documents", "required": False, "multiple": True,
        "max_size_mb": category.comment_attachment_max_size_mb, "max_count": category.comment_attachment_max_count,
        "allowed_extensions": category.comment_attachment_extensions_list})
    review_valid = False
    if request.method == "POST":
        review_valid = form.is_valid()
        _validate_wizard_attachments(request, attachment_specs, form, category)
        review_valid = review_valid and not form.errors
    if request.method == "POST" and review_valid:
        selection = wizard["selection"]
        sla = SLAPolicy.objects.filter(category_id=selection["category"], priority=form.cleaned_data["priority"], is_active=True).first()
        sla = sla or SLAPolicy.objects.filter(project_id=selection["project"],category__isnull=True,priority=form.cleaned_data["priority"],is_active=True).first()
        now = timezone.now()
        ticket = Ticket.objects.create(
            subject=form.cleaned_data["subject"], description=sanitize_rich_text(form.cleaned_data["description"]), requester=request.user,
            project_id=selection["project"], product_id=selection["product"], category_id=selection["category"],
            organization_id=selection.get("organization"), policy_id=selection.get("policy"),
            priority=form.cleaned_data["priority"], sla_policy=sla, ai_summary=analysis.get("summary", ""), ai_recommendations=analysis,
            first_response_due_at=now + timedelta(minutes=sla.first_response_minutes) if sla else None,
            resolution_due_at=now + timedelta(minutes=sla.resolution_minutes) if sla else None,
        )
        from services.business_requests import attach_organizations
        attach_organizations(ticket)
        allowed_group_ids = visible_support_groups(request.user).values_list("pk", flat=True)
        default_groups = list(category.default_groups.filter(pk__in=allowed_group_ids, is_active=True))
        if category.default_group and category.default_group not in default_groups and visible_support_groups(request.user).filter(pk=category.default_group_id).exists():
            default_groups.append(category.default_group)
        ticket.groups.add(*default_groups)
        if category.default_user and visible_users(request.user).filter(pk=category.default_user_id).exists():
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
        #notify_users(assignment_users, ticket=ticket, kind="assignment", title=f"New ticket assigned: {ticket.reference}", body=ticket.subject, send_email_message=category.send_initial_email)
        notify_users(
            assignment_users,
            ticket=ticket,
            kind="assignment",
            title=f"New ticket assigned: {ticket.reference}",
            body=ticket.subject,
            send_email_message=category.send_initial_email,
        )        
        AuditLog.record(request=request, action="ticket.create", instance=ticket, summary=f"Created {ticket.reference}")
        request.session.pop("ticket_wizard", None)
        messages.success(request, f"{ticket.reference} was submitted successfully.")
        if request.headers.get("HX-Request", "").lower() == "true":
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("portal:ticket_detail", args=[ticket.reference])
            return response
        return redirect("portal:ticket_detail", reference=ticket.reference)
    dynamic_review = DynamicTicketForm(
        schema=schema, user=request.user, initial=wizard.get("dynamic", {})
    )
    review_fields = []
    for name, field in dynamic_review.fields.items():
        value = wizard.get("dynamic", {}).get(name)
        if value in (None, "", []):
            continue
        choices = {str(key): str(label) for key, label in getattr(field, "choices", [])}
        if isinstance(value, list):
            display = ", ".join(choices.get(str(item), str(item)) for item in value)
        elif isinstance(value, bool):
            display = _("Yes") if value else _("No")
        else:
            display = choices.get(str(value), str(value))
        review_fields.append({"label": field.label, "value": display})
    return _render_ticket_wizard(request, "tickets/wizard/step4.html", {
        "form": form, "step": 4, "wizard": wizard, "analysis": analysis,
        "category": category, "project": category.product.project, "product": category.product,
        "review_fields": review_fields, "clarification": wizard.get("answers", {}).get("answer_1", ""),
        "attachment_specs": attachment_specs,
    })


# @login_required
# @require_GET
# def product_options(request):
#     products = Product.objects.filter(project_id=request.GET.get("project"), is_active=True)
#     return render(request, "tickets/partials/options.html", {"objects": products, "placeholder": "Select a product"})

from .services.access import (accessible_categories,accessible_products,)

@login_required
@require_GET
def product_options(request):

    project_id = request.GET.get("project")

    products = Product.objects.none()

    if project_id:
        products = (
            accessible_products(request.user)
            .filter(project_id=project_id)
            .order_by("name_en")
        )

    return render(
        request,
        "tickets/partials/options.html",
        {
            "objects": products,
            "placeholder": "Select a product",
        },
    )


# @login_required
# @require_GET
# def category_options(request):
#     categories = Category.objects.filter(product_id=request.GET.get("product"), is_active=True)
#     return render(request, "tickets/partials/options.html", {"objects": categories, "placeholder": "Select a category"})


@login_required
@require_GET
def category_options(request):

    product_id = request.GET.get("product")

    categories = Category.objects.none()

    if product_id:
        categories = (
            accessible_categories(request.user)
            .filter(product_id=product_id)
            .order_by("name_en")
        )

    return render(
        request,
        "tickets/partials/options.html",
        {
            "objects": categories,
            "placeholder": "Select a category",
        },
    )

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
    ticket_tab = request.GET.get("tab")
    if ticket_tab == "tasks":
        qs = qs.filter(task_item__is_deleted=False)
    elif ticket_tab == "tickets":
        qs = qs.filter(task_item__isnull=True)
    if request.GET.get("owner") == "me":
        qs = qs.filter(requester=request.user)
    if request.GET.get("scope") == "group":
        qs = qs.filter(groups__members=request.user).distinct()
    form = TicketFilterForm(request.GET, user=request.user)
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
@transaction.atomic
def edit_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    ticket = Ticket.objects.select_for_update().select_related("category").get(pk=ticket.pk)
    if not TicketAccessPolicy.can_edit(request.user, ticket):
        return HttpResponse("Take over this ticket before editing it.", status=403)
    original_status = ticket.status
    before = {name: getattr(ticket, name) for name in ("subject", "description", "priority", "status")}
    form = TicketEditForm(request.POST or None, instance=ticket, user=request.user)
    dynamic = getattr(ticket, "dynamic_data", None)
    schema = dynamic.form_version.schema if dynamic and dynamic.form_version else {"fields": []}
    dynamic_form = DynamicTicketForm(request.POST or None, schema=schema, user=request.user, initial=dynamic.values if dynamic else {})
    if request.method == "POST" and form.is_valid() and dynamic_form.is_valid():
        updated = form.save(commit=False)
        desired_status = updated.status
        updated.status = original_status
        if desired_status != original_status:
            from services.ticket_lifecycle import update_status
            try:
                update_status(updated, desired_status, request.user)
            except (PermissionError, ValueError) as exc:
                form.add_error("status", str(exc))
        if not form.errors:
            updated.description = sanitize_rich_text(updated.description)
            updated.save()
            if dynamic:
                dynamic.values = _jsonable(dynamic_form.cleaned_data)
                dynamic.save(update_fields=["values", "updated_at"])
            changed = [name for name in before if before[name] != getattr(updated, name)]
            if dynamic and dynamic_form.changed_data:
                changed.extend(dynamic_form.changed_data)
            TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="edited", summary="Ticket details updated", details={"status_from": original_status, "status_to": updated.status, "changed_fields": changed})
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
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    form = TicketAssignmentForm(request.POST, ticket=ticket, user=request.user)
    if not form.is_valid():
        return HttpResponse("Select authorized organizations, groups and staff members.",status=400)
    before={"primary":ticket.assignee_id,"users":list(ticket.assignees.values_list("pk",flat=True)),"groups":list(ticket.groups.values_list("pk",flat=True))}
    users, groups = list(form.cleaned_data["users"]), list(form.cleaned_data["groups"])
    if form.cleaned_data["replace_existing"]:
        ticket.assignees.set(users); ticket.groups.set(groups)
    else:
        ticket.assignees.add(*users); ticket.groups.add(*groups)
    ticket.assignee = ticket.assignees.order_by("first_name", "email").first()
    ticket.save(update_fields=["assignee", "updated_at"])
    TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="assignment", summary="Ticket assignment updated", details={"before":before,"after":{"primary":ticket.assignee_id,"users":[user.pk for user in ticket.assignees.all()],"groups":[group.pk for group in ticket.groups.all()]}})
    notify_users(list(ticket.assignees.all()), ticket=ticket, kind="assignment", title=f"Ticket assigned: {ticket.reference}", body=ticket.subject, send_email_message=ticket.category.send_update_email)
    messages.success(request, "Ticket assignment was updated.")
    return participant_response(request,ticket)


@login_required
@require_POST
@transaction.atomic
def unassign_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_assign(request.user, ticket):
        return HttpResponse("Assignment permission is required.", status=403)
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    target = request.POST.get("target", "all")
    if target not in {"users", "groups", "all"}:
        return HttpResponse("Invalid assignment target.", status=400)
    if target in {"users", "all"}:
        ticket.assignees.clear(); ticket.assignee = None; ticket.save(update_fields=["assignee", "updated_at"])
    if target in {"groups", "all"}:
        ticket.groups.clear()
    TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="unassigned", summary=f"Unassigned {target}")
    messages.success(request, f"{target.title()} assignment removed.")
    return participant_response(request,ticket)


@login_required
@require_POST
def take_over_ticket(request,reference):
    from services.ticket_participants import take_over_ticket as take
    ticket=get_object_or_404(TicketAccessPolicy.visible_queryset(request.user),reference=reference)
    try:take(ticket,request.user)
    except PermissionError as exc:return HttpResponse(str(exc),status=403)
    except ValueError as exc:return HttpResponse(str(exc),status=409)
    return participant_response(request,ticket)


@login_required
@require_POST
def share_ticket(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if not TicketAccessPolicy.can_share(request.user, ticket):
        return HttpResponse("Share permission is required.", status=403)
    form = TicketShareForm(request.POST, user=request.user,ticket=ticket)
    if not form.is_valid():
        messages.error(request, "Select a valid recipient and expiry period.")
        return redirect("portal:ticket_detail", reference=reference)
    share = TicketShare.objects.create(ticket=ticket, created_by=request.user, recipient=form.cleaned_data["recipient"], expires_at=timezone.now() + timedelta(days=form.cleaned_data["expires_in_days"]))
    link = request.build_absolute_uri(reverse("portal:shared_ticket", args=[share.token]))
    notify_users([share.recipient], ticket=ticket, kind="info", title=f"Ticket shared with you: {ticket.reference}", body=link, send_email_message=ticket.category.send_update_email)
    TicketEvent.objects.create(ticket=ticket, actor=request.user, event_type="shared", summary=f"Shared with {share.recipient.email}")
    messages.success(request, f"Secure link created for {share.recipient.email}: {link}")
    return participant_response(request,ticket)


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
    if not form.is_valid():return HttpResponse(" ".join(str(error) for errors in form.errors.values() for error in errors),status=400)
    try:decide_approval(approval,decision=form.cleaned_data['decision'],note=form.cleaned_data['note'],actor=request.user)
    except PermissionError as exc:return HttpResponse(str(exc),status=403)
    except ValueError as exc:return HttpResponse(str(exc),status=409)
    return participant_response(request,ticket)


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
    page = Paginator(visible_notifications(request.user), 20).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {"page_obj": page})


@login_required
@require_GET
def notification_feed(request):
    items = visible_notifications(request.user)[:10]
    return JsonResponse({"unread": visible_notifications(request.user).filter(read_at__isnull=True).count(), "items": [{"id": item.pk, "title": item.title, "body": item.body, "link": item.link, "kind": item.kind, "created_at": item.created_at.isoformat(), "read": bool(item.read_at)} for item in items]})


@login_required
@require_POST
def mark_notifications_read(request):
    ids = request.POST.getlist("ids")
    queryset = visible_notifications(request.user).filter(read_at__isnull=True)
    if ids:
        queryset = queryset.filter(pk__in=ids)
    queryset.update(read_at=timezone.now())
    if request.headers.get("HX-Request"):
        return HttpResponse("")
    return redirect(request.POST.get("next") or "portal:notifications")


def participant_response(request,ticket):
    if request.headers.get('HX-Request','').lower()=='true':
        response=HttpResponse(status=204);response['HX-Redirect']=reverse('portal:ticket_detail',args=[ticket.reference]);return response
    return redirect('portal:ticket_detail',reference=ticket.reference)


@login_required
@require_POST
def close_ticket(request, reference):
    from services.ticket_lifecycle import close_ticket as close
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    try:
        close(ticket, request.user)
    except PermissionError as exc:
        return HttpResponse(str(exc), status=403)
    except ValueError as exc:
        return HttpResponse(str(exc), status=409)
    return participant_response(request, ticket)


@login_required
@require_POST
def reopen_ticket(request, reference):
    from services.ticket_lifecycle import reopen_ticket as reopen
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    try:
        reopen(ticket, request.user)
    except PermissionError as exc:
        return HttpResponse(str(exc), status=403)
    except ValueError as exc:
        return HttpResponse(str(exc), status=409)
    return participant_response(request, ticket)


@login_required
@require_POST
def resubmit_ticket_approval(request, reference):
    from services.ticket_workflow import resubmit_approval
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    form = TicketApprovalResubmitForm(request.POST)
    if not form.is_valid():
        return HttpResponse("Describe how the query or rejection has been addressed (maximum 2000 characters).", status=400)
    try:
        resubmit_approval(ticket, actor=request.user, note=form.cleaned_data["note"])
    except PermissionError as exc:
        return HttpResponse(str(exc), status=403)
    except ValueError as exc:
        return HttpResponse(str(exc), status=409)
    return participant_response(request, ticket)

@login_required
@require_POST
def release_ticket(request,reference):
    from services.ticket_participants import release_ticket as release
    ticket=get_object_or_404(TicketAccessPolicy.visible_queryset(request.user),reference=reference)
    try:release(ticket,request.user)
    except PermissionError as exc:return HttpResponse(str(exc),status=403)
    return participant_response(request,ticket)

@login_required
@require_POST
def tag_ticket_user(request,reference):
    from services.ticket_participants import tag_user
    ticket=get_object_or_404(TicketAccessPolicy.visible_queryset(request.user),reference=reference)
    if not TicketAccessPolicy.can_share(request.user,ticket):return HttpResponse('Participant management permission is required.',status=403)
    active=request.POST.get('action')!='untag'
    if active:
        data=request.POST.copy()
        if 'users' not in data and data.get('user'):data.setlist('users',data.getlist('user'))
        form=TicketParticipantForm(data,ticket=ticket,user=request.user)
        if not form.is_valid():return HttpResponse('Select an authorized user.',status=400)
        targets=list(form.cleaned_data['users'])
    else:
        value=request.POST.get('user','')
        if not value.isdigit():return HttpResponse('Select an active tagged user.',status=400)
        target=get_object_or_404(ticket.tagged_users.filter(ticket_tags__ticket=ticket,ticket_tags__is_active=True),pk=value)
        targets=[target]
    try:
        with transaction.atomic():
            for target in targets:tag_user(ticket,request.user,target,active=active)
    except PermissionError as exc:return HttpResponse(str(exc),status=403)
    except ValueError as exc:return HttpResponse(str(exc),status=400)
    return participant_response(request,ticket)

@login_required
@require_POST
def request_ticket_approval(request,reference):
    from services.ticket_participants import request_approval
    ticket=get_object_or_404(TicketAccessPolicy.visible_queryset(request.user),reference=reference)
    if not TicketAccessPolicy.can_share(request.user,ticket):return HttpResponse('Approval request permission is required.',status=403)
    form=TicketApprovalRequestForm(request.POST,ticket=ticket,user=request.user)
    if not form.is_valid():return HttpResponse('Select an authorized approver.',status=400)
    try:request_approval(ticket,request.user,form.cleaned_data['approver'],form.cleaned_data['note'])
    except PermissionError as exc:return HttpResponse(str(exc),status=403)
    except ValueError as exc:return HttpResponse(str(exc),status=400)
    return participant_response(request,ticket)

@login_required
@require_POST
def cancel_ticket_approval(request,reference,approval_id):
    from services.ticket_participants import cancel_approval
    ticket=get_object_or_404(TicketAccessPolicy.visible_queryset(request.user),reference=reference)
    approval=get_object_or_404(ticket.approvals,pk=approval_id)
    try:cancel_approval(approval,request.user)
    except PermissionError as exc:return HttpResponse(str(exc),status=403)
    except ValueError as exc:return HttpResponse(str(exc),status=400)
    return participant_response(request,ticket)

@login_required
@require_GET
def assignment_options(request,reference):
    ticket=get_object_or_404(TicketAccessPolicy.visible_queryset(request.user),reference=reference)
    if not TicketAccessPolicy.can_assign(request.user,ticket):return HttpResponse('Assignment permission is required.',status=403)
    return render(request,'tickets/partials/assignment_fields.html',{'ticket':ticket,'assignment_form':TicketAssignmentForm(ticket=ticket,user=request.user,initial=request.GET.dict())})

@login_required
def create_request(request):
    from apps.tpa.models import MemberTransaction
    from apps.tpa.services.access import can_create_policy_enrollment
    if request.method=='POST' and request.POST.get('request_type')=='task':return redirect('tasks:create')
    form=UnifiedRequestForm(request.POST if request.method=='POST' else None,user=request.user,initial=request.GET.dict())
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data;kind=data['request_type'];project=data['project']
        if kind=='policy' and project.workflow_type=='NEW_POLICY_ENROLLMENT':
            if not can_create_policy_enrollment(request.user):return HttpResponse('Enrollment permission is required.',status=403)
            request.session['policy_request_context']={'product':data['product'].pk,'policy_type':data['policy_type'],'organization':data['organization'].pk if data.get('organization') else None}
            return redirect('tpa:policy_enrollment_create')
        if kind=='claim' and not (request.user.is_superuser or request.user.has_perm('tickets.add_ticket')):return HttpResponse('Claim creation permission is required.',status=403)
        if kind=='endorsement':
            from apps.tpa.services.access import can_create_for_policy
            if not can_create_for_policy(request.user,data['policy'],project.workflow_type):return HttpResponse('Endorsement permission is required for this policy.',status=403)
        if kind=='endorsement' and project.workflow_type in MemberTransaction.Type.values:
            policy=data['policy']
            tx=MemberTransaction.objects.create(policy=policy,organization=policy.organization,insurer=policy.organization,requester=request.user,requester_organization=policy.organization,transaction_type=project.workflow_type,effective_date=data['effective_date'],metadata={'workflow_project_id':project.pk},physical_card_required=policy.physical_card_required and project.workflow_type=='MEMBER_ADD')
            if tx.transaction_type=='POLICY_CANCEL':
                from apps.tpa.services.member_selection import populate_policy_cancellation
                populate_policy_cancellation(tx)
            return participant_response(request,tx.ticket)
        org=data.get('organization') or (data['policy'].organization if data.get('policy') else None)
        request.session['ticket_wizard']={'selection':{'project':project.pk,'product':data['product'].pk,'category':data['category'].pk,'organization':org.pk if org else None,'policy':data['policy'].pk if data.get('policy') else None}}
        return redirect('portal:create_ticket',step=2)
    template='tickets/partials/request_fields.html' if request.method=='GET' and request.headers.get('HX-Request','').lower()=='true' else 'tickets/request_form.html'
    return render(request,template,{'form':form})
