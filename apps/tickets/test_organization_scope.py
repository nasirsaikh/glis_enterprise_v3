from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.orchestrator.local_vanna import SqlGovernor
from apps.orchestrator.models import AIDomain, DataSource
from apps.accounts.models import UserProfile
from apps.tasks.forms import TaskForm
from apps.tpa.models import TPAOrganization
from services.access import TicketAccessPolicy
from services.tenancy import visible_support_groups, visible_users
from .forms import TicketAssignmentForm, TicketIntakeForm, TicketShareForm
from .models import Category, Product, Project, SupportGroup, Ticket


class PortalOrganizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_user("org-actor", email="actor@example.com", is_staff=True)
        cls.peer = User.objects.create_user("org-peer", email="peer@example.com")
        cls.outsider = User.objects.create_user("org-outside", email="outside@example.com")
        cls.team_peer = User.objects.create_user("org-team", email="team@example.com")
        cls.org = TPAOrganization.objects.create(code="ORG-A", name_en="Organization A", organization_type="CORPORATE")
        cls.other_org = TPAOrganization.objects.create(code="ORG-B", name_en="Organization B", organization_type="CORPORATE")
        cls.actor.profile.organizations.add(cls.org)
        cls.peer.profile.organizations.add(cls.org)
        cls.outsider.profile.organizations.add(cls.other_org)
        cls.actor.profile.role = UserProfile.Role.SUPPORT_AGENT
        cls.actor.profile.save()
        cls.actor.user_permissions.add(*Permission.objects.filter(content_type__app_label="tickets", codename__in=["assign", "view_all"]))
        cls.group = SupportGroup.objects.create(name="Shared support team", code="org-support")
        cls.group.members.add(cls.actor, cls.team_peer)
        cls.outside_group = SupportGroup.objects.create(name="Outside team", code="org-outside-group")
        cls.outside_group.organizations.add(cls.other_org)
        cls.project = Project.objects.create(code="ORG", name_en="Named Project")
        cls.product = Product.objects.create(project=cls.project, code="ORG-P", name_en="Named Product")
        cls.category = Category.objects.create(product=cls.product, code="ORG-C", name_en="Named Category")
        cls.auth_group = Group.objects.create(name="Organization requests")
        cls.actor.groups.add(cls.auth_group)
        cls.category.allowed_groups.add(cls.auth_group)
        cls.own_ticket = Ticket.objects.create(subject="Tenant A", description="Details", requester=cls.peer,
            project=cls.project, product=cls.product, category=cls.category)
        cls.outside_ticket = Ticket.objects.create(subject="Tenant B", description="Private", requester=cls.outsider,
            project=cls.project, product=cls.product, category=cls.category)

    def test_assignment_permission_does_not_expand_tenant_scope(self):
        form = TicketAssignmentForm(user=self.actor, ticket=self.own_ticket)
        self.assertIn(self.peer, form.fields["users"].queryset)
        self.assertIn(self.team_peer, form.fields["users"].queryset)
        self.assertNotIn(self.outsider, form.fields["users"].queryset)
        self.assertNotIn(self.outside_group, form.fields["groups"].queryset)

    def test_forged_assignment_and_share_are_invalid(self):
        assignment = TicketAssignmentForm({"users": [self.outsider.pk], "groups": [self.outside_group.pk]},
                                          user=self.actor, ticket=self.own_ticket)
        self.assertFalse(assignment.is_valid())
        self.assertFalse(TicketShareForm({"recipient": self.outsider.pk, "expires_in_days": 7}, user=self.actor).is_valid())

    def test_tasks_use_same_user_scope(self):
        form = TaskForm(user=self.actor)
        self.assertIn(self.peer, form.fields["owner"].queryset)
        self.assertNotIn(self.outsider, form.fields["owner"].queryset)
        self.assertNotIn(self.outsider, form.fields["tagged_users"].queryset)

    def test_view_all_dashboard_and_direct_url_are_scoped(self):
        self.assertIn(self.own_ticket, TicketAccessPolicy.visible_queryset(self.actor))
        self.assertNotIn(self.outside_ticket, TicketAccessPolicy.visible_queryset(self.actor))
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse("portal:ticket_detail", args=[self.outside_ticket.reference])).status_code, 404)

    def test_no_identity_has_empty_selectors(self):
        self.assertFalse(visible_users(None).exists())
        self.assertFalse(visible_support_groups(None).exists())

    def test_intake_has_one_required_clarification(self):
        form = TicketIntakeForm()
        self.assertEqual(list(form.fields), ["answer_1"])
        self.assertFalse(TicketIntakeForm({"answer_1": ""}).is_valid())

    def test_review_resolves_names_and_renders_full_width_request(self):
        self.client.force_login(self.actor)
        session = self.client.session
        session["ticket_wizard"] = {"selection": {"project": self.project.pk, "product": self.product.pk, "category": self.category.pk},
                                   "dynamic": {"location": "muscat"}, "answers": {"answer_1": "Explain my request"},
                                   "analysis": {"summary": "Request summary"}}
        session.save()
        response = self.client.get(reverse("portal:create_ticket", args=[4]))
        self.assertContains(response, "Named Project")
        self.assertContains(response, "Named Product")
        self.assertContains(response, "Explain my request")
        self.assertContains(response, 'class="review-layout"')

    def test_vanna_view_all_permission_keeps_organization_scope(self):
        source = DataSource.objects.create(name="Scoped analytics", engine="sqlite", is_read_only=True)
        domain = AIDomain.objects.create(name="Scoped tickets", slug="scoped-tickets", data_source=source,
                                        allowed_tables=["tickets_ticket"])
        governed = SqlGovernor(domain=domain, user=self.actor).govern("SELECT id, subject FROM tickets_ticket")
        self.assertIn("WITH tickets_ticket AS", governed)
        self.assertIn(f"WHERE id IN ({self.own_ticket.pk})", governed)
        self.assertNotIn(str(self.outside_ticket.pk), governed.split("WHERE id IN (", 1)[1].split(")", 1)[0])
