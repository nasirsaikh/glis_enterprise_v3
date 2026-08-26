#!/usr/bin/env python3
"""Seed every GLIS-owned Django model with linked demonstration data.

Place this file beside ``manage.py`` and run::

    python seed_entire_project.py

The script is idempotent: running it again updates the same stable demo rows
instead of creating another copy. It runs migrations and the project's existing
``seed_demo_data`` command first, then fills the remaining operational tables.

Only GLIS-owned models are forced to contain demo rows. Runtime/credential
tables such as Django sessions, OAuth accounts and OAuth tokens are deliberately
left to Django/allauth and real identity providers.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "glis.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.contrib.sites.models import Site  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.accounts.models import AccountPolicy, UserProfile  # noqa: E402
from apps.ai.models import AIInteraction, AISettings, default_questions  # noqa: E402
from apps.cms.models import (  # noqa: E402
    AnimationPreset,
    ContentVersion,
    Page,
    PageSection,
    SiteSettings,
    ThemeSettings,
)
from apps.core.models import AuditLog, ConfigurationVersion  # noqa: E402
from apps.knowledge.models import Article, ArticleFeedback  # noqa: E402
from apps.orchestrator.models import (  # noqa: E402
    AIDomain,
    AnalysisSession,
    QueryAudit,
    VannaSettings,
)
from apps.tickets.models import (  # noqa: E402
    DynamicFieldSchema,
    DynamicForm,
    FormDataSource,
    Notification,
    RelatedTicket,
    SavedTicketView,
    Ticket,
    TicketEscalation,
    TicketShare,
)
from services.ticket_workflow import initialize_approval_workflow  # noqa: E402


CUSTOM_APP_LABELS = {
    "accounts",
    "ai",
    "cms",
    "core",
    "knowledge",
    "orchestrator",
    "tickets",
}


def one_or_create(model, lookup: dict, defaults: dict):
    """Update the first matching non-unique row, otherwise create it."""
    obj = model.objects.filter(**lookup).order_by("pk").first()
    if obj is None:
        return model.objects.create(**lookup, **defaults)
    for field, value in defaults.items():
        setattr(obj, field, value)
    obj.save()
    return obj


def seed_framework_configuration() -> None:
    Site.objects.update_or_create(
        pk=settings.SITE_ID,
        defaults={"domain": "localhost:8000", "name": "GLIS Local Portal"},
    )


def seed_accounts() -> dict[str, object]:
    User = get_user_model()
    users = {user.email: user for user in User.objects.filter(email__endswith="@glis.local")}
    required_emails = {
        "admin@glis.local",
        "ops.admin@glis.local",
        "manager@glis.local",
        "claims.agent@glis.local",
        "support.agent@glis.local",
        "customer@glis.local",
        "auditor@glis.local",
        "guest@glis.local",
    }
    missing = required_emails - users.keys()
    if missing:
        raise RuntimeError(f"Base seed did not create required users: {sorted(missing)}")

    profile_data = {
        "admin@glis.local": ("Platform Administration", "System Administrator", "+968 2400 0101"),
        "ops.admin@glis.local": ("Operations", "Operations Administrator", "+968 2400 0102"),
        "manager@glis.local": ("Service Operations", "Service Operations Manager", "+968 2400 0201"),
        "claims.agent@glis.local": ("Claims", "Claims Specialist", "+968 2400 0301"),
        "support.agent@glis.local": ("Customer Service", "Support Specialist", "+968 2400 0302"),
        "customer@glis.local": ("Customer", "Policyholder", "+968 9900 1001"),
        "auditor@glis.local": ("Assurance", "Internal Auditor", "+968 2400 0401"),
        "guest@glis.local": ("External", "Guest Requester", "+968 9900 1002"),
    }
    for email, (department, title, phone) in profile_data.items():
        profile = users[email].profile
        profile.department = department
        profile.job_title = title
        profile.phone = phone
        profile.organization = "Greenline Insurance Services"
        profile.bio = f"Demonstration profile for the {title.lower()} role."
        profile.email_notifications = True
        profile.browser_notifications = True
        profile.sidebar_mode = UserProfile.SidebarMode.MINI
        profile.save()

    manager = users["manager@glis.local"]
    for email in ("claims.agent@glis.local", "support.agent@glis.local"):
        profile = users[email].profile
        profile.reporting_manager = manager
        profile.save(update_fields=["reporting_manager", "updated_at"])

    default_group = Group.objects.filter(name="Guest").first()
    policy = AccountPolicy.load()
    policy.public_registration_enabled = True
    policy.default_external_role = UserProfile.Role.GUEST
    policy.default_external_group = default_group
    policy.allowed_email_domains = ["glis.local", "example.com"]
    policy.external_users_require_approval = False
    policy.guest_ticket_visibility = "own"
    policy.save()
    return users


def seed_cms(users: dict[str, object]) -> None:
    admin = users["admin@glis.local"]
    site = SiteSettings.load()
    site.organization_details = (
        "Bilingual insurance service orchestration for customers, providers, "
        "support teams and management."
    )
    site.social_links = {
        "linkedin": "https://www.linkedin.com/company/glis-demo",
        "x": "https://x.com/glis_demo",
    }
    site.save()

    theme = ThemeSettings.load()
    theme.primary = "#147A50"
    theme.primary_dark = "#0D5F3D"
    theme.default_theme = "system"
    theme.users_may_choose_theme = True
    theme.animations_enabled = True
    theme.save()

    page = Page.objects.get(slug="about")
    page.updated_by = admin
    page.save(update_fields=["updated_by", "updated_at"])
    animation = AnimationPreset.objects.filter(key="fade-up").first()
    sections = [
        (
            1,
            "content",
            "Our purpose",
            "هدفنا",
            "Make every insurance service request visible, accountable and easy to follow.",
            "جعل كل طلب خدمة تأمينية واضحاً ومسؤولاً وسهل المتابعة.",
            {"width": "narrow"},
        ),
        (
            2,
            "features",
            "Connected service teams",
            "فرق خدمة مترابطة",
            "Customers, providers, claims, finance and operations work from one governed record.",
            "يعمل العملاء ومقدمو الخدمة والمطالبات والمالية والعمليات من سجل موحد ومحكوم.",
            {"columns": 3, "icons": ["shield", "people", "graph"]},
        ),
        (
            3,
            "statistics",
            "Service transparency",
            "شفافية الخدمة",
            "Track ownership, approvals, SLA targets and turnaround time from submission to closure.",
            "تابع المسؤولية والموافقات وأهداف مستوى الخدمة ووقت الإنجاز من التقديم حتى الإغلاق.",
            {"source": "cms_statistics"},
        ),
        (
            4,
            "cta",
            "Ready to submit a request?",
            "هل أنت مستعد لتقديم طلب؟",
            "Use the guided ticket form and attach the required documents securely.",
            "استخدم نموذج التذكرة الموجّه وأرفق المستندات المطلوبة بأمان.",
            {"label": "Submit a request", "url": "/portal/tickets/create/1/"},
        ),
    ]
    for order, section_type, title_en, title_ar, content_en, content_ar, config in sections:
        section = PageSection.objects.filter(page=page, order=order).first()
        values = {
            "section_type": section_type,
            "title_en": title_en,
            "title_ar": title_ar,
            "content_en": content_en,
            "content_ar": content_ar,
            "settings": config,
            "is_visible": True,
            "animation": animation,
            "animation_duration_ms": 500,
            "animation_delay_ms": (order - 1) * 80,
            "animate_once": True,
        }
        if section is None:
            PageSection.objects.create(page=page, order=order, **values)
        else:
            for field, value in values.items():
                setattr(section, field, value)
            section.save()

    ContentVersion.objects.update_or_create(
        page=page,
        version=1,
        defaults={
            "snapshot": {
                "slug": page.slug,
                "title_en": page.title_en,
                "title_ar": page.title_ar,
                "state": page.state,
                "section_orders": [1, 2, 3, 4],
            },
            "created_by": admin,
            "change_note": "Initial seeded bilingual content",
        },
    )


def seed_dynamic_forms(users: dict[str, object]) -> None:
    admin = users["admin@glis.local"]
    form = DynamicForm.objects.get(key="complaint")
    version = form.active_version or form.versions.order_by("-version").first()
    if version is None:
        raise RuntimeError("Complaint form has no form version after base seed.")

    registry_rows = [
        (
            "complaint_categories",
            "Complaint categories",
            "complaint_categories",
            {"cache_seconds": 300, "value_key": "value", "label_key": "label"},
        ),
        (
            "complaint_locations",
            "Complaint locations",
            "complaint_locations",
            {"cache_seconds": 3600, "value_key": "value", "label_key": "label"},
        ),
        (
            "complaint_reasons",
            "Complaint reasons",
            "complaint_reasons",
            {"cache_seconds": 3600, "value_key": "value", "label_key": "label"},
        ),
        (
            "claim_lookup",
            "Claim lookup",
            "claim_lookup",
            {"requires_parameter": "claim_number", "maximum_results": 20},
        ),
    ]
    allowed_roles = [
        "super_admin",
        "admin",
        "project_manager",
        "support_agent",
        "requester",
        "guest",
    ]
    for key, label, handler, metadata in registry_rows:
        FormDataSource.objects.update_or_create(
            key=key,
            defaults={
                "label": label,
                "handler": handler,
                "metadata": metadata,
                "allowed_roles": allowed_roles,
                "is_active": True,
            },
        )

    for order, field in enumerate(version.schema.get("fields", []), 1):
        field_name = field.get("name")
        if not field_name:
            continue
        configuration = {
            key: value
            for key, value in field.items()
            if key not in {"name", "label", "label_ar", "control", "required"}
        }
        DynamicFieldSchema.objects.update_or_create(
            form_version=version,
            name=field_name,
            defaults={
                "label_en": field.get("label", field_name.replace("_", " ").title()),
                "label_ar": field.get("label_ar", ""),
                "control": field.get("control", "text"),
                "required": bool(field.get("required", False)),
                "order": order,
                "configuration": configuration,
            },
        )

    ConfigurationVersion.objects.update_or_create(
        key="ticket-intake-form",
        version=1,
        defaults={
            "state": "published",
            "payload": {
                "form_key": form.key,
                "form_version": version.version,
                "field_count": len(version.schema.get("fields", [])),
                "attachment_policy": version.schema.get("attachments", {}),
            },
            "validation_errors": [],
            "change_note": "Initial seeded ticket intake configuration",
            "created_by": admin,
            "published_at": timezone.now(),
        },
    )


def seed_ticket_operations(users: dict[str, object]) -> None:
    admin = users["admin@glis.local"]
    manager = users["manager@glis.local"]
    customer = users["customer@glis.local"]
    auditor = users["auditor@glis.local"]

    tickets = list(Ticket.objects.select_related("category", "sla_policy").order_by("pk"))
    if len(tickets) < 2:
        raise RuntimeError("At least two tickets are required after base seed.")
    first, second = tickets[0], tickets[1]

    RelatedTicket.objects.update_or_create(
        source=first,
        target=second,
        defaults={"relationship": "similar"},
    )
    RelatedTicket.objects.update_or_create(
        source=second,
        target=first,
        defaults={"relationship": "references"},
    )

    one_or_create(
        SavedTicketView,
        {"owner": manager, "name": "My team's open tickets"},
        {
            "filters": {
                "status__in": ["new", "open", "in_progress"],
                "scope": "managed_groups",
                "ordering": "resolution_due_at",
            },
            "is_default": True,
        },
    )
    one_or_create(
        SavedTicketView,
        {"owner": auditor, "name": "SLA exceptions"},
        {
            "filters": {"sla_state": "overdue", "visibility": "standard"},
            "is_default": False,
        },
    )

    share = one_or_create(
        TicketShare,
        {"ticket": first, "created_by": admin, "recipient": auditor},
        {"expires_at": timezone.now() + timedelta(days=30), "is_active": True},
    )

    complaint_ticket = (
        Ticket.objects.filter(category__code="COMPLAINT")
        .select_related("category__approval_workflow")
        .order_by("pk")
        .first()
    )
    if (
        complaint_ticket
        and complaint_ticket.category.approval_workflow_id
        and not complaint_ticket.approvals.exists()
    ):
        initialize_approval_workflow(complaint_ticket)

    overdue = (
        Ticket.objects.exclude(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED])
        .filter(sla_policy__isnull=False)
        .select_related("sla_policy")
        .order_by("resolution_due_at")
        .first()
    )
    if overdue:
        rule = overdue.sla_policy.escalation_levels.order_by("level").first()
        if rule:
            escalation, _ = TicketEscalation.objects.update_or_create(
                ticket=overdue,
                rule=rule,
                defaults={
                    "message": "Seeded SLA escalation: manager review is required.",
                },
            )
            escalation.escalated_to_users.set([manager])
            Notification.objects.update_or_create(
                user=manager,
                ticket=overdue,
                kind="sla",
                title=f"SLA escalation: {overdue.reference}",
                defaults={
                    "body": "The ticket requires management review because its SLA target was exceeded.",
                    "link": f"/portal/tickets/{overdue.reference}/",
                },
            )

    Notification.objects.update_or_create(
        user=auditor,
        ticket=first,
        kind="info",
        title=f"Ticket shared: {first.reference}",
        defaults={
            "body": "A ticket was shared with you for review.",
            "link": f"/portal/tickets/{first.reference}/?share={share.token}",
        },
    )

    # Attach the published schema to seeded ticket data for reporting examples.
    form = DynamicForm.objects.get(key="complaint")
    for ticket in Ticket.objects.filter(category=form.category).select_related("dynamic_data"):
        if hasattr(ticket, "dynamic_data"):
            data = ticket.dynamic_data
            data.form_version = form.active_version
            data.reporting_values = {
                "category": ticket.category.name_en,
                "priority": ticket.priority,
                "status": ticket.status,
                "assigned": bool(ticket.assignee_id),
            }
            data.save()

    if not AuditLog.objects.filter(
        action="seed.completed",
        object_type=first._meta.label,
        object_id=str(first.pk),
    ).exists():
        AuditLog.record(
            actor=admin,
            action="seed.completed",
            instance=first,
            summary="Entire-project demonstration seed applied",
            changes={
                "ticket_reference": first.reference,
                "custom_apps": sorted(CUSTOM_APP_LABELS),
            },
        )

    # Keep one read and one unread notification for UI testing.
    read_notification = Notification.objects.filter(user=customer).order_by("pk").first()
    if read_notification and read_notification.read_at is None:
        read_notification.read_at = timezone.now() - timedelta(hours=2)
        read_notification.save(update_fields=["read_at", "updated_at"])


def seed_knowledge(users: dict[str, object]) -> None:
    customer = users["customer@glis.local"]
    auditor = users["auditor@glis.local"]
    articles = list(Article.objects.order_by("pk"))
    if not articles:
        raise RuntimeError("Base seed did not create knowledge articles.")

    tickets = Ticket.objects.select_related("project", "product", "category").order_by("pk")
    sample_ticket = tickets.first()
    if sample_ticket:
        for article in articles:
            article.projects.add(sample_ticket.project)
            article.products.add(sample_ticket.product)
            article.categories.add(sample_ticket.category)

    ArticleFeedback.objects.update_or_create(
        article=articles[0],
        user=customer,
        defaults={
            "helpful": True,
            "comment": "The checklist made the document requirements clear.",
        },
    )
    if len(articles) > 1:
        ArticleFeedback.objects.update_or_create(
            article=articles[1],
            user=auditor,
            defaults={
                "helpful": False,
                "comment": "Add an example showing where the SLA indicator appears.",
            },
        )


def seed_ai_and_orchestrator(users: dict[str, object]) -> None:
    admin = users["admin@glis.local"]
    manager = users["manager@glis.local"]
    ticket = Ticket.objects.order_by("pk").first()
    domain = AIDomain.objects.get(slug="service-operations")

    domain.allowed_groups.set(
        Group.objects.filter(
            name__in=["Admin", "Project Manager", "Support Agent", "Viewer"]
        )
    )

    ai_settings = AISettings.load()
    ai_settings.provider = "mock"
    ai_settings.system_prompt = (
        "Assist with insurance service requests. Enforce role visibility, do not expose "
        "sensitive fields, and never make final coverage, claim or approval decisions."
    )
    ai_settings.intake_questions = default_questions()
    ai_settings.is_enabled = True
    ai_settings.save()

    one_or_create(
        AIInteraction,
        {"ticket": ticket, "purpose": "intake_recommendation"},
        {
            "user": customer_or_admin(users),
            "provider": "mock",
            "request_summary": {
                "subject": ticket.subject if ticket else "Demo request",
                "requested_capabilities": ["category", "priority", "knowledge"],
            },
            "response": {
                "suggested_priority": ticket.priority if ticket else "medium",
                "suggested_category": ticket.category.name_en if ticket else "General service request",
                "reason": "Seeded safe demonstration recommendation.",
            },
            "confidence": "0.820",
            "duration_ms": 146,
            "succeeded": True,
            "error_code": "",
        },
    )

    vanna = VannaSettings.load()
    vanna.provider = "ollama_vanna"
    vanna.endpoint = "http://127.0.0.1:11434"
    vanna.allow_sql_execution = True
    vanna.require_human_review_for_training = True
    vanna.chroma_top_k = 8
    vanna.chroma_auto_train_successful_queries = True
    vanna.is_enabled = True
    vanna.save()

    session = AnalysisSession.objects.filter(
        user=manager,
        domain=domain,
        title="Service operations overview",
    ).first()
    session_values = {
        "context": {
            "date_range": "last_30_days",
            "permitted_project_ids": list(manager.ticket_projects.values_list("pk", flat=True)),
            "language": "en",
        },
        "is_active": True,
    }
    if session is None:
        session = AnalysisSession.objects.create(
            user=manager,
            domain=domain,
            title="Service operations overview",
            **session_values,
        )
    else:
        session.context = session_values["context"]
        session.is_active = True
        session.save()

    one_or_create(
        QueryAudit,
        {"session": session, "question": "Show open tickets by priority"},
        {
            "generated_sql": (
                "SELECT priority, COUNT(*) AS ticket_count FROM tickets_ticket "
                "WHERE status NOT IN ('resolved', 'closed') GROUP BY priority"
            ),
            "summary": "Open workload grouped by priority with resolved and closed tickets excluded.",
            "result_preview": [
                {"priority": "critical", "ticket_count": 2},
                {"priority": "high", "ticket_count": 4},
                {"priority": "medium", "ticket_count": 8},
                {"priority": "low", "ticket_count": 3},
            ],
            "chart_spec": {
                "type": "bar",
                "x": "priority",
                "y": "ticket_count",
                "title": "Open tickets by priority",
            },
            "response_metadata": {
                "provider": "ollama_vanna",
                "execution_mode": "chroma_rag_vanna_run_sql",
                "chroma_memories": 8,
                "followups": ["Which categories have the most overdue tickets?", "Compare first response TAT by month"],
            },
            "status": "completed",
            "row_count": 4,
            "duration_ms": 84,
            "error_code": "",
        },
    )
    one_or_create(
        QueryAudit,
        {"session": session, "question": "Which categories have the most overdue tickets?"},
        {
            "generated_sql": "SELECT category_id, COUNT(*) AS overdue_count FROM tickets_ticket WHERE resolution_due_at < CURRENT_TIMESTAMP AND status NOT IN ('resolved', 'closed') GROUP BY category_id",
            "summary": "Overdue open workload grouped by service category.",
            "result_preview": [
                {"category": "Claim status", "overdue_count": 5},
                {"category": "Payment inquiry", "overdue_count": 3},
                {"category": "Provider onboarding", "overdue_count": 2},
            ],
            "chart_spec": {"type": "bar", "x": "category", "y": "overdue_count", "title": "Overdue tickets by category"},
            "response_metadata": {"provider": "ollama_vanna", "execution_mode": "chroma_rag_vanna_run_sql", "chroma_memories": 8, "followups": ["Show the owners of these overdue tickets"]},
            "status": "completed",
            "row_count": 3,
            "duration_ms": 91,
            "error_code": "",
        },
    )
    one_or_create(
        QueryAudit,
        {"session": session, "question": "Compare first response TAT by month"},
        {
            "generated_sql": "SELECT strftime('%Y-%m', created_at) AS month, AVG((julianday(first_responded_at) - julianday(created_at)) * 24) AS response_hours FROM tickets_ticket WHERE first_responded_at IS NOT NULL GROUP BY strftime('%Y-%m', created_at)",
            "summary": "Average first-response turnaround time by month for tickets with a recorded first response.",
            "result_preview": [{"month": "2026-06", "response_hours": 5.8}, {"month": "2026-07", "response_hours": 4.6}, {"month": "2026-08", "response_hours": 3.9}],
            "chart_spec": {"type": "line", "x": "month", "y": "response_hours", "title": "First response TAT by month"},
            "response_metadata": {"provider": "ollama_vanna", "execution_mode": "chroma_rag_vanna_run_sql", "chroma_memories": 7, "followups": ["Break this down by support group"]},
            "status": "completed",
            "row_count": 3,
            "duration_ms": 77,
            "error_code": "",
        },
    )

    ConfigurationVersion.objects.update_or_create(
        key="vanna-business-context",
        version=1,
        defaults={
            "state": "published",
            "payload": {
                "domain": domain.slug,
                "rules": list(domain.business_rules.values_list("name", flat=True)),
                "allowed_tables": domain.allowed_tables,
                "sql_execution_enabled": False,
            },
            "validation_errors": [],
            "change_note": "Initial seeded Vanna domain configuration",
            "created_by": admin,
            "published_at": timezone.now(),
        },
    )


def customer_or_admin(users: dict[str, object]):
    return users.get("customer@glis.local") or users["admin@glis.local"]


def verify_every_custom_model() -> list[tuple[str, int]]:
    counts: list[tuple[str, int]] = []
    empty: list[str] = []
    for model in apps.get_models():
        if model._meta.app_label not in CUSTOM_APP_LABELS or model._meta.proxy:
            continue
        count = model.objects.count()
        counts.append((model._meta.label, count))
        if count == 0:
            empty.append(model._meta.label)
    if empty:
        raise RuntimeError(
            "The seed finished, but these GLIS tables are still empty: " + ", ".join(empty)
        )
    return sorted(counts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed every GLIS application table with linked demo data."
    )
    parser.add_argument(
        "--no-migrate",
        action="store_true",
        help="Skip the automatic migrate step.",
    )
    parser.add_argument(
        "--allow-non-debug",
        action="store_true",
        help="Allow execution when DJANGO_DEBUG=False (use only on a disposable database).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not settings.DEBUG and not args.allow_non_debug:
        print(
            "Refusing to seed while DJANGO_DEBUG=False. Use a disposable development "
            "database or pass --allow-non-debug explicitly.",
            file=sys.stderr,
        )
        return 2

    print("1/4 Applying migrations…")
    if not args.no_migrate:
        call_command("migrate", interactive=False, verbosity=0)
    else:
        print("    skipped (--no-migrate)")

    print("2/4 Seeding the base GLIS catalog, users, workflows and tickets…")
    call_command("seed_demo_data", verbosity=0)

    print("3/4 Seeding every remaining GLIS operational table…")
    with transaction.atomic():
        seed_framework_configuration()
        users = seed_accounts()
        seed_cms(users)
        seed_dynamic_forms(users)
        seed_ticket_operations(users)
        seed_knowledge(users)
        seed_ai_and_orchestrator(users)

    print("4/4 Verifying custom model coverage…")
    counts = verify_every_custom_model()
    width = max(len(label) for label, _ in counts)
    for label, count in counts:
        print(f"    {label:<{width}}  {count:>5}")

    print("\nEntire-project seed completed successfully.")
    print("Demo admin: admin@glis.local / DemoAdmin123!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
