from django.contrib import admin
from .models import AccountPolicy, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "department", "organization", "reporting_manager", "is_external", "is_approved")
    list_filter = ("role", "is_external", "is_approved")
    search_fields = ("user__email", "user__first_name", "user__last_name", "organization")
    fieldsets = (
        ("Identity", {"fields": ("user", "role", "avatar", "phone", "organization", "job_title", "department", "bio")}),
        ("Reporting", {"fields": ("reporting_manager",)}),
        ("Preferences", {"fields": ("preferred_language", "theme", "sidebar_mode", "email_notifications", "browser_notifications")}),
        ("Access", {"fields": ("is_external", "is_approved", "guest_access_expires_at")}),
    )


@admin.register(AccountPolicy)
class AccountPolicyAdmin(admin.ModelAdmin):
    fieldsets = (("Registration", {"fields": ("public_registration_enabled", "external_users_require_approval", "default_external_role", "default_external_group")}),
                 ("Identity providers", {"fields": ("google_login_enabled", "microsoft_login_enabled", "allowed_email_domains")}),
                 ("Guest access", {"fields": ("guest_ticket_visibility",)}))

    def has_add_permission(self, request):
        return not AccountPolicy.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
