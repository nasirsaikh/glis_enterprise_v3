from apps.accounts.models import Organization
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from apps.ai.models import default_questions
from apps.core.widgets import CheckboxSelectMultiple, RadioSelect
from .models import Category, Product, Project, SupportGroup, Ticket, TicketComment
from services.tenancy import organization_ids, visible_support_groups, visible_users, visible_organizations, assignable_groups, assignable_users, taggable_users, available_approvers
from apps.tpa.models import Policy
from .services.access import accessible_categories,accessible_products,accessible_projects

def selection_id(value):
    value=str(value or '')
    return int(value) if value.isascii() and value.isdigit() else None


class TicketCreateStep1Form(forms.Form):
    supports_business_requests = False
    organization = forms.ModelChoiceField(required=False,queryset=Organization.objects.none(),widget=forms.Select(attrs={'class':'select select-bordered w-full'}))
    policy = forms.ModelChoiceField(required=False,queryset=Policy.objects.none(),widget=forms.Select(attrs={'class':'select select-bordered w-full'}))


    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
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
                "class": "select select-bordered w-full",
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
                "class": "select select-bordered w-full",
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
                widget=forms.Textarea(attrs={"class": "textarea textarea-bordered w-full", "rows": 3, "data-question": index}),
                help_text=_("Optional") if question.get("optional") else "",
            )


class TicketReviewForm(forms.Form):
    subject = forms.CharField(max_length=240, widget=forms.TextInput(attrs={"class": "input input-bordered w-full"}))
    description = forms.CharField(max_length=2_000_000, widget=forms.Textarea(attrs={"class": "textarea textarea-bordered w-full richtext-source", "rows": 6}))
    priority = forms.ChoiceField(choices=Ticket.Priority.choices, widget=forms.Select(attrs={"class": "select select-bordered w-full"}))
    acknowledgment = forms.BooleanField(label=_("I confirm that the information is accurate and may be processed to provide this service."), widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}))


# class TicketCommentForm(forms.ModelForm):
#     class Meta:
#         model = TicketComment
#         fields = ("body", "is_internal")
#         widgets = {"body": forms.Textarea(attrs={"class": "textarea textarea-bordered w-full richtext-source", "rows": 3, "placeholder": _("Write an update…")}), "is_internal": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"})}

class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body","status", "is_internal"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full richtext-source",
                    "rows": 3,
                    "placeholder": "Write an update…",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "is_internal": forms.CheckboxInput(
                attrs={
                    "class": "toggle toggle-primary",
                    "role": "switch",
                }
            ),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].required = False
        self.fields["body"].widget.attrs.pop("required", None)
        self.fields["status"].required = True        

class TicketEditForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ("subject", "description", "priority", "status")
        widgets = {
            "subject": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(attrs={"class": "textarea textarea-bordered w-full richtext-source", "rows": 8}),
            "priority": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and hasattr(self.instance,'tpa_transaction'):
            self.fields['status'].disabled=True
        if user and not (user.is_superuser or user.has_perm("tickets.change_ticket")):
            self.fields.pop("priority", None)
            self.fields.pop("status", None)


class TicketAssignmentForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        required=False,
        queryset=get_user_model().objects.none(),
        widget=CheckboxSelectMultiple(attrs={"class": "checkbox checkbox-primary"}),
    )
    groups = forms.ModelMultipleChoiceField(
        required=False,
        queryset=SupportGroup.objects.none(),
        widget=CheckboxSelectMultiple(attrs={"class": "checkbox checkbox-primary"}),
    )
    replace_existing = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
    )

    organization = forms.ModelChoiceField(required=False,queryset=Organization.objects.none(),widget=forms.Select(attrs={'class':'select select-bordered w-full'}))
    support_group = forms.ModelChoiceField(required=False,queryset=SupportGroup.objects.none(),widget=forms.Select(attrs={'class':'select select-bordered w-full'}))

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
    recipient = forms.ModelChoiceField(queryset=get_user_model().objects.none(), widget=forms.Select(attrs={"class": "select select-bordered w-full"}))
    expires_in_days = forms.IntegerField(min_value=1, max_value=30, initial=7, widget=forms.NumberInput(attrs={"class": "input input-bordered w-full"}))

    def __init__(self, *args, user=None, ticket=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = (taggable_users(user,ticket) if ticket else visible_users(user)).exclude(pk=getattr(user, "pk", None)).order_by("first_name", "last_name", "email")


class TicketApprovalDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", _("Approve")), ("reject", _("Reject"))], widget=RadioSelect(attrs={"class": "radio radio-primary"}))
    note = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"class": "textarea textarea-bordered w-full", "rows": 3}))


class TicketFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.SearchInput(attrs={"class": "input input-bordered w-full", "placeholder": _("Search tickets")}))
    status = forms.ChoiceField(required=False, choices=[("", _("All statuses")), *Ticket.Status.choices], widget=forms.Select(attrs={"class": "select select-bordered w-full"}))
    priority = forms.ChoiceField(required=False, choices=[("", _("All priorities")), *Ticket.Priority.choices], widget=forms.Select(attrs={"class": "select select-bordered w-full"}))
    project = forms.ModelChoiceField(required=False, queryset=Project.objects.filter(is_active=True), empty_label=_("All projects"), widget=forms.Select(attrs={"class": "select select-bordered w-full"}))
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.filter(is_active=True), empty_label=_("All categories"), widget=forms.Select(attrs={"class": "select select-bordered w-full"}))
    organization = forms.ModelChoiceField(
        required=False,
        queryset=Organization.objects.none(),
        empty_label=_("All organizations"),
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )
    sla = forms.ChoiceField(required=False, choices=[("", _("All SLA states")), ("overdue", _("Overdue")), ("at_risk", _("At risk"))], widget=forms.Select(attrs={"class": "select select-bordered w-full"}))

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


class TicketParticipantForm(forms.Form):
    user = forms.ModelChoiceField(queryset=get_user_model().objects.none(),widget=forms.Select(attrs={'class':'select select-bordered w-full'}))
    def __init__(self,*args,ticket,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['user'].queryset=taggable_users(user,ticket)

class TicketApprovalRequestForm(forms.Form):
    approver = forms.ModelChoiceField(queryset=get_user_model().objects.none(),widget=forms.Select(attrs={'class':'select select-bordered w-full'}))
    note = forms.CharField(required=False,max_length=2000,widget=forms.Textarea(attrs={'class':'textarea textarea-bordered w-full','rows':3}))
    def __init__(self,*args,ticket,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['approver'].queryset=available_approvers(user,ticket)

class UnifiedRequestForm(TicketCreateStep1Form):
    supports_business_requests = True
    request_type = forms.ChoiceField(choices=Project.RequestType.choices,widget=forms.Select(attrs={'class':'select select-bordered w-full'}))
    effective_date = forms.DateField(required=False,widget=forms.DateInput(attrs={'type':'date','class':'input input-bordered w-full'}))
    policy_type = forms.ChoiceField(required=False,choices=[],widget=forms.Select(attrs={'class':'select select-bordered w-full'}))
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
