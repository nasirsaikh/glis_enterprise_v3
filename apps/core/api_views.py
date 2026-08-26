import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from apps.ai.models import AIInteraction, AISettings
from apps.ai.providers import get_provider
from apps.cms.models import SiteSettings, ThemeSettings
from apps.tickets.models import DynamicForm, Ticket, TicketComment
from services.access import TicketAccessPolicy
from services.dynamic_forms import DynamicTicketForm, safe_schema_payload


def _ticket_payload(ticket, include_dynamic=False):
    payload = {
        "reference": ticket.reference, "subject": ticket.subject, "status": ticket.status,
        "priority": ticket.priority, "project": ticket.project.name_en,
        "product": ticket.product.name_en, "category": ticket.category.name_en,
        "requester": {"id": ticket.requester_id, "email": ticket.requester.email},
        "created_at": ticket.created_at.isoformat(), "updated_at": ticket.updated_at.isoformat(),
    }
    if include_dynamic:
        payload["description"] = ticket.description
        payload["dynamic_data"] = getattr(getattr(ticket, "dynamic_data", None), "values", {})
    return payload


@login_required
@require_http_methods(["GET", "POST"])
def tickets_api(request):
    if request.method == "GET":
        tickets = TicketAccessPolicy.visible_queryset(request.user)[:100]
        return JsonResponse({"count": len(tickets), "results": [_ticket_payload(t) for t in tickets]})
    try:
        data = json.loads(request.body)
        required = ("subject", "description", "project_id", "product_id", "category_id")
        missing = [key for key in required if not data.get(key)]
        if missing:
            return JsonResponse({"errors": {key: "This field is required." for key in missing}}, status=422)
        ticket = Ticket.objects.create(
            subject=data["subject"], description=data["description"], project_id=data["project_id"],
            product_id=data["product_id"], category_id=data["category_id"], requester=request.user,
            priority=data.get("priority", "medium"),
        )
        return JsonResponse(_ticket_payload(ticket, include_dynamic=True), status=201)
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"error": "Invalid JSON payload", "detail": str(exc)}, status=400)


@login_required
@require_http_methods(["GET", "PATCH"])
def ticket_api(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    if request.method == "GET":
        return JsonResponse(_ticket_payload(ticket, include_dynamic=True))
    if not TicketAccessPolicy.can_edit(request.user, ticket):
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)
    for field in ("subject", "description", "status", "priority"):
        if field in data:
            setattr(ticket, field, data[field])
    ticket.save()
    return JsonResponse(_ticket_payload(ticket, include_dynamic=True))


@login_required
@require_POST
def comments_api(request, reference):
    ticket = get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)
    internal = bool(data.get("is_internal"))
    if internal and not TicketAccessPolicy.can_view_internal_notes(request.user, ticket):
        return JsonResponse({"error": "Internal notes are restricted"}, status=403)
    comment = TicketComment.objects.create(ticket=ticket, author=request.user, body=str(data.get("body", ""))[:5000], is_internal=internal)
    return JsonResponse({"id": comment.pk, "body": comment.body, "is_internal": comment.is_internal, "created_at": comment.created_at.isoformat()}, status=201)


@login_required
def form_schema_api(request, form_key):
    dynamic_form = get_object_or_404(DynamicForm.objects.select_related("active_version"), key=form_key, is_active=True, active_version__isnull=False)
    return JsonResponse({"key": dynamic_form.key, "version": dynamic_form.active_version.version, "state": dynamic_form.active_version.state, **safe_schema_payload(dynamic_form.active_version.schema)})


@login_required
@require_POST
def form_validate_api(request, form_key):
    dynamic_form = get_object_or_404(DynamicForm.objects.select_related("active_version"), key=form_key, is_active=True, active_version__isnull=False)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)
    form = DynamicTicketForm(data, schema=dynamic_form.active_version.schema, user=request.user)
    return JsonResponse({"valid": form.is_valid(), "errors": form.errors.get_json_data(), "cleaned_data": form.cleaned_data if form.is_valid() else {}})


@login_required
@require_POST
def ai_analyze_api(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)
    settings = AISettings.load()
    if not settings.is_enabled:
        return JsonResponse({"error": "AI assistance is disabled", "fallback": "Continue with manual review."}, status=503)
    safe_payload = {key: payload.get(key) for key in ("subject", "description", "category", "answers")}
    result = get_provider(settings.provider).analyze_ticket(safe_payload)
    AIInteraction.objects.create(user=request.user, purpose="api_analysis", provider=settings.provider, request_summary={"category": safe_payload.get("category")}, response=result, confidence=result.get("confidence"))
    return JsonResponse(result)


def cms_settings_api(request):
    site, theme = SiteSettings.load(), ThemeSettings.load()
    return JsonResponse({
        "site": {"name_en": site.site_name_en, "name_ar": site.site_name_ar, "short_name": site.short_name, "contact_email": site.contact_email},
        "theme": {"primary": theme.primary, "primary_dark": theme.primary_dark, "accent": theme.accent, "default": theme.default_theme},
    })
