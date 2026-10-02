from django import forms
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.tickets.models import Category, Product, Project, Ticket
from apps.tickets.services.access import accessible_categories, accessible_products, accessible_projects

from .models import Task
from services.tenancy import visible_users


class TaskForm(forms.ModelForm):
    status = forms.ChoiceField(choices=Ticket.Status.choices, required=True)

    class Meta:
        model = Task
        fields = (
            "title",
            "description",
            "project",
            "product",
            "category",
            "priority",
            "owner",
            "tagged_users",
            "due_date",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control w-100"}),
            "description": forms.Textarea(attrs={"class": "form-control w-100", "rows": 2}),
            "project": forms.Select(attrs={"class": "form-select w-100"}),
            "product": forms.Select(attrs={"class": "form-select w-100"}),
            "category": forms.Select(attrs={"class": "form-select w-100"}),
            "priority": forms.Select(attrs={"class": "form-select w-100"}),
            "owner": forms.Select(attrs={"class": "form-select w-100"}),
            "tagged_users": forms.SelectMultiple(attrs={"class": "form-select w-100"}),
            "due_date": forms.DateInput(attrs={"class": "form-control w-100", "type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        User = get_user_model()
        self.fields["owner"].queryset = visible_users(user).order_by("first_name", "last_name", "email")
        self.fields["tagged_users"].queryset = self.fields["owner"].queryset
        self.fields["status"].widget.attrs["class"] = "form-select w-100"

        if user and user.is_authenticated:
            if user.is_superuser:
                projects = Project.objects.filter(is_active=True)
                products = Product.objects.filter(is_active=True)
                categories = Category.objects.filter(is_active=True)
            else:
                projects = accessible_projects(user)
                products = accessible_products(user)
                categories = accessible_categories(user)

                # A task owner may have received an admin-created task for a
                # category outside their normal request-creation catalogue.
                # Keep the task's current hierarchy selectable so an allowed
                # owner can edit the occurrence without broadening access to
                # unrelated projects/products/categories.
                if self.instance.pk:
                    projects = (projects | Project.objects.filter(pk=self.instance.project_id)).distinct()
                    products = (products | Product.objects.filter(pk=self.instance.product_id)).distinct()
                    categories = (categories | Category.objects.filter(pk=self.instance.category_id)).distinct()

            self.fields["project"].queryset = projects.order_by("name_en")

            project_id = self.data.get("project") or getattr(self.instance, "project_id", None)
            product_id = self.data.get("product") or getattr(self.instance, "product_id", None)
            self.fields["product"].queryset = products.filter(project_id=project_id).order_by("name_en") if project_id else products.none()
            self.fields["category"].queryset = categories.filter(product_id=product_id).order_by("name_en") if product_id else categories.none()

        self.fields["project"].widget.attrs.update({
            "hx-get": reverse("portal:product_options"),
            "hx-target": "#id_product",
            "hx-trigger": "change",
        })
        self.fields["product"].widget.attrs.update({
            "hx-get": reverse("portal:category_options"),
            "hx-target": "#id_category",
            "hx-trigger": "change",
        })
        if self.instance.pk and self.instance.ticket_id:
            self.fields["status"].initial = self.instance.ticket.status
        else:
            self.fields["status"].initial = Ticket.Status.NEW

    def clean(self):
        cleaned = super().clean()
        project = cleaned.get("project")
        product = cleaned.get("product")
        category = cleaned.get("category")
        if project and product and product.project_id != project.pk:
            self.add_error("product", "The selected product does not belong to the selected project.")
        if product and category and category.product_id != product.pk:
            self.add_error("category", "The selected category does not belong to the selected product.")
        return cleaned
