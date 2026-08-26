import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from .models import QueryAudit, VannaSettings


def user_can_access_domain(user, domain):
    if user.is_superuser:
        return True
    allowed = domain.allowed_groups.all()
    return not allowed.exists() or allowed.filter(user=user).exists()


class VannaGateway:
    """Permission-aware adapter for a Vanna 2.0 agent gateway."""

    def ask(self, *, session, question, user):
        if not user_can_access_domain(user, session.domain):
            raise PermissionDenied("You do not have access to this analytics domain.")
        settings = VannaSettings.load()
        started = time.monotonic()
        audit = QueryAudit.objects.create(session=session, question=question, status="pending")
        try:
            if not settings.is_enabled:
                raise RuntimeError("Vanna analytics is disabled by the administrator.")
            if settings.provider == "demo":
                result = self._demo(session.domain, question)
            elif settings.provider == "ollama_vanna":
                from .local_vanna import LocalVannaOllama

                result = LocalVannaOllama().ask(
                    vanna_settings=settings,
                    session=session,
                    question=question,
                    user=user,
                )
            else:
                result = self._http(settings, session, question, user)
            self._validate_sql(result.get("sql", ""), session.domain)
            audit.generated_sql = result.get("sql", "")
            audit.summary = result.get("summary", "")
            audit.result_preview = (result.get("data") or [])[: session.domain.max_rows]
            audit.chart_spec = result.get("chart") or {}
            audit.response_metadata = {
                "provider": result.get("provider", settings.provider),
                "execution_mode": result.get("execution_mode", ""),
                "chroma_memories": result.get("chroma_memories", 0),
                "followups": result.get("followups") or [],
            }
            audit.row_count = len(result.get("data") or [])
            audit.status = "completed"
            return result
        except PermissionDenied:
            audit.status, audit.error_code = "blocked", "permission_denied"
            raise
        except Exception as exc:
            audit.status, audit.error_code, audit.summary = "failed", exc.__class__.__name__[:80], str(exc)[:500]
            raise
        finally:
            audit.duration_ms = int((time.monotonic() - started) * 1000)
            audit.save()
            session.updated_at = timezone.now()
            session.save(update_fields=["updated_at"])

    def _http(self, settings, session, question, user):
        if not settings.endpoint:
            raise RuntimeError("The Vanna gateway endpoint is not configured.")
        rules = list(session.domain.business_rules.filter(is_active=True).values_list("rule_text", flat=True))
        role = getattr(getattr(user, "profile", None), "role", "")
        table_policies = list(session.domain.table_policies.values("table_name", "access", "allowed_roles"))
        column_policies = list(session.domain.column_policies.values("table_name", "column_name", "sensitivity", "default_access", "mask_pattern"))
        row_policies = list(session.domain.row_policies.filter(is_active=True).values("name", "table_name", "predicate_template", "allowed_roles"))
        payload = {
            "question": question,
            "session_id": str(session.pk),
            "user": {"id": str(user.pk), "email": user.email, "role": role},
            "domain": {"slug": session.domain.slug, "collection": session.domain.collection_name, "max_rows": session.domain.max_rows},
            "context": {"schema": session.domain.schema_context, "business_rules": rules, "policies": {"tables": table_policies, "columns": column_policies, "rows": row_policies}},
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        secret = os.environ.get(settings.api_key_env, "") if settings.api_key_env else ""
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        request = Request(settings.endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=settings.timeout_seconds) as response:
                result = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("The Vanna gateway request failed.") from exc
        if not isinstance(result, dict):
            raise RuntimeError("The Vanna gateway returned an invalid response.")
        result.setdefault("data", [])
        result.setdefault("followups", [])
        return result

    def _validate_sql(self, sql, domain):
        if not sql:
            return
        normalized = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.S).strip().lower()
        if not normalized.startswith(("select", "with")) or re.search(r"\b(insert|update|delete|drop|alter|truncate|merge|execute|exec|grant|revoke)\b", normalized):
            raise PermissionDenied("Vanna produced a non-read-only statement, so the request was blocked.")
        denied = [item.table_name.lower() for item in domain.table_policies.filter(access="deny")]
        if any(re.search(rf"\b{re.escape(table)}\b", normalized) for table in denied):
            raise PermissionDenied("Vanna referenced a table denied by the active domain policy.")

    def _demo(self, domain, question):
        lowered = question.lower()
        if "priority" in lowered:
            data = [{"Priority": "Critical", "Tickets": 4}, {"Priority": "High", "Tickets": 8}, {"Priority": "Medium", "Tickets": 15}, {"Priority": "Low", "Tickets": 5}]
            chart = {"type": "bar", "x": "Priority", "y": "Tickets", "title": "Tickets by priority"}
            sql = "SELECT priority, COUNT(*) AS tickets FROM permitted_tickets GROUP BY priority"
        else:
            data = [{"Status": "Open", "Tickets": 12}, {"Status": "In Progress", "Tickets": 9}, {"Status": "Pending Customer", "Tickets": 4}, {"Status": "Resolved", "Tickets": 18}]
            chart = {"type": "bar", "x": "Status", "y": "Tickets", "title": "Ticket overview"}
            sql = "SELECT status, COUNT(*) AS tickets FROM permitted_tickets GROUP BY status"
        return {"sql": sql, "summary": f"Demo analysis for {domain.name}: {len(data)} grouped results. Connect the approved Vanna 2.0 gateway in Admin to use live data.", "data": data, "chart": chart, "followups": ["Show the same trend by month", "Which category has the highest overdue count?"], "provider": "demo"}
