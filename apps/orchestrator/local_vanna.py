"""Direct Vanna 2.0 + Ollama analytics for the Django application database."""

from __future__ import annotations

import json
import re
from uuid import uuid4
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings as django_settings
from django.db import connection

from services.access import TicketAccessPolicy


FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|merge|execute|exec|grant|revoke|"
    r"attach|detach|pragma|vacuum|create|replace|call|copy)\b",
    re.IGNORECASE,
)
TABLE_REFERENCE = re.compile(
    r"\b(?:from|join)\s+([A-Za-z0-9_\.\[\]`\"]+)",
    re.IGNORECASE,
)
CTE_NAME = re.compile(
    r"(?:\bwith\b|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(",
    re.IGNORECASE,
)


def _identifier(value: str) -> str:
    return value.replace("[", "").replace("]", "").replace('"', "").replace("`", "").lower()


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _extract_sql_candidate(content: Any) -> str:
    """Extract one SQL candidate from Ollama's structured-output fallback."""

    if isinstance(content, dict):
        return str(content.get("sql") or "").strip()

    text = str(content or "").strip()
    if not text:
        return ""

    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict) and payload.get("sql"):
        return str(payload["sql"]).strip()

    fenced = re.search(r"```(?:sql)?\s*(select\b.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip().rstrip(";")

    plain = re.search(r"(?is)\b(select\b.*?)(?:;\s*(?:\n|$)|$)", text)
    return plain.group(1).strip() if plain else ""


class SqlGovernor:
    """Validate Vanna SQL and apply the portal's ticket visibility scope."""

    def __init__(self, *, domain, user):
        self.domain = domain
        self.user = user
        self.role = getattr(getattr(user, "profile", None), "role", "") or "user"
        self.allowed_tables = {_identifier(item).split(".")[-1] for item in domain.allowed_tables}
        self.table_policies = list(domain.table_policies.all())
        self.column_policies = list(domain.column_policies.prefetch_related("role_overrides"))
        self.visible_ticket_ids = list(
            TicketAccessPolicy.visible_queryset(user).values_list("pk", flat=True)
        )
        self.last_generated_sql = ""
        self.last_effective_sql = ""

    def govern(self, sql: str) -> str:
        generated = self._clean(sql)
        self._validate_read_only(generated)
        references = self._validate_tables(generated)
        self._validate_columns(generated)
        effective = self._scope_tickets(generated, references)
        self.last_generated_sql = generated
        self.last_effective_sql = effective
        return effective

    @staticmethod
    def _clean(sql: str) -> str:
        sql = str(sql or "").strip()
        sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE).strip()
        sql = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.DOTALL).strip()
        if sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    @staticmethod
    def _validate_read_only(sql: str) -> None:
        if not sql:
            raise ValueError("Vanna did not generate SQL.")
        if not re.match(r"^select\b", sql, re.IGNORECASE):
            raise ValueError("Only SELECT queries are permitted; submit a single statement.")
        if ";" in sql:
            raise ValueError("Multiple SQL statements are not permitted.")
        if FORBIDDEN_SQL.search(sql):
            raise ValueError("Vanna generated a non-read-only SQL statement.")

    def _validate_tables(self, sql: str) -> set[str]:
        cte_names = {_identifier(item) for item in CTE_NAME.findall(sql)}
        references: set[str] = set()
        for raw in TABLE_REFERENCE.findall(sql):
            normalized = _identifier(raw)
            table = normalized.split(".")[-1]
            if table in cte_names:
                continue
            references.add(table)
            if table not in self.allowed_tables:
                raise ValueError(f"Table '{table}' is not allowed in this analytics domain.")
            policy = next(
                (item for item in self.table_policies if _identifier(item.table_name).split(".")[-1] == table),
                None,
            )
            if policy and policy.access == "deny":
                raise ValueError(f"Table '{table}' is denied by the active table policy.")
            if policy and policy.allowed_roles and self.role not in policy.allowed_roles:
                raise ValueError(f"Your role is not permitted to query table '{table}'.")
        return references

    def _column_access(self, policy) -> str:
        override = next(
            (item for item in policy.role_overrides.all() if item.role == self.role),
            None,
        )
        return override.access if override else policy.default_access

    def _validate_columns(self, sql: str) -> None:
        for policy in self.column_policies:
            if self._column_access(policy) != "deny":
                continue
            if re.search(rf"\b{re.escape(policy.column_name)}\b", sql, re.IGNORECASE):
                raise ValueError(
                    f"Column '{policy.table_name}.{policy.column_name}' is denied for your role."
                )

    def _scope_tickets(self, sql: str, references: set[str]) -> str:
        table = "tickets_ticket"
        if table not in references or self.user.is_superuser or self.user.has_perm("tickets.view_all"):
            return sql

        # A schema-qualified reference could bypass the scoped CTE, so scoped users
        # may only reference the unqualified logical table name.
        for raw in TABLE_REFERENCE.findall(sql):
            normalized = _identifier(raw)
            if normalized.split(".")[-1] == table and normalized != table:
                raise ValueError("Use the unqualified tickets_ticket table in scoped analytics queries.")

        ids = ",".join(str(pk) for pk in self.visible_ticket_ids) or "NULL"
        vendor = connection.vendor
        if vendor == "sqlite":
            physical_table = 'main."tickets_ticket"'
        elif vendor in {"microsoft", "mssql"}:
            schema = getattr(django_settings, "VANNA_DB_SCHEMA", "dbo")
            physical_table = f"[{schema}].[tickets_ticket]"
        else:
            schema = getattr(django_settings, "VANNA_DB_SCHEMA", "public")
            physical_table = f'"{schema}"."tickets_ticket"'

        scope_cte = f"tickets_ticket AS (SELECT * FROM {physical_table} WHERE id IN ({ids}))"
        if re.match(r"^with\b", sql, re.IGNORECASE):
            return re.sub(r"^with\s+", f"WITH {scope_cte}, ", sql, count=1, flags=re.IGNORECASE)
        return f"WITH {scope_cte} {sql}"

    def mask_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mask_columns = {
            policy.column_name.lower(): policy.mask_pattern
            for policy in self.column_policies
            if self._column_access(policy) == "mask"
        }
        output = []
        for row in rows:
            clean = {}
            for column, value in row.items():
                if column.lower() in mask_columns and value not in (None, ""):
                    text = str(value)
                    clean[column] = f"{text[:1]}••••" if text else "••••"
                else:
                    clean[column] = _json_value(value)
            output.append(clean)
        return output


