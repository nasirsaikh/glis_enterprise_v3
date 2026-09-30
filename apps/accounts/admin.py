from django import forms
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.tpa.models import TPAOrganization

from .models import AccountPolicy, UserProfile


class OrganizationUserCreationForm(UserCreationForm):
    organizations = forms.ModelMultipleChoiceField(
        queryset=TPAOrganization.objects.filter(is_active=True).order_by("name_en"),
        required=False,
        widget=FilteredSelectMultiple("organizations", is_stacked=False),
        help_text="Select every organization this user is allowed to act for.",
    )


class OrganizationUserChangeForm(UserChangeForm):
    organizations = forms.ModelMultipleChoiceField(
        queryset=TPAOrganization.objects.filter(is_active=True).order_by("name_en"),
        required=False,
        widget=FilteredSelectMultiple("organizations", is_stacked=False),
        help_text="Select every organization this user is allowed to act for.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            profile = getattr(self.instance, "profile", None)
            if profile:
                self.fields["organizations"].initial = profile.organizations.all()


User = get_user_model()
try:
    admin.site.unregister(User)
except NotRegistered:
    pass


@admin.register(User)
class PortalUserAdmin(DjangoUserAdmin):
    add_form = OrganizationUserCreationForm
    form = OrganizationUserChangeForm
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Organizations", {"fields": ("organizations",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Organizations", {"fields": ("organizations",)}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "organizations" in form.cleaned_data:
            obj.profile.organizations.set(form.cleaned_data["organizations"])


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "department",
        "organization_summary",
        "reporting_manager",
        "is_external",
        "is_approved",
    )
    list_filter = (
        "role",
        ("organizations", admin.RelatedOnlyFieldListFilter),
        "is_external",
        "is_approved",
    )
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "organization",
        "organizations__code",
        "organizations__name_en",
        "organizations__name_ar",
    )
    filter_horizontal = ("organizations",)
    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "user",
                    "role",
                    "avatar",
                    "phone",
                    "organizations",
                    "job_title",
                    "department",
                    "bio",
                )
            },
        ),
        ("Reporting", {"fields": ("reporting_manager",)}),
        (
            "Preferences",
            {
                "fields": (
                    "preferred_language",
                    "theme",
                    "sidebar_mode",
                    "email_notifications",
                    "browser_notifications",
                )
            },
        ),
        ("Access", {"fields": ("is_external", "is_approved", "guest_access_expires_at")}),
        (
            "Legacy",
            {
                "fields": ("organization",),
                "classes": ("collapse",),
                "description": "Deprecated free-text organization retained for backwards compatibility.",
            },
        ),
    )

    @admin.display(description="Organizations")
    def organization_summary(self, obj):
        names = list(obj.organizations.values_list("name_en", flat=True)[:4])
        if not names:
            return obj.organization or "—"
        suffix = " …" if obj.organizations.count() > 4 else ""
        return ", ".join(names) + suffix


@admin.register(AccountPolicy)
class AccountPolicyAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Registration",
            {
                "fields": (
                    "public_registration_enabled",
                    "external_users_require_approval",
                    "default_external_role",
                    "default_external_group",
                )
            },
        ),
        (
            "Identity providers",
            {
                "fields": (
                    "google_login_enabled",
                    "microsoft_login_enabled",
                    "allowed_email_domains",
                )
            },
        ),
        ("Guest access", {"fields": ("guest_ticket_visibility",)}),
    )

    def has_add_permission(self, request):
        return not AccountPolicy.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
