from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from apps.ai.models import default_questions
from .models import Category, Product, Project, SupportGroup, Ticket, TicketComment


class TicketCreateStep1Form(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none(), widget=forms.Select(attrs={"class": "form-select", "hx-get": "/portal/lookups/products/", "hx-target": "#id_product", "hx-trigger": "change"}))
    product = forms.ModelChoiceField(queryset=Product.objects.none(), widget=forms.Select(attrs={"class": "form-select", "hx-get": "/portal/lookups/categories/", "hx-target": "#id_category", "hx-trigger": "change"}))
    category = forms.ModelChoiceField(queryset=Category.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(is_active=True)
        project_id = self.data.get("project") or self.initial.get("project")
        product_id = self.data.get("product") or self.initial.get("product")
        self.fields["product"].queryset = Product.objects.filter(is_active=True, project_id=project_id) if project_id else Product.objects.none()
        self.fields["category"].queryset = Category.objects.filter(is_active=True, product_id=product_id) if product_id else Category.objects.none()


class TicketIntakeForm(forms.Form):
    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = (questions or default_questions())[:4]
        while len(self.questions) < 4:
            self.questions.append(default_questions()[len(self.questions)])
        for index, question in enumerate(self.questions, start=1):
            self.fields[f"answer_{index}"] = forms.CharField(
                label=_(question["text"]), required=not question.get("optional", False),
                widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "data-question": index}),
                help_text=_("Optional") if question.get("optional") else "",
            )


class TicketReviewForm(forms.Form):
    subject = forms.CharField(max_length=240, widget=forms.TextInput(attrs={"class": "form-control"}))
    description = forms.CharField(max_length=2_000_000, widget=forms.Textarea(attrs={"class": "form-control richtext-source", "rows": 6}))
    priority = forms.ChoiceField(choices=Ticket.Priority.choices, widget=forms.Select(attrs={"class": "form-select"}))
    acknowledgment = forms.BooleanField(label=_("I confirm that the information is accurate and may be processed to provide this service."))


class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ("body", "is_internal")
        widgets = {"body": forms.Textarea(attrs={"class": "form-control richtext-source", "rows": 3, "placeholder": _("Write an update…")}), "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"})}


class TicketEditForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ("subject", "description", "priority", "status")
        widgets = {
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control richtext-source", "rows": 8}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not (user.is_superuser or user.has_perm("tickets.change_ticket")):
            self.fields.pop("priority", None)
            self.fields.pop("status", None)


class TicketAssignmentForm(forms.Form):
    users = forms.ModelMultipleChoiceField(required=False, queryset=get_user_model().objects.none(), widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 7}))
    groups = forms.ModelMultipleChoiceField(required=False, queryset=SupportGroup.objects.none(), widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 7}))
    replace_existing = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, ticket=None, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["users"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name", "email")
        self.fields["groups"].queryset = SupportGroup.objects.filter(is_active=True).order_by("name")
        if ticket and not self.is_bound:
            self.initial["users"] = ticket.assignees.all()
            self.initial["groups"] = ticket.groups.all()


class TicketShareForm(forms.Form):
    recipient = forms.ModelChoiceField(queryset=get_user_model().objects.none(), widget=forms.Select(attrs={"class": "form-select"}))
    expires_in_days = forms.IntegerField(min_value=1, max_value=30, initial=7, widget=forms.NumberInput(attrs={"class": "form-control"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = get_user_model().objects.filter(is_active=True).exclude(pk=getattr(user, "pk", None)).order_by("first_name", "last_name", "email")


class TicketApprovalDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", _("Approve")), ("reject", _("Reject"))], widget=forms.RadioSelect)
    note = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))


class TicketFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.SearchInput(attrs={"class": "form-control", "placeholder": _("Search tickets")}))
    status = forms.ChoiceField(required=False, choices=[("", _("All statuses")), *Ticket.Status.choices], widget=forms.Select(attrs={"class": "form-select"}))
    priority = forms.ChoiceField(required=False, choices=[("", _("All priorities")), *Ticket.Priority.choices], widget=forms.Select(attrs={"class": "form-select"}))
    project = forms.ModelChoiceField(required=False, queryset=Project.objects.filter(is_active=True), empty_label=_("All projects"), widget=forms.Select(attrs={"class": "form-select"}))
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.filter(is_active=True), empty_label=_("All categories"), widget=forms.Select(attrs={"class": "form-select"}))
    sla = forms.ChoiceField(required=False, choices=[("", _("All SLA states")), ("overdue", _("Overdue")), ("at_risk", _("At risk"))], widget=forms.Select(attrs={"class": "form-select"}))
