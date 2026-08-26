import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from apps.accounts.models import UserProfile
from apps.cms.models import NavigationItem, Page
from apps.orchestrator.local_vanna import LocalVannaOllama, SqlGovernor
from apps.orchestrator.models import AIDomain, AnalysisSession, DataSource, QueryAudit, VannaSettings
from services.access import TicketAccessPolicy
from services.dynamic_forms import DynamicTicketForm, build_api_payload, safe_schema_payload
from .models import Category, Notification, Product, Project, SupportGroup, Ticket


class TicketAccessPolicyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.guest = User.objects.create_user(username="guest@example.com", email="guest@example.com", password="test-password")
        self.other = User.objects.create_user(username="other@example.com", email="other@example.com", password="test-password")
        self.agent = User.objects.create_user(username="agent@example.com", email="agent@example.com", password="test-password")
        self.guest.profile.role = UserProfile.Role.GUEST
        self.guest.profile.save()
        self.agent.profile.role = UserProfile.Role.SUPPORT_AGENT
        self.agent.profile.save()
        self.support = SupportGroup.objects.create(name="Claims", code="claims")
        self.support.members.add(self.agent)
        self.project = Project.objects.create(code="CLM", name_en="Claims")
        self.project.groups.add(self.support)
        self.product = Product.objects.create(project=self.project, code="MOTOR", name_en="Motor")
        self.category = Category.objects.create(product=self.product, code="STATUS", name_en="Claim status", default_group=self.support)
        self.own = Ticket.objects.create(subject="Own request", description="Own", requester=self.guest, project=self.project, product=self.product, category=self.category)
        self.group_ticket = Ticket.objects.create(subject="Group request", description="Group", requester=self.other, project=self.project, product=self.product, category=self.category)
        self.group_ticket.groups.add(self.support)

    def test_guest_only_sees_own_ticket(self):
        self.assertEqual(list(TicketAccessPolicy.visible_queryset(self.guest)), [self.own])

    def test_support_member_sees_group_ticket(self):
        self.assertIn(self.group_ticket, TicketAccessPolicy.visible_queryset(self.agent))

    def test_ticket_detail_prevents_idor(self):
        self.client.force_login(self.guest)
        own_response = self.client.get(reverse("portal:ticket_detail", args=[self.own.reference]))
        self.assertEqual(own_response.status_code, 200)
        response = self.client.get(reverse("portal:ticket_detail", args=[self.group_ticket.reference]))
        self.assertEqual(response.status_code, 404)

    def test_group_member_must_take_over_before_editing(self):
        self.assertFalse(TicketAccessPolicy.can_edit(self.agent, self.group_ticket))
        self.assertTrue(TicketAccessPolicy.can_take_over(self.agent, self.group_ticket))
        self.client.force_login(self.agent)
        response = self.client.post(reverse("portal:take_over_ticket", args=[self.group_ticket.reference]))
        self.assertRedirects(response, reverse("portal:ticket_detail", args=[self.group_ticket.reference]))
        self.assertTrue(self.group_ticket.assignees.filter(pk=self.agent.pk).exists())
        self.assertTrue(TicketAccessPolicy.can_edit(self.agent, self.group_ticket))

    def test_multi_user_and_group_assignment(self):
        permission = Permission.objects.get(codename="assign", content_type__app_label="tickets")
        self.agent.user_permissions.add(permission)
        second_group = SupportGroup.objects.create(name="Operations", code="operations")
        self.client.force_login(self.agent)
        response = self.client.post(reverse("portal:assign_ticket", args=[self.group_ticket.reference]), {"users": [self.agent.pk, self.other.pk], "groups": [self.support.pk, second_group.pk], "replace_existing": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.group_ticket.assignees.count(), 2)
        self.assertEqual(self.group_ticket.groups.count(), 2)

    def test_export_returns_only_visible_tickets(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse("portal:export_tickets"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8-sig")
        self.assertIn(self.own.reference, body)
        self.assertNotIn(self.group_ticket.reference, body)

    def test_notification_feed_is_user_scoped(self):
        Notification.objects.create(user=self.agent, ticket=self.group_ticket, title="Assigned", link=f"/portal/tickets/{self.group_ticket.reference}/")
        Notification.objects.create(user=self.other, ticket=self.group_ticket, title="Other")
        self.client.force_login(self.agent)
        payload = self.client.get(reverse("portal:notification_feed")).json()
        self.assertEqual(payload["unread"], 1)
        self.assertEqual(len(payload["items"]), 1)


class DynamicFormSecurityTests(TestCase):
    def test_safe_schema_never_exposes_raw_sql(self):
        schema = {"fields": [{"name": "location", "data_source": {"registry": "complaint_locations", "query": "DROP TABLE tickets"}, "lookup": {"query": "SELECT secret"}}]}
        safe = safe_schema_payload(schema)
        self.assertNotIn("query", safe["fields"][0]["data_source"])
        self.assertNotIn("query", safe["fields"][0]["lookup"])

    def test_registry_driven_select_is_rendered(self):
        schema = {"fields": [{"name": "location", "label": "Location", "control": "select", "required": True, "data_source": {"registry": "complaint_locations"}}]}
        form = DynamicTicketForm({"location": "muscat"}, schema=schema)
        self.assertTrue(form.is_valid())

    def test_validated_values_map_to_api_sections(self):
        schema = {"api_defaults": {"sspId": 0}, "fields": [{"name": "category", "api_name": "categoryId", "api_type": "int", "api_section": "root"}, {"name": "details", "api_name": "description", "api_type": "string", "api_section": "complaintDetail"}]}
        payload = build_api_payload(schema, {"category": "7", "details": "Delayed response"})
        self.assertEqual(payload, {"sspId": 0, "categoryId": 7, "complaintDetail": {"description": "Delayed response"}})


class PublicExperienceTests(TestCase):
    def test_public_home_and_login_render_without_seed_data(self):
        self.assertEqual(self.client.get(reverse("public:home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_login")).status_code, 200)

    def test_development_static_asset_resolves_without_manifest(self):
        self.assertEqual(staticfiles_storage.url("css/glis.css"), "/static/css/glis.css")

    def test_language_switch_translates_both_directions(self):
        response = self.client.post(reverse("switch_language"), {"language": "ar", "next": "/portal/"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/ar/portal/")
        response = self.client.post(reverse("switch_language"), {"language": "en", "next": "/ar/portal/"})
        self.assertEqual(response["Location"], "/portal/")


class VannaConsoleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="analyst@example.com", email="analyst@example.com", password="test-password")
        source = DataSource.objects.create(name="Test warehouse", engine="sqlite", is_read_only=True)
        self.domain = AIDomain.objects.create(
            name="Operations",
            slug="operations",
            allowed_tables=["tickets_ticket", "tickets_project"],
        )
        self.domain.data_sources.add(source)

    def test_demo_vanna_console_and_query(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("orchestrator:console")).status_code, 200)
        response = self.client.post(reverse("orchestrator:ask"), {"domain": self.domain.pk, "question": "Show tickets by priority"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("sql", payload)
        self.assertTrue(payload["data"])

    def test_follow_up_questions_remain_in_the_same_session(self):
        self.client.force_login(self.user)
        first = self.client.post(reverse("orchestrator:ask"), {"domain": self.domain.pk, "question": "Show tickets by priority"}).json()
        second = self.client.post(reverse("orchestrator:ask"), {"domain": self.domain.pk, "session_id": first["session_id"], "question": "Now show the same tickets by status"}).json()
        self.assertEqual(first["session_id"], second["session_id"])
        history = self.client.get(reverse("orchestrator:session_detail", args=[first["session_id"]])).json()
        self.assertEqual([item["question"] for item in history["queries"]], ["Show tickets by priority", "Now show the same tickets by status"])

    def test_session_history_is_user_scoped(self):
        session = AnalysisSession.objects.create(user=self.user, domain=self.domain, title="Private analysis")
        QueryAudit.objects.create(session=session, question="First question", summary="First answer")
        QueryAudit.objects.create(session=session, question="Second question", summary="Second answer")
        self.client.force_login(self.user)
        response = self.client.get(reverse("orchestrator:session_detail", args=[session.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["question"] for item in response.json()["queries"]], ["First question", "Second question"])
        other = get_user_model().objects.create_user(username="other-analyst@example.com", email="other-analyst@example.com", password="test-password")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("orchestrator:session_detail", args=[session.pk])).status_code, 404)

    @patch("apps.orchestrator.local_vanna.LocalVannaOllama.ask")
    def test_local_ollama_provider_is_used_for_query(self, local_ask):
        local_ask.return_value = {
            "sql": "SELECT status, COUNT(*) AS total FROM tickets_ticket GROUP BY status",
            "summary": "Open tickets grouped by status.",
            "data": [{"status": "open", "total": 2}],
            "chart": {"type": "pie", "x": "status", "y": "total"},
            "followups": [],
            "provider": "ollama_vanna",
        }
        config = VannaSettings.load()
        config.provider = "ollama_vanna"
        config.endpoint = "http://127.0.0.1:11434"
        config.allow_sql_execution = True
        config.save()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("orchestrator:ask"),
            {"domain": self.domain.pk, "question": "Show tickets by status"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "ollama_vanna")
        local_ask.assert_called_once()

    def test_sql_governor_blocks_unknown_and_write_tables(self):
        governor = SqlGovernor(domain=self.domain, user=self.user)
        with self.assertRaisesMessage(ValueError, "not allowed"):
            governor.govern("SELECT email FROM auth_user")
        with self.assertRaisesMessage(ValueError, "Only SELECT"):
            governor.govern("DELETE FROM tickets_ticket")

    def test_sql_governor_applies_ticket_visibility_cte(self):
        governor = SqlGovernor(domain=self.domain, user=self.user)
        sql = governor.govern(
            "SELECT status, COUNT(*) AS total FROM tickets_ticket GROUP BY status"
        )
        self.assertIn("WITH tickets_ticket AS", sql)
        self.assertIn("WHERE id IN (NULL)", sql)

    @staticmethod
    def _fake_embeddings(*, model, input):
        texts = [input] if isinstance(input, str) else list(input)
        return {
            "embeddings": [
                [1.0, float(sum(map(ord, text)) % 17 + 1), float(len(text) % 13 + 1)]
                for text in texts
            ]
        }

    @patch("ollama.Client")
    def test_vanna_chroma_rag_executes_governed_run_sql(self, ollama_client):
        ollama_client.return_value.embed.side_effect = self._fake_embeddings
        ollama_client.return_value.chat.side_effect = [
            {
                "message": {
                    "content": (
                        '{"sql":"SELECT status, COUNT(*) AS total '
                        'FROM tickets_ticket GROUP BY status"}'
                    )
                },
                "done": True,
                "done_reason": "stop",
            },
            {
                "message": {"content": "No visible tickets were returned for this user."},
                "done": True,
                "done_reason": "stop",
            },
        ]
        config = VannaSettings.load()
        config.provider = "ollama_vanna"
        config.endpoint = "http://127.0.0.1:11434"
        config.allow_sql_execution = True
        config.save()
        session = AnalysisSession.objects.create(
            user=self.user,
            domain=self.domain,
            title="Status analysis",
        )
        with tempfile.TemporaryDirectory() as chroma_directory:
            with override_settings(CHROMA_PERSIST_DIRECTORY=chroma_directory):
                result = LocalVannaOllama().ask(
                    vanna_settings=config,
                    session=session,
                    question="Show tickets by status",
                    user=self.user,
                )
        self.assertEqual(result["provider"], "ollama_vanna")
        self.assertEqual(result["execution_mode"], "chroma_rag_vanna_run_sql")
        self.assertGreater(result["chroma_memories"], 0)
        self.assertIn("WITH tickets_ticket AS", result["sql"])
        self.assertEqual(result["data"], [])
        self.assertEqual(ollama_client.return_value.chat.call_count, 2)
        self.assertTrue(ollama_client.return_value.embed.called)
        self.assertNotIn("tools", ollama_client.return_value.chat.call_args_list[0].kwargs)

    @patch("ollama.Client")
    def test_vanna_chroma_retries_non_structured_sql_response(self, ollama_client):
        ollama_client.return_value.embed.side_effect = self._fake_embeddings
        ollama_client.return_value.chat.side_effect = [
            {
                "message": {"content": "I will prepare the requested ticket analysis."},
                "done": True,
                "done_reason": "stop",
            },
            {
                "message": {
                    "content": (
                        '{"sql":"SELECT status, COUNT(*) AS total '
                        'FROM tickets_ticket GROUP BY status"}'
                    )
                },
                "done": True,
                "done_reason": "stop",
            },
            {
                "message": {"content": "No visible tickets were returned for this user."},
                "done": True,
                "done_reason": "stop",
            },
        ]
        config = VannaSettings.load()
        config.provider = "ollama_vanna"
        config.endpoint = "http://127.0.0.1:11434"
        config.allow_sql_execution = True
        config.save()
        session = AnalysisSession.objects.create(
            user=self.user,
            domain=self.domain,
            title="Recovered status analysis",
        )

        with tempfile.TemporaryDirectory() as chroma_directory:
            with override_settings(CHROMA_PERSIST_DIRECTORY=chroma_directory):
                result = LocalVannaOllama().ask(
                    vanna_settings=config,
                    session=session,
                    question="Show tickets by status",
                    user=self.user,
                )

        self.assertEqual(result["execution_mode"], "chroma_rag_vanna_run_sql")
        self.assertIn("WITH tickets_ticket AS", result["sql"])
        self.assertEqual(result["data"], [])
        self.assertEqual(ollama_client.return_value.chat.call_count, 3)
        retry_payload = ollama_client.return_value.chat.call_args_list[1].kwargs
        self.assertNotIn("tools", retry_payload)
        self.assertEqual(retry_payload["format"]["required"], ["sql"])


class PortalCustomizationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="portal-user@example.com", email="portal-user@example.com", password="test-password")
        self.page = Page.objects.create(
            slug="portal-guide-test",
            title_en="Portal guide",
            body_en="Managed entirely from Admin.",
            audience=Page.Audience.PORTAL,
            state=Page.State.PUBLISHED,
            publication_date=timezone.now(),
        )
        NavigationItem.objects.create(
            label_en="Portal guide",
            location="portal",
            section=NavigationItem.Section.RESOURCES,
            icon="bi-compass",
            linked_page=self.page,
            order=10,
        )

    def test_sidebar_mode_is_saved_to_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:sidebar_preference"), {"mode": UserProfile.SidebarMode.HIDDEN})
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.sidebar_mode, UserProfile.SidebarMode.HIDDEN)

    def test_admin_managed_portal_page_and_navigation_render(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("portal:managed_page", args=[self.page.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Managed entirely from Admin.")
        self.assertContains(response, "Portal guide")

    def test_group_restricted_portal_page_is_not_exposed(self):
        restricted_group = Group.objects.create(name="Restricted CMS readers")
        self.page.allowed_groups.add(restricted_group)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("portal:managed_page", args=[self.page.slug])).status_code, 404)
