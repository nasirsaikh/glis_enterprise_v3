from apps.accounts.models import Organization
from django import forms
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import AccountPolicy, UserProfile
from apps.tickets.models import SupportGroup


class OrganizationUserCreationForm(UserCreationForm):
    support_groups = forms.ModelMultipleChoiceField(queryset=SupportGroup.objects.none(),required=False,
        widget=FilteredSelectMultiple("support groups",is_stacked=False))
    organizations = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.filter(is_active=True).order_by("name_en"),
        required=False,
        widget=FilteredSelectMultiple("organizations", is_stacked=False),
        help_text="Select every organization this user is allowed to act for.",
    )


class OrganizationUserChangeForm(UserChangeForm):
    support_groups = forms.ModelMultipleChoiceField(queryset=SupportGroup.objects.none(),required=False,
        widget=FilteredSelectMultiple("support groups",is_stacked=False))
    organizations = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.filter(is_active=True).order_by("name_en"),
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
            self.fields["support_groups"].initial=self.instance.support_groups.all()


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
        ("Organizations", {"fields": ("organizations","support_groups")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Organizations", {"fields": ("organizations","support_groups")}),
    )

    def get_queryset(self, request):
        from services.tenancy import visible_users
        return super().get_queryset(request).filter(pk__in=visible_users(request.user).values('pk'))

    def get_form(self, request, obj=None, **kwargs):
        from services.tenancy import visible_organizations,visible_support_groups
        base=super().get_form(request,obj,**kwargs)
        class ScopedForm(base):
            def __init__(self,*args,**form_kwargs):
                super().__init__(*args,**form_kwargs)
                self.fields['organizations'].queryset=visible_organizations(request.user)
                self.fields['support_groups'].queryset=visible_support_groups(request.user)
        return ScopedForm

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "organizations" in form.cleaned_data:
            obj.profile.organizations.set(form.cleaned_data["organizations"])
        if "support_groups" in form.cleaned_data:obj.support_groups.set(form.cleaned_data["support_groups"])


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from services.tenancy import visible_users
        return super().get_queryset(request).filter(user_id__in=visible_users(request.user).values('pk'))
    def formfield_for_foreignkey(self,db_field,request,**kwargs):
        from services.tenancy import visible_users
        if db_field.remote_field.model is User:kwargs['queryset']=visible_users(request.user)
        return super().formfield_for_foreignkey(db_field,request,**kwargs)
    def formfield_for_manytomany(self,db_field,request,**kwargs):
        from services.tenancy import visible_organizations
        if db_field.remote_field.model is Organization:kwargs['queryset']=visible_organizations(request.user)
        return super().formfield_for_manytomany(db_field,request,**kwargs)

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
        ("Access", {"fields": ("is_external", "is_approved", "is_locked", "guest_access_expires_at")}),
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


from .models import OrganizationType

@admin.register(OrganizationType)
class OrganizationTypeAdmin(admin.ModelAdmin):
    list_display = ('code','name','display_order','is_active')
    search_fields = ('code','name')
    list_filter = ('is_active',)

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('code','name_en','organization_type','parent_organization','is_active')
    list_filter = ('organization_type','is_active')
    search_fields = ('code','name_en','name_ar','commercial_registration')
    autocomplete_fields = ('organization_type','parent_organization')
    readonly_fields = ('related_users','related_groups','related_policies','related_tickets')
    @admin.display(description='Linked users')
    def related_users(self,obj):
        return ', '.join(obj.user_profiles.values_list('user__username',flat=True)[:50]) or '—'
    @admin.display(description='Support groups')
    def related_groups(self,obj):
        return ', '.join(obj.support_groups.values_list('name',flat=True)[:50]) or '—'
    @admin.display(description='Policy count')
    def related_policies(self,obj):return obj.policies.count()
    @admin.display(description='Ticket count')
    def related_tickets(self,obj):return obj.tickets.count()
    def formfield_for_foreignkey(self,db_field,request,**kwargs):
        if db_field.name=='parent_organization':
            from services.tenancy import visible_organizations
            kwargs['queryset']=visible_organizations(request.user)
        return super().formfield_for_foreignkey(db_field,request,**kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:return qs
        from services.tenancy import organization_ids
        return qs.filter(pk__in=organization_ids(request.user))