def _database_dialect() -> str:
    vendor = connection.vendor
    if vendor == "sqlite":
        return "SQLite"
    if vendor in {"microsoft", "mssql"}:
        return "Microsoft SQL Server T-SQL"
    if vendor == "postgresql":
        return "PostgreSQL"
    if vendor == "mysql":
        return "MySQL"
    return vendor


def _system_prompt(*, vanna_settings, domain, user, session, retrieved_context="") -> str:
    role = getattr(getattr(user, "profile", None), "role", "") or "user"
    rules = list(
        domain.business_rules.filter(is_active=True).values("name", "rule_text", "sql_guidance")
    )
    prompts = list(
        domain.training_prompts.filter(is_active=True).values("name", "prompt_type", "content", "version")
    )
    candidates = list(
        domain.training_candidates.filter(status__in=["approved", "trained"])
        .values("kind", "question", "sql", "content")[:30]
    )
    recent = list(
        session.queries.filter(status="completed")
        .order_by("-created_at")
        .values("question", "generated_sql", "summary")[:5]
    )
    table_policies = list(domain.table_policies.values("table_name", "access", "allowed_roles"))
    column_policies = list(
        domain.column_policies.values(
            "table_name", "column_name", "sensitivity", "default_access", "mask_pattern"
        )
    )
    row_policies = list(
        domain.row_policies.filter(is_active=True).values(
            "name", "table_name", "predicate_template", "allowed_roles"
        )
    )

    rule_text = "\n".join(
        f"- {item['name']}: {item['rule_text']} SQL guidance: {item['sql_guidance']}" for item in rules
    ) or "- No additional business rules."
    prompt_text = "\n".join(
        f"- [{item['prompt_type']} v{item['version']}] {item['name']}: {item['content']}"
        for item in prompts
    ) or "- No additional training prompts."
    examples = "\n".join(
        f"- Kind={item['kind']}; Question={item['question']}; SQL={item['sql']}; Context={item['content']}"
        for item in candidates
    ) or "- No approved examples."
    history = "\n".join(
        f"- Question={item['question']}; SQL={item['generated_sql']}; Summary={item['summary']}"
        for item in reversed(recent)
    ) or "- No earlier questions in this session."

    return f"""{vanna_settings.system_prompt}

You are generating SQL for Vanna 2.0 using Ollama and ChromaDB retrieval. The
application—not the language model—will execute the SQL through Vanna's governed
run_sql tool after validation.

Mandatory execution rules:
- Database dialect: {_database_dialect()}.
- Authenticated role: {role}.
- Generate exactly one read-only SELECT query. Do not generate a leading WITH query.
- Use only these tables: {', '.join(domain.allowed_tables)}.
- Never use INSERT, UPDATE, DELETE, DDL, procedures, PRAGMA or multiple statements.
- Never schema-qualify tickets_ticket; the application transparently applies the
  authenticated user's permitted-ticket scope before execution.
- Prefer explicit columns. Never use SELECT * unless an approved example requires it.
- Apply NULLIF to divisors and handle NULL values in aggregates.
- Keep the result at or below {domain.max_rows} rows.
- Return only JSON with one key: {{"sql": "SELECT ..."}}.
- Do not explain the SQL and do not invent query results.

Domain schema context:
{domain.schema_context or 'Use Django application table names and conventional foreign-key columns.'}

Business rules maintained in Admin:
{rule_text}

Training prompts maintained in Admin:
{prompt_text}

Approved training examples maintained in Admin:
{examples}

Table policies: {table_policies}
Column policies: {column_policies}
Row policy descriptions: {row_policies}

Recent conversation context:
{history}

Relevant ChromaDB memories for this question:
{retrieved_context or '- No matching ChromaDB memory was found.'}

Training governance:
{vanna_settings.training_prompt}
""".strip()


