from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from cms.api import create_page, add_plugin, publish_page
from cms.models import Page


SAMPLE_PAGES = [
    {
        "title": "Home",
        "slug": "home",
        "template": "cms/glis_home.html",
        "reverse_id": "glis-home",
        "is_home": True,
        "sections": [
            ("hero", "TextPlugin", "<h1>Welcome to GLIS</h1><p>One secure enterprise platform for insurance services, analytics, knowledge and collaboration.</p>"),
            ("main_content", "TextPlugin", "<h2>Insurance service, made clear</h2><p>GLIS connects customers, providers and internal teams through a single digital service layer.</p>"),
            ("services", "TextPlugin", "<h2>Services</h2><p>Submit requests, track cases, access support and collaborate securely.</p>"),
            ("statistics", "TextPlugin", "<h2>Platform Highlights</h2><p>Centralized requests • AI analytics • Knowledge base • Secure workflows</p>"),
            ("testimonials", "TextPlugin", "<h2>Built for enterprise teams</h2><p>Designed for operational transparency, governance and faster service delivery.</p>"),
            ("call_to_action", "TextPlugin", "<h2>Get Started</h2><p><a href='/portal/'>Open the GLIS Portal</a></p>"),
        ],
    },
    {
        "title": "About",
        "slug": "about",
        "template": "cms/glis_page.html",
        "reverse_id": "about",
        "sections": [
            ("content", "TextPlugin", "<h1>About GLIS</h1><p>GLIS is an enterprise insurance service platform that centralizes digital requests, knowledge, analytics, automation and collaboration.</p><h2>Our Purpose</h2><p>To simplify insurance operations and provide a consistent digital experience for customers, partners and internal teams.</p>"),
        ],
    },
    {
        "title": "Services",
        "slug": "services",
        "template": "cms/glis_page.html",
        "reverse_id": "services",
        "sections": [
            ("content", "TextPlugin", "<h1>Services</h1><h3>Service Requests</h3><p>Create and track insurance-related requests through the GLIS portal.</p><h3>Claims Support</h3><p>Submit and follow up claim-related service requests.</p><h3>Analytics</h3><p>Use governed AI analytics to query and understand enterprise data.</p><h3>Knowledge</h3><p>Access operational guidance, FAQs and business documentation.</p>"),
        ],
    },
    {
        "title": "Solutions",
        "slug": "solutions",
        "template": "cms/glis_page.html",
        "reverse_id": "solutions",
        "sections": [
            ("content", "TextPlugin", "<h1>Solutions</h1><h3>Customer Service</h3><p>Centralized service request management.</p><h3>Insurance Operations</h3><p>Structured workflows for underwriting, claims, finance and support teams.</p><h3>AI Analytics</h3><p>Natural-language analytics over governed enterprise data.</p><h3>Automation</h3><p>Automated notifications, scheduled processing and business workflows.</p>"),
        ],
    },
    {
        "title": "Knowledge Base",
        "slug": "knowledge-base",
        "template": "cms/glis_page.html",
        "reverse_id": "knowledge-base",
        "sections": [
            ("content", "TextPlugin", "<h1>Knowledge Base</h1><p>Find guides, procedures, FAQs and operational documentation.</p><p><a href='/knowledge/'>Open the Knowledge Base</a></p>"),
        ],
    },
    {
        "title": "Contact",
        "slug": "contact",
        "template": "cms/glis_page.html",
        "reverse_id": "contact",
        "sections": [
            ("content", "TextPlugin", "<h1>Contact Us</h1><p>For support, questions or service assistance, contact the GLIS team through the portal or your configured support channels.</p><p><strong>Email:</strong> care@glis.example</p><p><strong>Location:</strong> Muscat, Sultanate of Oman</p>"),
        ],
    },
]


class Command(BaseCommand):
    help = "Create sample django CMS pages for the GLIS website. Safe to run multiple times."

    def add_arguments(self, parser):
        parser.add_argument("--language", default="en")
        parser.add_argument("--site-id", type=int, default=1)
        parser.add_argument("--publish", action="store_true", help="Publish pages after creation")

    def handle(self, *args, **options):
        language = options["language"]
        site_id = options["site_id"]
        should_publish = options["publish"]

        site = Site.objects.get(pk=site_id)
        self.stdout.write(self.style.NOTICE(f"Using site: {site.domain} (ID {site_id})"))

        created = 0
        skipped = 0

        for spec in SAMPLE_PAGES:
            page = Page.objects.filter(reverse_id=spec["reverse_id"], site=site).first()
            if page:
                self.stdout.write(f"Skipping existing page: {spec['title']}")
                skipped += 1
                continue

            page = create_page(
                title=spec["title"],
                template=spec["template"],
                language=language,
                slug=spec["slug"],
                reverse_id=spec["reverse_id"],
                site=site,
                in_navigation=True,
            )

            if spec.get("is_home"):
                page.set_as_homepage()

            for placeholder_slot, plugin_type, body in spec.get("sections", []):
                placeholder = page.placeholders.get(slot=placeholder_slot)
                add_plugin(
                    placeholder=placeholder,
                    plugin_type=plugin_type,
                    language=language,
                    body=body,
                )

            if should_publish:
                try:
                    publish_page(page, user=None, language=language)
                except TypeError:
                    # django CMS 5.x/versioning setups may expose publishing differently.
                    self.stdout.write(self.style.WARNING(
                        f"Created {spec['title']} as draft; publish it from the CMS toolbar/admin."
                    ))

            created += 1
            self.stdout.write(self.style.SUCCESS(f"Created page: {spec['title']}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Created: {created}, skipped: {skipped}"))
        self.stdout.write("Open /admin/ or /pages/?toolbar_on to edit the generated content.")
