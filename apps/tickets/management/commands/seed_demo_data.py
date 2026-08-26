from datetime import timedelta
from itertools import cycle
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from allauth.account.models import EmailAddress
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import AccountPolicy, UserProfile
from apps.ai.models import AISettings, default_questions
from apps.cms.models import AnimationPreset, HeroSection, NavigationItem, Page, Service, ServiceCategory, SiteSettings, Statistic, Testimonial, ThemeSettings
from apps.core.models import ModuleRegistry
from apps.knowledge.models import Article, KnowledgeCategory
from apps.orchestrator.models import (
    AIDomain, BusinessRule, ColumnPolicy, ColumnRolePolicy, DataSource,
    RowAccessPolicy, SuggestedPrompt, TablePolicy, TrainingCandidate,
    TrainingPrompt, VannaSettings,
)
from apps.tickets.models import (
    ApprovalStep, ApprovalWorkflow, Category, DynamicForm, DynamicFormVersion,
    Notification, Product, Project, SLAEscalationRule, SLAPolicy, SupportGroup,
    Ticket, TicketAttachment, TicketComment, TicketDynamicData, TicketEvent,
)
from services.ticket_workflow import initialize_approval_workflow


PASSWORD = "DemoAdmin123!"


COMPLAINT_SCHEMA = {
    "api_section": "complaintDetail",
    "api_defaults": {"sspId": 0},
    "security": {"datasource_policy": "registry_only", "raw_sql_execution": False},
    "attachments": {
        "enabled": True, "max_size_mb": 10,
        "allowed_extensions": [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"],
        "items": [
            {"name": "civil_id", "label": "Civil ID", "control": "file", "required": True, "multiple": False, "min_count": 1, "max_count": 1, "max_size_mb": 10, "allowed_extensions": [".pdf", ".jpg", ".jpeg", ".png"], "required_message": "Please attach the Civil ID.", "help_text": "Upload Civil ID as PDF or image.", "restricted": True},
            {"name": "policy_copy", "label": "Policy Copy", "control": "file", "required": True, "multiple": False, "min_count": 1, "max_count": 1, "max_size_mb": 10, "allowed_extensions": [".pdf", ".jpg", ".jpeg", ".png"], "required_message": "Please attach the Policy Copy.", "help_text": "Upload the relevant policy copy."},
            {"name": "complaint_evidence", "label": "Complaint Evidence", "control": "file", "required": False, "multiple": True, "min_count": 0, "max_count": 3, "max_size_mb": 10, "allowed_extensions": [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"], "help_text": "Optional emails, letters, screenshots or supporting evidence."},
        ],
    },
    "fields": [
        {"name": "category_id", "label": "Category Name", "label_ar": "فئة الشكوى", "control": "select", "required": True, "searchable": True, "api_name": "categoryId", "api_type": "int", "data_source": {"type": "registry", "registry": "complaint_categories"}},
        {"name": "complainant_name", "label": "Complainant Name", "label_ar": "اسم مقدم الشكوى", "control": "text", "required": True, "api_name": "complainantName", "validation": {"max_length": 100}},
        {"name": "complainant_contact_no", "label": "Contact Number", "label_ar": "رقم الاتصال", "control": "tel", "required": True, "api_name": "complainantContactNo", "validation": {"min_length": 5, "max_length": 30}},
        {"name": "claim_number", "label": "Policy/Claim Number", "label_ar": "رقم الوثيقة أو المطالبة", "control": "text", "required": True, "api_name": "policyOrClaimNumber", "lookup": {"registry": "claim_lookup", "required_match": True, "result_map": {"claim_number": "claim_number", "policy_number": "policy_number", "insured_name": "insured_name", "product": "product", "nature_of_claim": "nature_of_claim"}}},
        {"name": "complaint_date", "label": "Complaint Date", "label_ar": "تاريخ الشكوى", "control": "date", "required": True, "default": {"source": "system", "value": "today"}, "editable": False, "validation": {"max": "today"}, "disabled_reason": "Complaint Date is automatically set to today's date."},
        {"name": "location_id", "label": "Complaint Location", "label_ar": "موقع الشكوى", "control": "select", "required": True, "api_name": "locationId", "data_source": {"type": "registry", "registry": "complaint_locations"}},
        {"name": "reason_id", "label": "Complaint Reason", "label_ar": "سبب الشكوى", "control": "select", "required": True, "api_name": "reasonId", "data_source": {"type": "registry", "registry": "complaint_reasons"}},
        {"name": "receiving_source", "label": "Receiving Source", "label_ar": "مصدر الاستلام", "control": "select", "required": True, "default": {"source": "literal", "value": 5}, "editable": False, "data_source": {"type": "enum", "options": [{"value": 5, "label": "Website Form"}]}},
        {"name": "description", "label": "Description", "label_ar": "الوصف", "control": "richtext", "required": True, "api_name": "description", "validation": {"min_length": 5, "max_length": 2000000}},
        {"name": "beneficiary_account", "label": "Beneficiary Account (if relevant)", "label_ar": "حساب المستفيد", "control": "text", "required": False, "sensitive": True, "visible_to_roles": ["admin", "project_manager", "support_agent", "requester", "guest"]},
    ],
}


class Command(BaseCommand):
    help = "Seed a realistic, idempotent GLIS development environment. Never use the demo passwords in production."

    def handle(self, *args, **options):
        self.stdout.write("Seeding GLIS demo data…")
        users = self.seed_users_and_roles()
        support_groups = self.seed_support_groups(users)
        projects, products, categories = self.seed_catalog(support_groups, users)
        self.seed_forms_and_sla(projects, products, categories)
        self.seed_orchestrator(users)
        self.seed_cms()
        self.seed_knowledge(users, projects, products, categories)
        self.seed_tickets(users, support_groups, projects, products, categories)
        self.stdout.write(self.style.SUCCESS("Demo data ready. Sign in with admin@glis.local / DemoAdmin123!"))

    def seed_users_and_roles(self):
        User = get_user_model()
        specs = [
            ("admin@glis.local", "Amal", "Rahman", UserProfile.Role.SUPER_ADMIN, True, True),
            ("ops.admin@glis.local", "Omar", "Salim", UserProfile.Role.ADMIN, True, False),
            ("manager@glis.local", "Maha", "Al Harthy", UserProfile.Role.PROJECT_MANAGER, False, False),
            ("claims.agent@glis.local", "Noura", "Khalid", UserProfile.Role.SUPPORT_AGENT, False, False),
            ("support.agent@glis.local", "Fahad", "Ali", UserProfile.Role.SUPPORT_AGENT, False, False),
            ("customer@glis.local", "Sara", "Ahmed", UserProfile.Role.REQUESTER, False, False),
            ("auditor@glis.local", "Yusuf", "Hassan", UserProfile.Role.VIEWER, False, False),
            ("guest@glis.local", "Guest", "Customer", UserProfile.Role.GUEST, False, False),
        ]
        users = {}
        for email, first, last, role, staff, superuser in specs:
            user, created = User.objects.get_or_create(username=email, defaults={"email": email, "first_name": first, "last_name": last, "is_staff": staff, "is_superuser": superuser})
            user.email, user.first_name, user.last_name, user.is_staff, user.is_superuser = email, first, last, staff, superuser
            if created or not user.check_password(PASSWORD):
                user.set_password(PASSWORD)
            user.save()
            EmailAddress.objects.update_or_create(user=user, email=email, defaults={"verified": True, "primary": True})
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role, profile.is_external, profile.is_approved = role, role == UserProfile.Role.GUEST, True
            profile.sidebar_mode = UserProfile.SidebarMode.MINI
            profile.save()
            users[role if role not in users else email] = user

        manager = get_user_model().objects.get(email="manager@glis.local")
        for email in ("claims.agent@glis.local", "support.agent@glis.local"):
            profile = get_user_model().objects.get(email=email).profile
            profile.reporting_manager = manager
            profile.department = "Service Operations"
            profile.job_title = "Support Agent"
            profile.save(update_fields=["reporting_manager", "department", "job_title", "updated_at"])

        role_permissions = {
            UserProfile.Role.ADMIN: ["view_all", "assign", "export", "view_sensitive", "view_internal_notes", "manage_projects", "manage_products", "manage_categories", "manage_forms", "manage_sla", "view_audit"],
            UserProfile.Role.PROJECT_MANAGER: ["view_group", "assign", "export", "view_internal_notes"],
            UserProfile.Role.SUPPORT_AGENT: ["view_group", "view_internal_notes", "change_ticket", "add_ticketcomment"],
            UserProfile.Role.REQUESTER: ["view_own", "add_ticket"],
            UserProfile.Role.VIEWER: ["view_group"],
            UserProfile.Role.GUEST: ["view_own", "add_ticket"],
        }
        for role, codenames in role_permissions.items():
            group, _ = Group.objects.get_or_create(name=role.replace("_", " ").title())
            permissions = Permission.objects.filter(codename__in=codenames)
            group.permissions.set(permissions)
            for user in User.objects.filter(profile__role=role):
                user.groups.add(group)
        AccountPolicy.load()
        return users

    def seed_support_groups(self, users):
        claims_agent = get_user_model().objects.get(email="claims.agent@glis.local")
        support_agent = get_user_model().objects.get(email="support.agent@glis.local")
        manager = get_user_model().objects.get(email="manager@glis.local")
        groups = {}
        for name, code, member in [
            ("Claims", "claims", claims_agent), ("Underwriting", "underwriting", manager),
            ("Finance", "finance", manager), ("Operations", "operations", support_agent),
            ("Customer Service", "customer-service", support_agent), ("IT Support", "it-support", support_agent),
        ]:
            auth_group, _ = Group.objects.get_or_create(name=f"Support · {name}")
            obj, _ = SupportGroup.objects.update_or_create(code=code, defaults={"name": name, "auth_group": auth_group, "can_view_sensitive": code in {"claims", "finance"}, "can_view_restricted_attachments": code == "claims", "can_assign_group_tickets": member == manager, "can_access_reports": member == manager})
            obj.members.add(member, manager)
            obj.managers.add(manager)
            groups[code] = obj
        return groups

    def seed_catalog(self, groups, users):
        project_specs = [("CUS", "Customer Services", "خدمات العملاء", groups["customer-service"]), ("CLM", "Claims & Benefits", "المطالبات والمنافع", groups["claims"]), ("FIN", "Finance & Payments", "المالية والمدفوعات", groups["finance"]), ("OPS", "Provider & Operations", "مقدمو الخدمة والعمليات", groups["operations"])]
        projects = {}
        for code, en, ar, group in project_specs:
            project, _ = Project.objects.update_or_create(code=code, defaults={"name_en": en, "name_ar": ar, "is_active": True})
            project.groups.add(group)
            project.members.add(users[UserProfile.Role.PROJECT_MANAGER])
            projects[code] = project
        product_specs = [("CUS", "SERVICE", "Customer Care", "العناية بالعملاء"), ("CLM", "MOTOR", "Motor Claims", "مطالبات المركبات"), ("CLM", "HEALTH", "Health Benefits", "المنافع الصحية"), ("FIN", "PAY", "Payments", "المدفوعات"), ("OPS", "PROVIDER", "Provider Services", "خدمات مقدمي الخدمة")]
        products = {}
        for project_code, code, en, ar in product_specs:
            product, _ = Product.objects.update_or_create(project=projects[project_code], code=code, defaults={"name_en": en, "name_ar": ar, "is_active": True})
            products[code] = product
        category_specs = [
            ("SERVICE", "COMPLAINT", "Submit a complaint", "تقديم شكوى", "high", groups["customer-service"]),
            ("SERVICE", "GENERAL", "General service request", "طلب خدمة عام", "medium", groups["customer-service"]),
            ("MOTOR", "CLAIM-STATUS", "Motor claim status", "حالة مطالبة مركبة", "medium", groups["claims"]),
            ("MOTOR", "CLAIM-DOCS", "Claim document support", "دعم مستندات المطالبة", "high", groups["claims"]),
            ("HEALTH", "PREAUTH", "Pre-authorization support", "دعم الموافقة المسبقة", "critical", groups["claims"]),
            ("PAY", "PAYMENT", "Claim payment inquiry", "استفسار عن دفعة مطالبة", "high", groups["finance"]),
            ("PROVIDER", "EMPANEL", "Provider empanelment", "ضم مقدم خدمة", "medium", groups["operations"]),
        ]
        categories = {}
        for product_code, code, en, ar, priority, group in category_specs:
            default_user = group.members.filter(profile__role=UserProfile.Role.SUPPORT_AGENT).first()
            category, _ = Category.objects.update_or_create(product=products[product_code], code=code, defaults={"name_en": en, "name_ar": ar, "default_priority": priority, "default_group": group, "default_user": default_user, "auto_close_days": 7, "reopen_allowed_days": 14, "send_initial_email": True, "send_update_email": True, "is_active": True})
            category.default_groups.add(group)
            categories[code] = category
        return projects, products, categories

    def seed_forms_and_sla(self, projects, products, categories):
        workflow, _ = ApprovalWorkflow.objects.update_or_create(name="Complaint management approval", defaults={"description": "Dynamic two-level approval seeded for demonstration.", "is_active": True})
        manager = get_user_model().objects.get(email="manager@glis.local")
        admin_user = get_user_model().objects.get(email="ops.admin@glis.local")
        step1, _ = ApprovalStep.objects.update_or_create(workflow=workflow, sequence=1, defaults={"name": "Service manager review", "approvals_required": 1, "escalation_after_hours": 8})
        step1.approver_users.set([manager])
        step2, _ = ApprovalStep.objects.update_or_create(workflow=workflow, sequence=2, defaults={"name": "Operations approval", "approvals_required": 1, "escalation_after_hours": 24})
        step2.approver_users.set([admin_user])
        categories["COMPLAINT"].approval_workflow = workflow
        categories["COMPLAINT"].required_documents = COMPLAINT_SCHEMA["attachments"]["items"]
        categories["COMPLAINT"].save(update_fields=["approval_workflow", "required_documents", "updated_at"])
        form, _ = DynamicForm.objects.update_or_create(key="complaint", defaults={"name_en": "Complaint form", "name_ar": "نموذج الشكوى", "project": projects["CUS"], "product": products["SERVICE"], "category": categories["COMPLAINT"], "is_active": True})
        version, _ = DynamicFormVersion.objects.update_or_create(form=form, version=1, defaults={"state": "published", "schema": COMPLAINT_SCHEMA, "published_at": timezone.now(), "change_note": "Secure registry-based version of supplied complaint configuration"})
        form.active_version = version
        form.save(update_fields=["active_version"])
        for category in categories.values():
            for priority, response, resolution in [("low", 480, 2880), ("medium", 240, 1440), ("high", 60, 480), ("critical", 15, 120)]:
                policy, _ = SLAPolicy.objects.update_or_create(category=category, priority=priority, defaults={"name": f"{category.name_en} · {priority.title()}", "project": category.product.project, "first_response_minutes": response, "resolution_minutes": resolution, "is_active": True})
                manager = get_user_model().objects.get(email="manager@glis.local")
                escalation, _ = SLAEscalationRule.objects.update_or_create(policy=policy, level=1, defaults={"trigger_after_minutes": 0, "include_assignee_reporting_manager": True, "notification_message": "The resolution SLA has been breached; manager action is required.", "is_active": True})
                escalation.target_users.add(manager)
        AISettings.load()

    def seed_orchestrator(self, users):
        source, _ = DataSource.objects.update_or_create(name="GLIS Demo Warehouse", defaults={"engine": "mssql", "host": "sqlserver.internal", "port": 1433, "database_name": "GLIS_Analytics", "credential_env_prefix": "GLIS_ANALYTICS_DB", "is_read_only": True, "is_active": True})
        domain, _ = AIDomain.objects.update_or_create(slug="service-operations", defaults={"name": "Service Operations", "description": "Ticket, SLA, assignment and approval analytics.", "collection_name": "glis_service_operations", "schema_context": "Tickets join Projects, Products, Categories, Support Groups and SLA policies by reviewed keys.", "allowed_tables": ["tickets_ticket", "tickets_project", "tickets_product", "tickets_category", "tickets_slapolicy"], "max_rows": 1000, "is_active": True})
        domain.data_sources.add(source)
        for priority, name, text, sql_hint in [
            (10, "Open ticket definition", "Open workload excludes Resolved and Closed statuses.", "status NOT IN ('resolved','closed')"),
            (20, "SLA breach definition", "A ticket is overdue when resolution_due_at is earlier than the current timestamp and status is not Resolved or Closed.", "resolution_due_at < CURRENT_TIMESTAMP"),
            (30, "TAT definition", "First response TAT is first_responded_at minus created_at; resolution TAT is resolved_at minus created_at.", "Use duration in hours and never divide by zero."),
        ]:
            BusinessRule.objects.update_or_create(domain=domain, name=name, defaults={"priority": priority, "rule_text": text, "sql_guidance": sql_hint, "is_active": True})
        for table in domain.allowed_tables:
            TablePolicy.objects.update_or_create(domain=domain, table_name=table, defaults={"access": "allow", "allowed_roles": ["super_admin", "admin", "project_manager", "support_agent", "viewer"]})
        email_policy, _ = ColumnPolicy.objects.update_or_create(domain=domain, table_name="auth_user", column_name="email", defaults={"sensitivity": "personal", "default_access": "mask", "mask_pattern": "first-character + domain"})
        ColumnRolePolicy.objects.update_or_create(column_policy=email_policy, role="admin", defaults={"access": "allow"})
        RowAccessPolicy.objects.update_or_create(domain=domain, name="Project and support-group scope", defaults={"table_name": "tickets_ticket", "predicate_template": "project_id IN {permitted_project_ids} OR group_id IN {permitted_group_ids}", "allowed_roles": ["project_manager", "support_agent"], "is_active": True})
        for order, prompt in enumerate(["Show open tickets by status and priority", "Which categories have the highest overdue tickets?", "Compare first response and resolution TAT", "Show tickets assigned to each staff member"], 1):
            SuggestedPrompt.objects.update_or_create(domain=domain, text_en=prompt, defaults={"order": order, "is_active": True})
        TrainingPrompt.objects.update_or_create(domain=domain, name="Insurance SQL generation", prompt_type="sql_generation", version=1, defaults={"content": "Generate read-only, parameterized SQL. Apply domain business rules and every table, column and row policy. Use NULLIF for risky denominators and cap result rows.", "is_active": True})
        TrainingCandidate.objects.update_or_create(domain=domain, kind="question_sql", question="Show open tickets by priority", defaults={"sql": "SELECT priority, COUNT(*) AS tickets FROM tickets_ticket WHERE status NOT IN ('resolved','closed') GROUP BY priority", "status": "approved", "created_by": users[UserProfile.Role.SUPER_ADMIN]})
        vanna = VannaSettings.load()
        vanna.provider = "ollama_vanna"
        vanna.endpoint = "http://127.0.0.1:11434"
        vanna.allow_sql_execution = True
        vanna.chroma_top_k = 8
        vanna.chroma_auto_train_successful_queries = True
        vanna.is_enabled = True
        vanna.save()

    def seed_cms(self):
        SiteSettings.load(); ThemeSettings.load(); HeroSection.load()
        for key, label, css in [("none", "None", ""), ("fade-up", "Fade up", "fade-up"), ("slide-left", "Slide left", "slide-left"), ("scale-in", "Scale in", "scale-in"), ("gentle-lift", "Gentle hover lift", "gentle-lift")]:
            AnimationPreset.objects.update_or_create(key=key, defaults={"label": label, "css_class": css})
        nav = [
            ("Home", "الرئيسية", "public:home", "", 10),
            ("About GLIS", "عن جرين لاين", "public:home", "#about", 20),
            ("Services", "الخدمات", "public:home", "#services", 30),
            ("Insurance Solutions", "حلول التأمين", "public:home", "#solutions", 40),
            ("Knowledge Base", "قاعدة المعرفة", "knowledge:list", "", 50),
            ("Contact", "تواصل معنا", "public:home", "#contact", 60),
        ]
        for en, ar, route_name, url, order in nav:
            NavigationItem.objects.update_or_create(label_en=en, location="header", defaults={"label_ar": ar, "route_name": route_name, "route_arguments": [], "url": url, "order": order, "is_visible": True})
        portal_guide, _ = Page.objects.update_or_create(
            slug="portal-user-guide",
            defaults={
                "title_en": "Portal user guide",
                "title_ar": "دليل مستخدم البوابة",
                "summary_en": "How to submit, track and collaborate on service tickets.",
                "summary_ar": "كيفية تقديم تذاكر الخدمة ومتابعتها والتعاون بشأنها.",
                "body_en": "<h2>Working in the portal</h2><p>Use the navigation to create requests, review your tickets, follow SLA targets and collaborate with assigned teams.</p><h3>Navigation preference</h3><p>Use the header toggle to cycle between full, icon-only and hidden navigation. Your choice is saved to your profile.</p>",
                "body_ar": "<h2>العمل في البوابة</h2><p>استخدم التنقل لإنشاء الطلبات ومراجعة تذاكرك ومتابعة أهداف مستوى الخدمة والتعاون مع الفرق المعينة.</p>",
                "audience": Page.Audience.PORTAL,
                "portal_icon": "bi-compass",
                "state": Page.State.PUBLISHED,
                "publication_date": timezone.now(),
                "is_visible": True,
            },
        )
        analytics_help, _ = Page.objects.update_or_create(
            slug="analytics-help",
            defaults={
                "title_en": "Analytics assistant guide",
                "title_ar": "دليل مساعد التحليلات",
                "summary_en": "Ask governed questions with Ollama, Vanna and ChromaDB.",
                "summary_ar": "اطرح أسئلة محكومة باستخدام أولاما وفانا وكروما دي بي.",
                "body_en": "<h2>Ask clear business questions</h2><p>Choose a domain, start a conversation and refine it with follow-up questions. Every question is stored in the selected session.</p><h3>Review before use</h3><p>Inspect generated SQL, result rows and query diagnostics before using an answer operationally.</p>",
                "body_ar": "<h2>اطرح أسئلة عمل واضحة</h2><p>اختر نطاقاً وابدأ محادثة ثم حسّنها بأسئلة متابعة. يتم حفظ كل سؤال في الجلسة المحددة.</p>",
                "audience": Page.Audience.PORTAL,
                "portal_icon": "bi-stars",
                "state": Page.State.PUBLISHED,
                "publication_date": timezone.now(),
                "is_visible": True,
            },
        )
        portal_nav = [
            ("Overview", "نظرة عامة", NavigationItem.Section.WORKSPACE, "bi-grid-1x2", "portal:dashboard", [], None, 10, False, False),
            ("Tickets", "التذاكر", NavigationItem.Section.WORKSPACE, "bi-ticket-perforated", "portal:ticket_list", [], None, 20, False, False),
            ("Create ticket", "إنشاء تذكرة", NavigationItem.Section.WORKSPACE, "bi-plus-circle", "portal:create_ticket", [1], None, 30, False, True),
            ("Vanna analytics", "تحليلات فانا", NavigationItem.Section.INTELLIGENCE, "bi-stars", "orchestrator:console", [], None, 40, False, False),
            ("Knowledge base", "قاعدة المعرفة", NavigationItem.Section.INTELLIGENCE, "bi-journal-text", "knowledge:list", [], None, 50, False, False),
            ("Portal guide", "دليل البوابة", NavigationItem.Section.RESOURCES, "bi-compass", "", [], portal_guide, 60, False, False),
            ("Analytics guide", "دليل التحليلات", NavigationItem.Section.RESOURCES, "bi-graph-up-arrow", "", [], analytics_help, 70, False, False),
            ("Platform admin", "إدارة المنصة", NavigationItem.Section.ADMINISTRATION, "bi-sliders", "admin:index", [], None, 80, True, False),
            ("CMS & portal pages", "صفحات الموقع والبوابة", NavigationItem.Section.ADMINISTRATION, "bi-window", "admin:cms_page_changelist", [], None, 90, True, False),
            ("Navigation manager", "إدارة التنقل", NavigationItem.Section.ADMINISTRATION, "bi-list-nested", "admin:cms_navigationitem_changelist", [], None, 100, True, False),
        ]
        for label_en, label_ar, section, icon, route_name, route_arguments, linked_page, order, staff_only, emphasized in portal_nav:
            NavigationItem.objects.update_or_create(
                label_en=label_en,
                location="portal",
                defaults={
                    "label_ar": label_ar,
                    "section": section,
                    "icon": icon,
                    "route_name": route_name,
                    "route_arguments": route_arguments,
                    "linked_page": linked_page,
                    "url": "",
                    "order": order,
                    "staff_only": staff_only,
                    "emphasized": emphasized,
                    "is_visible": True,
                },
            )
        service_category, _ = ServiceCategory.objects.update_or_create(slug="insurance-services", defaults={"name_en": "Insurance Services", "name_ar": "خدمات التأمين", "icon": "bi-shield-check"})
        services = [
            ("Claims coordination", "تنسيق المطالبات", "Submit claim-related inquiries and supporting documents through a secure workflow.", "قدّم استفسارات المطالبات ومستنداتها عبر مسار آمن.", "bi-clipboard2-pulse"),
            ("Policy servicing", "خدمات الوثائق", "Request policy documents, endorsements and service updates with clear ownership.", "اطلب مستندات الوثيقة والتعديلات مع وضوح المسؤولية.", "bi-file-earmark-check"),
            ("Member support", "دعم الأعضاء", "Get help with benefits, eligibility and health service questions.", "احصل على دعم للمنافع والأهلية والخدمات الصحية.", "bi-person-heart"),
            ("Provider services", "خدمات مقدمي الخدمة", "Coordinate empanelment, network and provider operational requests.", "نسّق طلبات شبكة ومقدمي الخدمة.", "bi-hospital"),
            ("Payment inquiries", "استفسارات المدفوعات", "Track approved payment inquiries and the responsible finance workflow.", "تابع استفسارات المدفوعات ومسارها المالي.", "bi-cash-coin"),
            ("Customer care", "العناية بالعملاء", "Raise feedback or complaints and follow every update transparently.", "قدّم الملاحظات أو الشكاوى وتابعها بوضوح.", "bi-headset"),
        ]
        for order, (en, ar, summary_en, summary_ar, icon) in enumerate(services, 1):
            Service.objects.update_or_create(category=service_category, title_en=en, defaults={"title_ar": ar, "summary_en": summary_en, "summary_ar": summary_ar, "icon": icon, "link": "/portal/tickets/create/1/", "is_featured": order <= 3, "is_active": True, "order": order})
        for order, (label_en, label_ar, value, suffix) in enumerate([("Request visibility", "وضوح الطلبات", "24/7", ""), ("Supported languages", "اللغات المدعومة", "2", ""), ("Activity tracked", "تتبع النشاط", "100", "%"), ("Unified workspace", "مساحة عمل موحدة", "1", "")], 1):
            Statistic.objects.update_or_create(label_en=label_en, defaults={"label_ar": label_ar, "value": value, "suffix": suffix, "order": order})
        Testimonial.objects.update_or_create(name="Service Operations Lead", defaults={"role_en": "Insurance Operations", "role_ar": "عمليات التأمين", "quote_en": "A clear request record reduces hand-offs and makes ownership visible.", "quote_ar": "سجل الطلب الواضح يقلل التحويلات ويجعل المسؤولية ظاهرة."})
        for order, (key, name, icon) in enumerate([("tickets", "Tickets", "bi-ticket"), ("knowledge", "Knowledge Base", "bi-journal-text"), ("ai", "AI Assistant", "bi-stars"), ("claims", "Claims Services", "bi-clipboard-pulse"), ("payments", "Payments", "bi-cash-coin")], 1):
            ModuleRegistry.objects.update_or_create(key=key, defaults={"name_en": name, "name_ar": name, "icon": icon, "order": order, "is_enabled": True})
        Page.objects.update_or_create(slug="about", defaults={"title_en": "About GLIS", "title_ar": "عن جرين لاين", "summary_en": "A service coordination platform for connected insurance relationships.", "summary_ar": "منصة لتنسيق الخدمات في علاقات التأمين المترابطة.", "body_en": "GLIS brings customers, providers, insurers and service teams into one accountable workflow. The platform is designed around secure access, clear ownership and bilingual service.", "body_ar": "تجمع منصة جرين لاين العملاء ومقدمي الخدمة وشركات التأمين وفرق الخدمة ضمن مسار عمل واحد ومسؤول.", "audience": Page.Audience.PUBLIC, "state": "published", "publication_date": timezone.now(), "is_visible": True})

    def seed_knowledge(self, users, projects, products, categories):
        knowledge_specs = [("claims", "Claims", "المطالبات", "bi-clipboard-pulse"), ("policies", "Policies", "الوثائق", "bi-file-text"), ("support", "Support", "الدعم", "bi-life-preserver")]
        cats = {}
        for slug, en, ar, icon in knowledge_specs:
            cats[slug], _ = KnowledgeCategory.objects.update_or_create(slug=slug, defaults={"name_en": en, "name_ar": ar, "icon": icon})
        articles = [
            ("claim-documents", cats["claims"], "Documents to prepare for claim support", "المستندات المطلوبة لدعم المطالبة", "A practical checklist for a complete request.", "قائمة عملية لطلب مكتمل.", "Prepare the claim number, policy number, identity document, event details and any supporting reports. Remove unrelated personal information before upload."),
            ("track-request", cats["support"], "How to track a submitted request", "كيفية متابعة طلب مقدم", "Follow status, updates and service timelines.", "تابع الحالة والتحديثات والمواعيد.", "Open My Tickets, select the reference and review the status, SLA panel, conversation and activity timeline. Reply in the public conversation when the team requests clarification."),
            ("policy-service", cats["policies"], "Understanding policy service requests", "فهم طلبات خدمة الوثائق", "Choose the correct service and provide useful context.", "اختر الخدمة المناسبة وقدم معلومات مفيدة.", "A policy service request should include the policy reference, requested change, effective date and supporting documents. Coverage changes remain subject to insurer approval."),
        ]
        for slug, category, en, ar, summary_en, summary_ar, body_en in articles:
            Article.objects.update_or_create(slug=slug, defaults={"category": category, "title_en": en, "title_ar": ar, "summary_en": summary_en, "summary_ar": summary_ar, "body_en": body_en, "body_ar": summary_ar, "state": "published", "is_public": True, "is_featured": True, "published_at": timezone.now(), "author": users[UserProfile.Role.SUPER_ADMIN]})

    def seed_tickets(self, users, groups, projects, products, categories):
        User = get_user_model()
        requesters = [User.objects.get(email="customer@glis.local"), User.objects.get(email="guest@glis.local")]
        agents = [User.objects.get(email="claims.agent@glis.local"), User.objects.get(email="support.agent@glis.local"), User.objects.get(email="manager@glis.local")]
        category_list = list(categories.values())
        statuses = cycle(["new", "open", "in_progress", "pending_customer", "resolved", "closed"])
        priorities = cycle(["low", "medium", "medium", "high", "critical"])
        subjects = ["Claim status update requested", "Policy copy required", "Hospital pre-authorization follow-up", "Payment reference inquiry", "Complaint about service delay", "Provider onboarding documents", "Member eligibility clarification", "Motor repair approval follow-up"]
        for index in range(24):
            category = category_list[index % len(category_list)]
            status, priority = next(statuses), next(priorities)
            created_at = timezone.now() - timedelta(days=23-index, hours=index % 7)
            sla = SLAPolicy.objects.filter(category=category, priority=priority).first()
            ticket, created = Ticket.objects.get_or_create(subject=f"{subjects[index % len(subjects)]} #{index+1}", requester=requesters[index % 2], defaults={
                "description": f"Demo request {index+1}: please review the service details and provide the next required action.",
                "assignee": agents[index % len(agents)] if index % 3 else None,
                "project": category.product.project, "product": category.product, "category": category,
                "status": status, "priority": priority, "visibility": "restricted" if index % 8 == 0 else "standard",
                "is_sensitive": index % 6 == 0, "tags": ["demo", category.code.lower()], "sla_policy": sla,
                "first_response_due_at": created_at + timedelta(minutes=sla.first_response_minutes if sla else 240),
                "resolution_due_at": created_at + timedelta(minutes=sla.resolution_minutes if sla else 1440),
                "resolved_at": created_at + timedelta(hours=10) if status in {"resolved", "closed"} else None,
                "closed_at": created_at + timedelta(hours=12) if status == "closed" else None,
                "ai_summary": "A service request requiring document verification and responsible-team review.",
                "ai_recommendations": {"suggested_priority": priority, "suggested_group": category.default_group.name, "confidence": 0.82, "suggested_solution": "Verify references and supporting documents before responding."},
            })
            if created:
                Ticket.objects.filter(pk=ticket.pk).update(created_at=created_at, updated_at=created_at + timedelta(hours=2))
                ticket.refresh_from_db()
            ticket.groups.add(category.default_group)
            if ticket.assignee:
                ticket.assignees.add(ticket.assignee)
            TicketDynamicData.objects.update_or_create(ticket=ticket, defaults={"values": {"claim_number": f"CLM-2026-{1000+index}", "description": ticket.description, "beneficiary_account": "OM••••••••1234" if ticket.is_sensitive else ""}, "sensitive_keys": ["beneficiary_account"] if ticket.is_sensitive else []})
            if not ticket.comments.exists():
                TicketComment.objects.create(ticket=ticket, author=ticket.requester, body="Please help with this request and let me know if any additional document is required.")
                TicketComment.objects.create(ticket=ticket, author=agents[index % len(agents)], body="Initial triage completed and routed to the responsible team.", is_internal=True)
            TicketEvent.objects.get_or_create(ticket=ticket, event_type="created", summary="Ticket submitted", defaults={"actor": ticket.requester})
            TicketEvent.objects.get_or_create(ticket=ticket, event_type="routed", summary=f"Routed to {category.default_group.name}", defaults={"actor": agents[index % len(agents)]})
            if ticket.assignee:
                Notification.objects.get_or_create(user=ticket.assignee, ticket=ticket, kind="assignment", title=f"Assigned: {ticket.reference}", defaults={"body": ticket.subject, "link": f"/portal/tickets/{ticket.reference}/"})
            if category.approval_workflow_id and not ticket.approvals.exists():
                initialize_approval_workflow(ticket)
            if index < 4 and not ticket.attachments.exists():
                attachment = TicketAttachment(ticket=ticket, uploaded_by=ticket.requester, original_name=f"supporting-document-{index+1}.pdf", content_type="application/pdf", size=40, scan_status="clean", is_restricted=index == 0)
                attachment.file.save(f"supporting-document-{index+1}.pdf", ContentFile(b"%PDF-1.4\n% GLIS demo placeholder\n%%EOF"), save=True)