def _chart_spec(question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows or len(rows[0]) < 2:
        return {}
    columns = list(rows[0].keys())
    numeric = [
        column
        for column in columns
        if any(isinstance(row.get(column), (int, float)) and not isinstance(row.get(column), bool) for row in rows)
    ]
    if not numeric:
        return {}
    y = numeric[-1]
    x = next((column for column in columns if column != y), columns[0])
    lowered = question.lower()
    x_values = [str(row.get(x, "")) for row in rows]
    looks_temporal = any(re.search(r"\d{4}[-/]\d{1,2}", value) for value in x_values)
    if any(token in lowered for token in ("trend", "day", "month", "year", "over time")) or looks_temporal:
        chart_type = "line"
    elif any(token in lowered for token in ("pie", "status", "priority", "assigned")) and len(rows) <= 12:
        chart_type = "pie"
    else:
        chart_type = "bar"
    return {"type": chart_type, "x": x, "y": y, "title": question[:100]}


def _followups(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Show open tickets by priority", "Show overdue tickets by category"]
    columns = list(rows[0].keys())
    dimension = columns[0].replace("_", " ")
    return [
        f"Show the same result by month and {dimension}",
        "Compare first-response TAT and resolution TAT",
    ]


class LocalVannaOllama:
    """Chroma-RAG SQL generation with deterministic Vanna run_sql execution."""

    def ask(self, *, vanna_settings, session, question, user) -> dict[str, Any]:
        if not vanna_settings.allow_sql_execution:
            raise RuntimeError(
                "Enable 'Allow SQL execution' in Admin → Orchestrator → Vanna settings."
            )
        return async_to_sync(self._ask_async)(
            vanna_settings=vanna_settings,
            session=session,
            question=question,
            user=user,
        )

    async def _ask_async(self, *, vanna_settings, session, question, user):
        try:
            import ollama
            import pandas as pd
            from vanna.capabilities.file_system import FileSystem
            from vanna.capabilities.file_system.models import CommandResult
            from vanna.capabilities.sql_runner import SqlRunner
            from vanna.capabilities.sql_runner import RunSqlToolArgs
            from vanna.core.tool import ToolContext
            from vanna.core.user import User as VannaUser
            from vanna.tools import RunSqlTool
            from .chroma_memory import ChromaDomainMemory
        except ImportError as exc:
            raise RuntimeError(
                "Vanna/Ollama/ChromaDB dependencies are missing. "
                "Run: pip install -r requirements.txt"
            ) from exc

        governor = await sync_to_async(SqlGovernor, thread_sensitive=True)(
            domain=session.domain,
            user=user,
        )
        max_rows = session.domain.max_rows

        class DjangoSqlRunner(SqlRunner):
            async def run_sql(self, args, context):
                return await sync_to_async(self._execute, thread_sensitive=True)(args.sql)

            @staticmethod
            def _execute(sql):
                effective_sql = governor.govern(sql)
                with connection.cursor() as cursor:
                    cursor.execute(effective_sql)
                    columns = [item[0] for item in (cursor.description or [])]
                    records = cursor.fetchmany(max_rows + 1) if columns else []
                records = records[:max_rows]
                rows = [dict(zip(columns, record)) for record in records]
                return pd.DataFrame(governor.mask_rows(rows), columns=columns)

        class NoopFileSystem(FileSystem):
            """Prevent Vanna's SQL tool from writing temporary CSV files."""

            async def list_files(self, directory, context):
                return []

            async def read_file(self, filename, context):
                return ""

            async def write_file(self, filename, content, context, overwrite=False):
                return None

            async def exists(self, path, context):
                return False

            async def is_directory(self, path, context):
                return False

            async def search_files(self, query, context, *, max_results=20, include_content=False):
                return []

            async def run_bash(self, command, context, *, timeout=None):
                return CommandResult(stdout="", stderr="Disabled", returncode=1)

        role = governor.role
        vanna_user = VannaUser(
            id=str(user.pk),
            username=user.get_username(),
            email=user.email,
            group_memberships=[role, "admin" if user.is_staff or user.is_superuser else "user"],
            metadata={"django_user_id": user.pk, "domain": session.domain.slug},
        )

        model = getattr(django_settings, "OLLAMA_MODEL", "qwen2.5-coder:7b")
        host = vanna_settings.endpoint or getattr(
            django_settings, "OLLAMA_HOST", "http://127.0.0.1:11434"
        )
        context_window = int(getattr(django_settings, "OLLAMA_CONTEXT_WINDOW", 8192))
        temperature = float(getattr(django_settings, "OLLAMA_TEMPERATURE", 0.1))

        memory = await sync_to_async(ChromaDomainMemory, thread_sensitive=True)(
            domain=session.domain,
            vanna_settings=vanna_settings,
        )
        synced_documents = await sync_to_async(memory.sync_from_admin, thread_sensitive=True)()
        retrieved = await sync_to_async(memory.retrieve, thread_sensitive=True)(question)
        retrieved_context = "\n\n".join(
            f"[{item['source_type']}] {item['content']}" for item in retrieved
        )
        prompt = await sync_to_async(_system_prompt, thread_sensitive=True)(
            vanna_settings=vanna_settings,
            domain=session.domain,
            user=user,
            session=session,
            retrieved_context=retrieved_context,
        )

        client = ollama.Client(host=host, timeout=vanna_settings.timeout_seconds)
        sql_format = {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        }
        generation_messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": question},
        ]
        response = await sync_to_async(client.chat, thread_sensitive=True)(
            model=model,
            messages=generation_messages,
            format=sql_format,
            options={
                "num_ctx": context_window,
                "temperature": 0.0,
            },
        )
        generated_sql = _extract_sql_candidate((response.get("message") or {}).get("content"))
        if not generated_sql:
            generation_messages.append(
                {
                    "role": "user",
                    "content": "Return the required JSON now. The sql value must start with SELECT.",
                }
            )
            response = await sync_to_async(client.chat, thread_sensitive=True)(
                model=model,
                messages=generation_messages,
                format=sql_format,
                options={"num_ctx": context_window, "temperature": 0.0},
            )
            generated_sql = _extract_sql_candidate(
                (response.get("message") or {}).get("content")
            )
        if not generated_sql:
            raise RuntimeError("Ollama did not return structured SQL after ChromaDB retrieval.")

        tool_context = ToolContext(
            user=vanna_user,
            conversation_id=str(session.pk),
            request_id=uuid4().hex,
            agent_memory=memory.agent_memory,
            metadata={
                "django_user_id": user.pk,
                "domain": session.domain.slug,
                "role": role,
            }
        )
        run_sql = RunSqlTool(
            sql_runner=DjangoSqlRunner(),
            file_system=NoopFileSystem(),
            custom_tool_description="Execute one governed read-only SELECT query.",
        )
        tool_result = await run_sql.execute(
            tool_context,
            RunSqlToolArgs(sql=generated_sql),
        )
        if not tool_result.success:
            raise RuntimeError(tool_result.error or tool_result.result_for_llm)
        rows = [
            {column: _json_value(value) for column, value in row.items()}
            for row in tool_result.metadata.get("results", [])
        ][:max_rows]

        summary_response = await sync_to_async(client.chat, thread_sensitive=True)(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize governed analytics results accurately and concisely. "
                        "Use the same language as the user's question. Do not invent values."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\nSQL: {governor.last_generated_sql}\n"
                        f"Rows ({len(rows)}): {json.dumps(rows[:50], ensure_ascii=False, default=str)}"
                    ),
                },
            ],
            options={"num_ctx": context_window, "temperature": temperature},
        )
        summary = str((summary_response.get("message") or {}).get("content") or "").strip()
        if not summary:
            summary = f"Vanna returned {len(rows)} row(s)."
        await sync_to_async(memory.remember_success, thread_sensitive=True)(
            question=question,
            sql=governor.last_generated_sql,
            summary=summary,
        )
        return {
            "sql": governor.last_effective_sql,
            "summary": summary,
            "data": rows,
            "chart": _chart_spec(question, rows),
            "followups": _followups(rows),
            "provider": "ollama_vanna",
            "model": model,
            "execution_mode": "chroma_rag_vanna_run_sql",
            "chroma_collection": memory.collection_name,
            "chroma_memories": len(retrieved),
            "chroma_synced": synced_documents,
        }
