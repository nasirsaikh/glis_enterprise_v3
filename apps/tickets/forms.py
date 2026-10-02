from apps.accounts.models import Organization, OrganizationType
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from apps.ai.models import default_questions
from apps.core.widgets import RadioSelect
from .models import Category, Product, Project, SupportGroup, Ticket, TicketComment, SLAPolicy, TicketOrganization
from services.tenancy import organization_ids, visible_support_groups, visible_users, visible_organizations, assignable_groups, assignable_users, taggable_users, available_approvers
from apps.tpa.models import Policy
from .services.access import accessible_categories,accessible_products,accessible_projects

def selection_id(value):
    value=str(value or '')
    return int(value) if value.isascii() and value.isdigit() else None


class TicketCreateStep1Form(forms.Form):
    supports_business_requests = False
    organization = forms.ModelChoiceField(required=False,queryset=Organization.objects.none(),widget=forms.Select(attrs={'class':'form-select w-100'}))
    policy = forms.ModelChoiceField(required=False,queryset=Policy.objects.none(),widget=forms.Select(attrs={'class':'form-select w-100'}))


    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        widget=forms.Select(
            attrs={
                "class": "form-select w-100",
                "hx-get": "/portal/lookups/products/",
                "hx-target": "#id_product",
                "hx-swap": "innerHTML settle:0ms",
                "hx-sync": "this:replace",
                "hx-trigger": "change",
            }
        ),
    )

    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(
            attrs={
                "class": "form-select w-100",
                "hx-get": "/portal/lookups/categories/",
                "hx-target": "#id_category",
                "hx-swap": "innerHTML settle:0ms",
                "hx-sync": "this:replace",
                "hx-trigger": "change",
            }
        ),
    )

    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        widget=forms.Select(
            attrs={
                "class": "form-select w-100",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user

        if not user or not user.is_authenticated:
            return

        from apps.tpa.services.access import visible_policies
        self.fields['organization'].queryset = visible_organizations(user)
        self.fields['policy'].queryset = visible_policies(user)
        # --------------------------------
        # Projects user can access
        # --------------------------------
        self.fields["project"].queryset = (
            accessible_projects(user)
            .order_by("name_en")
        )

        if not self.supports_business_requests:
            self.fields['project'].queryset=self.fields['project'].queryset.filter(request_type__in=['service','other'])

        project_id = selection_id(
            self.data.get("project")
            or self.initial.get("project")
        )

        product_id = selection_id(
            self.data.get("product")
            or self.initial.get("product")
        )

        # --------------------------------
        # Products user can access
        # under selected project
        # --------------------------------
        if project_id:
            self.fields["product"].queryset = (
                accessible_products(user)
                .filter(project_id=project_id)
                .order_by("name_en")
            )
        else:
            self.fields["product"].queryset = Product.objects.none()

        # --------------------------------
        # Categories user can access
        # under selected product
        # --------------------------------
        if product_id:
            self.fields["category"].queryset = (
                accessible_categories(user)
                .filter(product_id=product_id)
                .order_by("name_en")
            )
        else:
            self.fields["category"].queryset = Category.objects.none()

    def clean(self):
        data = super().clean()
        project,product,category = data.get('project'),data.get('product'),data.get('category')
        if product and project and product.project_id != project.pk:self.add_error('product','Select a product in this project.')
        if category and product and category.product_id != product.pk:self.add_error('category','Select a category in this product.')
        policy,org = data.get('policy'),data.get('organization')
        if policy and org and policy.organization_id != org.pk:self.add_error('organization','The organization must match the policy.')
        return data


class TicketIntakeForm(forms.Form):
    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = [dict((questions or default_questions())[0])]
        for index, question in enumerate(self.questions, start=1):
            self.fields[f"answer_{index}"] = forms.CharField(
                label=_(question["text"]), required=not question.get("optional", False),
                widget=forms.Textarea(attrs={"class": "form-control w-100", "rows": 3, "data-question": index}),
                help_text=_("Optional") if question.get("optional") else "",
            )


class TicketReviewForm(forms.Form):
    subject = forms.CharField(max_length=240, widget=forms.TextInput(attrs={"class": "form-control w-100"}))
    description = forms.CharField(max_length=2_000_000, widget=forms.Textarea(attrs={"class": "form-control w-100 richtext-source", "rows": 6}))
    priority = forms.ChoiceField(choices=Ticket.Priority.choices, widget=forms.Select(attrs={"class": "form-select w-100"}))
    acknowledgment = forms.BooleanField(label=_("I confirm that the information is accurate and may be processed to provide this service."), widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


# class TicketCommentForm(forms.ModelForm):
#     class Meta:
#         model = TicketComment
#         fields = ("body", "is_internal")
#         widgets = {"body": forms.Textarea(attrs={"class": "form-control w-100 richtext-source", "rows": 3, "placeholder": _("Write an update…")}), "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"})}

class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body","status", "is_internal"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "form-control w-100 richtext-source",
                    "rows": 6,
                    "placeholder": "Write an update…",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "form-select w-100",
                }
            ),
            "is_internal": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input glis-switch",
                    "role": "switch",
                }
            ),
        }
    def __init__(self, *args, ticket=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].required = False
        self.fields["body"].widget.attrs.pop("required", None)
        self.fields["status"].required = False
        choices = [("", _("Keep current status"))]
        if ticket and user:
            from services.access import TicketAccessPolicy
            if TicketAccessPolicy.can_edit(user, ticket) and ticket.approval_state not in {"pending", "rejected", "needs_info"} and not hasattr(ticket, "tpa_transaction"):
                choices += [(value, label) for value, label in Ticket.Status.choices if value not in {Ticket.Status.NEW, Ticket.Status.CLOSED}]
            if TicketAccessPolicy.can_close(user, ticket):
                choices.append((Ticket.Status.CLOSED, _("Close ticket")))
            if not TicketAccessPolicy.can_view_internal_notes(user, ticket):
                self.fields.pop("is_internal", None)
        else:
            choices += [(value, label) for value, label in Ticket.Status.choices if value != Ticket.Status.NEW]
        self.fields["status"].choices = choices

class TicketEditForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ("subject", "description", "priority", "status")
        widgets = {
            "subject": forms.TextInput(attrs={"class": "form-control w-100"}),
            "description": forms.Textarea(attrs={"class": "form-control w-100 richtext-source", "rows": 8}),
            "priority": forms.Select(attrs={"class": "form-select w-100"}),
            "status": forms.Select(attrs={"class": "form-select w-100"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and (hasattr(self.instance,'tpa_transaction') or self.instance.status == Ticket.Status.CLOSED or self.instance.approval_state in {'pending','rejected','needs_info'}):
            self.fields['status'].disabled=True
        if user and not (user.is_superuser or user.has_perm("tickets.change_ticket")):
            self.fields.pop("priority", None)
            self.fields.pop("status", None)


class TicketAssignmentForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        required=False,
        queryset=get_user_model().objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-select w-100"}),
    )
    groups = forms.ModelMultipleChoiceField(
        required=False,
        queryset=SupportGroup.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-select w-100"}),
    )
    replace_existing = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    organization = forms.ModelChoiceField(required=False,queryset=Organization.objects.none(),widget=forms.Select(attrs={'class':'form-select w-100'}))
    support_group = forms.ModelChoiceField(required=False,queryset=SupportGroup.objects.none(),widget=forms.Select(attrs={'class':'form-select w-100'}))

    def __init__(self,*args,ticket=None,user=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['organization'].queryset = visible_organizations(user,ticket)
        org_id = selection_id(self.data.get('organization') or self.initial.get('organization'))
        org = self.fields['organization'].queryset.filter(pk=org_id).first() if org_id else None
        groups = assignable_groups(user,ticket,org) if ticket else visible_support_groups(user)
        group_id = selection_id(self.data.get('support_group') or self.initial.get('support_group'))
        group = groups.filter(pk=group_id).first() if group_id else None
        self.fields['support_group'].queryset = groups
        self.fields['groups'].queryset = groups
        self.fields['users'].queryset = (assignable_users(user,ticket,group,org) if ticket else visible_users(user)).prefetch_related('profile__organizations')
        if group_id and not group:self.fields['users'].queryset=self.fields['users'].queryset.none()
        if ticket and not self.is_bound:
            self.initial['users']=ticket.assignees.all();self.initial['groups']=ticket.groups.all()



class TicketShareForm(forms.Form):
    recipient = forms.ModelChoiceField(queryset=get_user_model().objects.none(), widget=forms.Select(attrs={"class": "form-select w-100"}))
    expires_in_days = forms.IntegerField(min_value=1, max_value=30, initial=7, widget=forms.NumberInput(attrs={"class": "form-control w-100"}))

    def __init__(self, *args, user=None, ticket=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = (taggable_users(user,ticket) if ticket else visible_users(user)).exclude(pk=getattr(user, "pk", None)).order_by("first_name", "last_name", "email")


class TicketApprovalDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", _("Approve")), ("reject", _("Reject")), ("needs_info", _("Request additional information"))], widget=RadioSelect(attrs={"class": "form-check-input"}))
    note = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"class": "form-control w-100", "rows": 3}))

    def clean(self):
        data = super().clean()
        if data.get("decision") in {"reject", "needs_info"} and not data.get("note", "").strip():
            self.add_error("note", _("Explain the rejection or information required."))
        return data


class TicketApprovalResubmitForm(forms.Form):
    note = forms.CharField(max_length=2000, label=_("Response to the approver"), widget=forms.Textarea(attrs={"class": "form-control w-100", "rows": 4}))


class TicketFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.SearchInput(attrs={"class": "form-control w-100", "placeholder": _("Search tickets")}))
    status = forms.ChoiceField(required=False, choices=[("", _("All statuses")), *Ticket.Status.choices], widget=forms.Select(attrs={"class": "form-select w-100"}))
    priority = forms.ChoiceField(required=False, choices=[("", _("All priorities")), *Ticket.Priority.choices], widget=forms.Select(attrs={"class": "form-select w-100"}))
    project = forms.ModelChoiceField(required=False, queryset=Project.objects.filter(is_active=True), empty_label=_("All projects"), widget=forms.Select(attrs={"class": "form-select w-100"}))
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.filter(is_active=True), empty_label=_("All categories"), widget=forms.Select(attrs={"class": "form-select w-100"}))
    organization = forms.ModelChoiceField(
        required=False,
        queryset=Organization.objects.none(),
        empty_label=_("All organizations"),
        widget=forms.Select(attrs={"class": "form-select w-100"}),
    )
    sla = forms.ChoiceField(required=False, choices=[("", _("All SLA states")), ("overdue", _("Overdue")), ("at_risk", _("At risk"))], widget=forms.Select(attrs={"class": "form-select w-100"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = accessible_projects(user) if user and user.is_authenticated else Project.objects.none()
        self.fields["category"].queryset = accessible_categories(user) if user and user.is_authenticated else Category.objects.none()
        organizations = Organization.objects.filter(is_active=True)
        if not user or not user.is_authenticated:
            organizations = organizations.none()
        elif not user.is_superuser:
            organizations = organizations.filter(pk__in=organization_ids(user))
        self.fields["organization"].queryset = organizations.order_by("organization_type", "name_en")


class DashboardFilterForm(TicketFilterForm):
    product = forms.ModelChoiceField(required=False, queryset=Product.objects.none(), empty_label=_("All products"), widget=forms.Select(attrs={"class": "form-select w-100"}))
    group = forms.ModelChoiceField(required=False, queryset=SupportGroup.objects.none(), empty_label=_("All support groups"), widget=forms.Select(attrs={"class": "form-select w-100"}))
    assignee = forms.ModelChoiceField(required=False, queryset=get_user_model().objects.none(), empty_label=_("All assignees"), widget=forms.Select(attrs={"class": "form-select w-100"}))
    request_type = forms.ChoiceField(required=False, choices=[("", _("All request types")), *Project.RequestType.choices], widget=forms.Select(attrs={"class": "form-select w-100"}))
    approval_state = forms.ChoiceField(required=False, choices=[("", _("All approval states")), *Ticket._meta.get_field("approval_state").choices], widget=forms.Select(attrs={"class": "form-select w-100"}))
    date_from = forms.DateField(required=False, label=_("Created from"), widget=forms.DateInput(attrs={"type": "date", "class": "form-control w-100"}))
    date_to = forms.DateField(required=False, label=_("Created through"), widget=forms.DateInput(attrs={"type": "date", "class": "form-control w-100"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        from services.access import TicketAccessPolicy
        from apps.tpa.services.access import visible_policies

        authenticated = bool(user and user.is_authenticated)
        visible = TicketAccessPolicy.visible_queryset(user).order_by() if authenticated else Ticket.objects.none()
        # Start again from the visible IDs so membership joins do not narrow
        # the other participants/options on a visible request.
        requests = Ticket.objects.filter(pk__in=visible.values("pk"))
        projects = self.fields["project"].queryset
        categories = self.fields["category"].queryset

        def options(model, allowed, existing, ordering):
            return model.objects.filter(Q(pk__in=allowed.order_by().values("pk")) | Q(pk__in=existing)).distinct().order_by(*ordering)

        def multiple_models(name, queryset, label, placeholder):
            self.fields[name] = forms.ModelMultipleChoiceField(required=False, queryset=queryset, label=label,
                widget=forms.SelectMultiple(attrs={"class": "form-select w-100", "data-placeholder": placeholder}))

        project_options = options(Project, projects, requests.values("project_id"), ("name_en", "pk"))
        category_options = options(Category, categories, requests.values("category_id"), ("name_en", "pk"))
        products = accessible_products(user) if authenticated else Product.objects.none()
        multiple_models("project", project_options, _("Projects"), _("All projects"))
        multiple_models("product", options(Product, products, requests.values("product_id"), ("name_en", "pk")), _("Products"), _("All products"))
        multiple_models("category", category_options, _("Categories / subcategories"), _("All categories"))
        organizations = Organization.objects.filter(
            Q(pk__in=visible_organizations(user).values("pk")) | Q(pk__in=requests.values("organization_id"))
            | Q(pk__in=TicketOrganization.objects.filter(ticket__in=requests, can_view=True).values("organization_id"))
        ).distinct().order_by("name_en", "pk")
        multiple_models("organization", organizations, _("Organizations"), _("All organizations"))
        multiple_models("organization_type", OrganizationType.objects.filter(code__in=organizations.values("organization_type_id")), _("Organization types"), _("All organization types"))
        policies = visible_policies(user) if authenticated else Policy.objects.none()
        multiple_models("policy", options(Policy, policies, requests.values("policy_id"), ("policy_number", "pk")), _("Policies"), _("All policies"))
        multiple_models("group", options(SupportGroup, visible_support_groups(user), requests.values("groups__pk"), ("name", "pk")), _("Support groups"), _("All support groups"))
        users = visible_users(user)
        User = get_user_model()
        assignees = User.objects.filter(Q(pk__in=users.values("pk")) | Q(pk__in=requests.values("assignee_id")) | Q(pk__in=requests.values("assignees__pk"))).distinct().order_by("first_name", "last_name", "username")
        multiple_models("assignee", assignees, _("Assignees"), _("All assignees"))
        multiple_models("requester", options(User, users, requests.values("requester_id"), ("first_name", "last_name", "username")), _("Requesters"), _("All requesters"))
        multiple_models("approver", options(User, users, requests.values("approvals__approver_id"), ("first_name", "last_name", "username")), _("Approvers"), _("All approvers"))
        sla_policies = SLAPolicy.objects.filter(is_active=True).filter(Q(project__in=project_options) | Q(category__in=category_options))
        multiple_models("sla_policy", options(SLAPolicy, sla_policies, requests.values("sla_policy_id"), ("name", "pk")), _("SLA policies"), _("All SLA policies"))
        for name in ("assignee", "requester", "approver"):
            self.fields[name].label_from_instance = lambda person: f"{person.get_full_name() or person.username}" + (f" ({person.email})" if person.email else "")

        request_types = set(project_options.values_list("request_type", flat=True))
        choice_specs = {
            "status": (Ticket.Status.choices, _("Statuses"), _("All statuses")),
            "priority": (Ticket.Priority.choices, _("Priorities"), _("All priorities")),
            "request_type": ([(value, label) for value, label in Project.RequestType.choices if value in request_types], _("Request types"), _("All request types")),
            "approval_state": (Ticket._meta.get_field("approval_state").choices, _("Approval states"), _("All approval states")),
            "visibility": (Ticket._meta.get_field("visibility").choices, _("Visibility"), _("All visibility levels")),
            "sla": ([("healthy", _("Healthy")), ("at_risk", _("At risk")), ("overdue", _("Overdue")), ("paused", _("Paused")), ("resolved", _("Resolved")), ("closed", _("Closed"))], _("SLA states"), _("All SLA states")),
        }
        for name, (choices, label, placeholder) in choice_specs.items():
            self.fields[name] = forms.MultipleChoiceField(required=False, choices=choices, label=label,
                widget=forms.SelectMultiple(attrs={"class": "form-select w-100", "data-placeholder": placeholder}))
        self.order_fields(["q", "project", "status", "request_type", "product", "category", "priority", "organization", "organization_type", "policy", "requester", "assignee", "group", "approver", "approval_state", "visibility", "sla", "sla_policy", "date_from", "date_to"])
        for field in self.fields.values():
            field.widget.attrs["form"] = "dashboard-filter-form"

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            self.add_error("date_to", _("The end date must be on or after the start date."))
        return data


class TicketParticipantForm(forms.Form):
    user = forms.ModelChoiceField(queryset=get_user_model().objects.none(),widget=forms.Select(attrs={'class':'form-select w-100'}))
    def __init__(self,*args,ticket,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['user'].queryset=taggable_users(user,ticket)

class TicketApprovalRequestForm(forms.Form):
    approver = forms.ModelChoiceField(queryset=get_user_model().objects.none(),widget=forms.Select(attrs={'class':'form-select w-100'}))
    note = forms.CharField(required=False,max_length=2000,widget=forms.Textarea(attrs={'class':'form-control w-100','rows':3}))
    def __init__(self,*args,ticket,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['approver'].queryset=available_approvers(user,ticket)

class UnifiedRequestForm(TicketCreateStep1Form):
    supports_business_requests = True
    request_type = forms.ChoiceField(choices=Project.RequestType.choices,widget=forms.Select(attrs={'class':'form-select w-100'}))
    effective_date = forms.DateField(required=False,widget=forms.DateInput(attrs={'type':'date','class':'form-control w-100'}))
    policy_type = forms.ChoiceField(required=False,choices=[],widget=forms.Select(attrs={'class':'form-select w-100'}))
    def __init__(self,*args,user=None,**kwargs):
        super().__init__(*args,user=user,**kwargs)
        kind=self.data.get('request_type') or self.initial.get('request_type') or Project.RequestType.SERVICE
        self.selected_request_type=kind
        self.fields['request_type'].initial=kind
        self.fields['project'].queryset=self.fields['project'].queryset.filter(request_type=kind)
        self.fields['policy'].required=kind in {'endorsement','claim'}
        self.fields['effective_date'].required=kind=='endorsement'
        product=self.fields['product'].queryset.filter(pk=selection_id(self.data.get('product') or self.initial.get('product'))).first()
        if product:self.fields['policy_type'].choices=[(v.get('code'),v.get('name',v.get('code'))) if isinstance(v,dict) else (v,str(v).replace('_',' ').title()) for v in product.policy_types]
        self.fields['policy_type'].required=kind=='policy'
        policy=self.fields['policy'].queryset.filter(pk=selection_id(self.data.get('policy') or self.initial.get('policy'))).first()
        if policy:
            code=policy.product.code if policy.product_id else policy.product_type
            self.fields['product'].queryset=self.fields['product'].queryset.filter(code=code)
            if self.fields['product'].queryset.count()==1:
                selected=self.fields['product'].queryset.first()
                self.initial['product']=selected.pk
                self.fields['category'].queryset=accessible_categories(user).filter(product=selected)
                if self.fields['category'].queryset.count()==1:self.initial['category']=self.fields['category'].queryset.first().pk
        for name in ['project','product','policy']:
            self.fields[name].widget.attrs.update({'hx-get':reverse('portal:create_request'),'hx-include':'closest form','hx-target':'#request-fields','hx-swap':'outerHTML','hx-trigger':'change','hx-indicator':'#request-loading'})
