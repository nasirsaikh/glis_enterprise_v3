# apps/app_settings/management/commands/seed_cms_pages_v2.py

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

from cms.api import add_plugin, create_page
from cms.models import Page


User = get_user_model()


class Command(BaseCommand):
    help = "Create sample django CMS pages for GLIS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Optional user ID used as page creator.",
        )

    def handle(self, *args, **options):
        user = self._get_user(options.get("user_id"))

        pages = [
            {
                "title": "Home",
                "slug": "",
                "reverse_id": "glis_home",
                "template": "cms/glis_home.html",
                "is_home": True,
                "plugins": {
                    "hero": [
                        (
                            "TextPlugin",
                            """
                            <div class="py-5 text-center">
                                <span class="badge text-bg-success mb-3">
                                    GLIS Enterprise Platform
                                </span>

                                <h1 class="display-4 fw-bold">
                                    One platform for insurance services,
                                    analytics and automation
                                </h1>

                                <p class="lead text-muted mt-3">
                                    Manage service requests, analytics,
                                    knowledge, workflows and enterprise
                                    operations from one secure platform.
                                </p>

                                <div class="mt-4">
                                    <a href="/portal/" class="btn btn-primary btn-lg me-2">
                                        Open Portal
                                    </a>

                                    <a href="/pages/services/" class="btn btn-outline-primary btn-lg">
                                        Explore Services
                                    </a>
                                </div>
                            </div>
                            """,
                        ),
                    ],
                    "main_content": [
                        (
                            "TextPlugin",
                            """
                            <div class="text-center mb-5">
                                <h2 class="fw-bold">Built for enterprise insurance operations</h2>
                                <p class="text-muted">
                                    GLIS combines operational workflows,
                                    AI-assisted analytics and centralized
                                    service management.
                                </p>
                            </div>
                            """,
                        ),
                    ],
                    "services": [
                        (
                            "TextPlugin",
                            """
                            <div class="row g-4 py-4">

                                <div class="col-md-4">
                                    <div class="card h-100 shadow-sm border-0">
                                        <div class="card-body">
                                            <h3 class="h5">Service Management</h3>
                                            <p>
                                                Manage tickets, requests,
                                                complaints and internal workflows.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-4">
                                    <div class="card h-100 shadow-sm border-0">
                                        <div class="card-body">
                                            <h3 class="h5">AI Analytics</h3>
                                            <p>
                                                Ask questions in natural language
                                                and analyze enterprise data.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-4">
                                    <div class="card h-100 shadow-sm border-0">
                                        <div class="card-body">
                                            <h3 class="h5">Automation</h3>
                                            <p>
                                                Automate recurring operational,
                                                reporting and communication tasks.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                            </div>
                            """,
                        ),
                    ],
                    "statistics": [
                        (
                            "TextPlugin",
                            """
                            <div class="row g-4 text-center py-5">

                                <div class="col-md-3">
                                    <div class="p-4 bg-body-tertiary rounded-4">
                                        <div class="display-6 fw-bold">24/7</div>
                                        <div class="text-muted">Platform Access</div>
                                    </div>
                                </div>

                                <div class="col-md-3">
                                    <div class="p-4 bg-body-tertiary rounded-4">
                                        <div class="display-6 fw-bold">AI</div>
                                        <div class="text-muted">Analytics Enabled</div>
                                    </div>
                                </div>

                                <div class="col-md-3">
                                    <div class="p-4 bg-body-tertiary rounded-4">
                                        <div class="display-6 fw-bold">360°</div>
                                        <div class="text-muted">Service Visibility</div>
                                    </div>
                                </div>

                                <div class="col-md-3">
                                    <div class="p-4 bg-body-tertiary rounded-4">
                                        <div class="display-6 fw-bold">1</div>
                                        <div class="text-muted">Enterprise Platform</div>
                                    </div>
                                </div>

                            </div>
                            """,
                        ),
                    ],
                    "testimonials": [
                        (
                            "TextPlugin",
                            """
                            <div class="py-5 text-center">
                                <h2 class="fw-bold">A unified digital workspace</h2>
                                <p class="lead text-muted">
                                    Designed to connect operational teams,
                                    analytics, customers and service workflows.
                                </p>
                            </div>
                            """,
                        ),
                    ],
                    "call_to_action": [
                        (
                            "TextPlugin",
                            """
                            <div class="p-5 rounded-4 bg-body-tertiary text-center my-5">
                                <h2 class="fw-bold">
                                    Ready to use GLIS?
                                </h2>

                                <p class="text-muted">
                                    Access your enterprise workspace and
                                    start managing requests and analytics.
                                </p>

                                <a href="/portal/" class="btn btn-primary btn-lg">
                                    Open GLIS Portal
                                </a>
                            </div>
                            """,
                        ),
                    ],
                },
            },
            {
                "title": "About",
                "slug": "about",
                "reverse_id": "glis_about",
                "template": "cms/glis_page.html",
                "plugins": {
                    "content": [
                        (
                            "TextPlugin",
                            """
                            <h1>About GLIS</h1>

                            <p class="lead">
                                GLIS is an enterprise platform designed to
                                centralize insurance service management,
                                analytics, automation and knowledge.
                            </p>

                            <h2 class="mt-5">Our Purpose</h2>

                            <p>
                                The platform provides a unified environment
                                for operational teams to collaborate,
                                manage requests and make better use of
                                enterprise data.
                            </p>

                            <h2 class="mt-5">Key Capabilities</h2>

                            <ul>
                                <li>Enterprise service management</li>
                                <li>AI-powered analytics</li>
                                <li>Workflow automation</li>
                                <li>Knowledge management</li>
                                <li>Reporting and dashboards</li>
                                <li>Secure role-based access</li>
                            </ul>
                            """,
                        ),
                    ],
                },
            },
            {
                "title": "Services",
                "slug": "services",
                "reverse_id": "glis_services",
                "template": "cms/glis_page.html",
                "plugins": {
                    "content": [
                        (
                            "TextPlugin",
                            """
                            <h1>Services</h1>

                            <p class="lead">
                                GLIS provides multiple enterprise services
                                through one centralized platform.
                            </p>

                            <div class="row g-4 mt-3">

                                <div class="col-md-6">
                                    <div class="card h-100 shadow-sm">
                                        <div class="card-body">
                                            <h2 class="h5">Ticket Management</h2>
                                            <p>
                                                Submit, assign, track and resolve
                                                enterprise service requests.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-6">
                                    <div class="card h-100 shadow-sm">
                                        <div class="card-body">
                                            <h2 class="h5">AI Analytics</h2>
                                            <p>
                                                Ask business questions and receive
                                                governed data analysis.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-6">
                                    <div class="card h-100 shadow-sm">
                                        <div class="card-body">
                                            <h2 class="h5">Automation</h2>
                                            <p>
                                                Execute recurring workflows,
                                                reporting and operational jobs.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-6">
                                    <div class="card h-100 shadow-sm">
                                        <div class="card-body">
                                            <h2 class="h5">Knowledge Management</h2>
                                            <p>
                                                Maintain organizational knowledge,
                                                procedures and reference material.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                            </div>
                            """,
                        ),
                    ],
                },
            },
            {
                "title": "Solutions",
                "slug": "solutions",
                "reverse_id": "glis_solutions",
                "template": "cms/glis_page.html",
                "plugins": {
                    "content": [
                        (
                            "TextPlugin",
                            """
                            <h1>Solutions</h1>

                            <p class="lead">
                                GLIS supports multiple enterprise use cases
                                across insurance operations.
                            </p>

                            <h2 class="mt-5">AI Analytics</h2>
                            <p>
                                Natural-language analytics powered by governed
                                enterprise data access.
                            </p>

                            <h2 class="mt-4">Operational Automation</h2>
                            <p>
                                Automate repetitive reporting, scheduling and
                                service workflows.
                            </p>

                            <h2 class="mt-4">Service Management</h2>
                            <p>
                                Centralize complaints, requests, approvals,
                                assignments and communication.
                            </p>

                            <h2 class="mt-4">Enterprise Reporting</h2>
                            <p>
                                Create dashboards, reports and management
                                information from controlled data sources.
                            </p>
                            """,
                        ),
                    ],
                },
            },
            {
                "title": "Knowledge Base",
                "slug": "knowledge-base",
                "reverse_id": "glis_knowledge",
                "template": "cms/glis_page.html",
                "plugins": {
                    "content": [
                        (
                            "TextPlugin",
                            """
                            <h1>Knowledge Base</h1>

                            <p class="lead">
                                Access guides, procedures, FAQs and
                                organizational knowledge.
                            </p>

                            <div class="alert alert-info mt-4">
                                The operational GLIS Knowledge Base remains
                                available through the dedicated Knowledge app.
                            </div>

                            <p>
                                <a href="/knowledge/" class="btn btn-primary">
                                    Open Knowledge Base
                                </a>
                            </p>
                            """,
                        ),
                    ],
                },
            },
            {
                "title": "Contact",
                "slug": "contact",
                "reverse_id": "glis_contact",
                "template": "cms/glis_page.html",
                "plugins": {
                    "content": [
                        (
                            "TextPlugin",
                            """
                            <h1>Contact</h1>

                            <p class="lead">
                                Contact the GLIS support team for platform
                                assistance and service requests.
                            </p>

                            <div class="row g-4 mt-3">

                                <div class="col-md-4">
                                    <div class="card h-100">
                                        <div class="card-body">
                                            <h2 class="h5">Email</h2>
                                            <p>care@glis.example</p>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-4">
                                    <div class="card h-100">
                                        <div class="card-body">
                                            <h2 class="h5">Phone</h2>
                                            <p>+968 2400 0000</p>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-4">
                                    <div class="card h-100">
                                        <div class="card-body">
                                            <h2 class="h5">Location</h2>
                                            <p>Muscat, Sultanate of Oman</p>
                                        </div>
                                    </div>
                                </div>

                            </div>
                            """,
                        ),
                    ],
                },
            },
        ]

        with transaction.atomic():
            for page_definition in pages:
                self._create_page(
                    page_definition=page_definition,
                    user=user,
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "GLIS sample django CMS pages seeded successfully."
            )
        )

        self.stdout.write(
            "Review the pages in django CMS and publish them when ready."
        )

    def _get_user(self, user_id):
        if user_id:
            try:
                return User.objects.get(pk=user_id)
            except User.DoesNotExist as exc:
                raise CommandError(
                    f"User with ID {user_id} does not exist."
                ) from exc

        user = (
            User.objects
            .filter(is_superuser=True, is_active=True)
            .order_by("pk")
            .first()
        )

        if not user:
            user = (
                User.objects
                .filter(is_staff=True, is_active=True)
                .order_by("pk")
                .first()
            )

        if not user:
            raise CommandError(
                "No active superuser/staff user found. "
                "Create one first or use --user-id."
            )

        return user

    def _create_page(self, page_definition, user):
        reverse_id = page_definition["reverse_id"]

        existing = Page.objects.filter(
            reverse_id=reverse_id
        ).first()

        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipping existing page: "
                    f"{page_definition['title']}"
                )
            )
            return existing

        page = create_page(
            title=page_definition["title"],
            template=page_definition["template"],
            language="en",
            slug=page_definition["slug"] or None,
            created_by=user,
            reverse_id=reverse_id,
            in_navigation=True,
        )

        if page_definition.get("is_home"):
            try:
                page.set_as_homepage()
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"Could not automatically mark Home "
                        f"as homepage: {exc}"
                    )
                )

        self._add_plugins(
            page=page,
            plugins=page_definition.get("plugins", {}),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {page_definition['title']}"
            )
        )

        return page

    def _add_plugins(self, page, plugins):
        page_content = page.get_admin_content(
            language="en"
        )

        if not page_content:
            self.stdout.write(
                self.style.WARNING(
                    f"No English PageContent found for {page}."
                )
            )
            return

        placeholders = {
            placeholder.slot: placeholder
            for placeholder in page_content.get_placeholders()
        }

        for slot, plugin_definitions in plugins.items():
            placeholder = placeholders.get(slot)

            if not placeholder:
                self.stdout.write(
                    self.style.WARNING(
                        f"Placeholder '{slot}' not found "
                        f"for page '{page}'."
                    )
                )
                continue

            for plugin_type, body in plugin_definitions:
                add_plugin(
                    placeholder=placeholder,
                    plugin_type=plugin_type,
                    language="en",
                    body=body.strip(),
                )