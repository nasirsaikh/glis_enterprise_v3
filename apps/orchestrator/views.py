from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import AIDomain, AnalysisSession, QueryAudit, VannaSettings
from .services import VannaGateway, user_can_access_domain


def accessible_domains(user):
    return [domain for domain in AIDomain.objects.filter(is_active=True).prefetch_related("allowed_groups") if user_can_access_domain(user, domain)]


def _serialize_query(query):
    metadata = query.response_metadata or {}
    return {
        "id": query.pk,
        "question": query.question,
        "sql": query.generated_sql,
        "summary": query.summary,
        "data": query.result_preview or [],
        "chart": query.chart_spec or {},
        "status": query.status,
        "row_count": query.row_count,
        "duration_ms": query.duration_ms,
        "error_code": query.error_code,
        "created_at": query.created_at.isoformat(),
        "provider": metadata.get("provider", ""),
        "execution_mode": metadata.get("execution_mode", ""),
        "chroma_memories": metadata.get("chroma_memories", 0),
        "followups": metadata.get("followups", []),
        "export_url": reverse("orchestrator:export_query", args=[query.pk]) if query.status == "completed" and query.result_preview else "",
    }


def _serialize_session(session):
    return {
        "id": str(session.pk),
        "title": session.title or "Untitled analysis",
        "domain_id": session.domain_id,
        "domain": session.domain.name,
        "updated_at": session.updated_at.isoformat(),
        "question_count": getattr(session, "question_count", session.queries.count()),
    }


@login_required
def console(request):
    domains = accessible_domains(request.user)
    domain = next((item for item in domains if str(item.pk) == request.GET.get("domain")), domains[0] if domains else None)
    prompts = domain.suggested_prompts.filter(is_active=True) if domain else []
    sessions = []
    active_session = None
    if domain:
        sessions = list(AnalysisSession.objects.filter(user=request.user, domain=domain, is_active=True).select_related("domain").annotate(question_count=Count("queries"))[:50])
        requested_session = request.GET.get("session")
        if requested_session:
            active_session = next((item for item in sessions if str(item.pk) == requested_session), None)
        if active_session is None:
            active_session = sessions[0] if sessions else None
    return render(
        request,
        "orchestrator/console.html",
        {
            "domains": domains,
            "selected_domain": domain,
            "suggested_prompts": prompts,
            "vanna_settings": VannaSettings.load(),
            "analysis_sessions": sessions,
            "active_session": active_session,
        },
    )


@login_required
@require_POST
def ask(request):
    domain = get_object_or_404(AIDomain, pk=request.POST.get("domain"), is_active=True)
    if not user_can_access_domain(request.user, domain):
        raise PermissionDenied
    question = request.POST.get("question", "").strip()
    if not question:
        return JsonResponse({"error": "Please enter a question."}, status=400)
    session_id = request.POST.get("session_id")
    session = AnalysisSession.objects.filter(pk=session_id, user=request.user, domain=domain, is_active=True).first() if session_id else None
    if session is None:
        session = AnalysisSession.objects.create(user=request.user, domain=domain, title=question[:120])
    try:
        result = VannaGateway().ask(session=session, question=question, user=request.user)
    except Exception as exc:
        failed_query = session.queries.order_by("-created_at", "-pk").first()
        return JsonResponse({
            "error": str(exc),
            "session_id": str(session.pk),
            "query": _serialize_query(failed_query) if failed_query else None,
        }, status=503)
    query = session.queries.order_by("-created_at", "-pk").first()
    result.update({
        "session_id": str(session.pk),
        "session": _serialize_session(session),
        "query": _serialize_query(query) if query else None,
    })
    return JsonResponse(result)


@login_required
def session_list(request):
    sessions = AnalysisSession.objects.filter(user=request.user, is_active=True).select_related("domain").annotate(question_count=Count("queries"))
    domain_id = request.GET.get("domain")
    if domain_id:
        sessions = sessions.filter(domain_id=domain_id)
    allowed_domain_ids = {domain.pk for domain in accessible_domains(request.user)}
    return JsonResponse({"sessions": [_serialize_session(session) for session in sessions if session.domain_id in allowed_domain_ids]})


@login_required
def session_detail(request, session_id):
    session = get_object_or_404(AnalysisSession.objects.select_related("domain"), pk=session_id, user=request.user, is_active=True)
    if not user_can_access_domain(request.user, session.domain):
        raise PermissionDenied
    queries = session.queries.all()
    return JsonResponse({"session": _serialize_session(session), "queries": [_serialize_query(query) for query in queries]})


@login_required
def export_result(request, session_id):
    import csv
    from django.http import HttpResponse
    session = get_object_or_404(AnalysisSession, pk=session_id, user=request.user)
    audit = session.queries.filter(status="completed").order_by("-created_at", "-pk").first()
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="vanna-{session.pk}.csv"'
    rows = audit.result_preview if audit else []
    if rows:
        writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
    return response


@login_required
def export_query(request, query_id):
    import csv
    from django.http import HttpResponse
    audit = get_object_or_404(QueryAudit.objects.select_related("session"), pk=query_id, session__user=request.user, status="completed")
    if not user_can_access_domain(request.user, audit.session.domain):
        raise PermissionDenied
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="vanna-query-{audit.pk}.csv"'
    rows = audit.result_preview or []
    if rows:
        writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return response
