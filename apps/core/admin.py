from django.contrib import admin, messages
from django.utils import timezone
from .models import *


@admin.register(ModuleRegistry)
class ModuleRegistryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "key", "is_enabled", "show_in_navigation", "order")
    list_editable = ("is_enabled", "show_in_navigation", "order")
    search_fields = ("name_en", "name_ar", "key")


@admin.register(ConfigurationVersion)
class ConfigurationVersionAdmin(admin.ModelAdmin):
    list_display = ("key", "version", "state", "created_by", "created_at", "published_at")
    list_filter = ("state", "key")
    readonly_fields = ("created_at", "updated_at")
    actions = ("validate_selected", "publish_selected")

    @admin.action(description="Validate selected JSON configuration")
    def validate_selected(self, request, queryset):
        for config in queryset:
            errors = [] if isinstance(config.payload, dict) else [{"line": 1, "message": "The root JSON value must be an object."}]
            config.validation_errors = errors
            config.save(update_fields=["validation_errors", "updated_at"])
        self.message_user(request, "Configuration validation completed.")

    @admin.action(description="Publish selected valid configuration")
    def publish_selected(self, request, queryset):
        if not request.user.is_superuser and not request.user.has_perm("core.manage_json_config"):
            self.message_user(request, "You do not have permission to publish configuration.", messages.ERROR)
            return
        for config in queryset:
            if config.validation_errors or not isinstance(config.payload, dict):
                self.message_user(request, f"{config.key} v{config.version} is not valid.", messages.ERROR)
                continue
            ConfigurationVersion.objects.filter(key=config.key, state="published").exclude(pk=config.pk).update(state="archived")
            config.state, config.published_at = "published", timezone.now()
            config.save(update_fields=["state", "published_at", "updated_at"])


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "summary", "sensitivity")
    list_filter = ("action", "sensitivity", "object_type")
    search_fields = ("summary", "object_id", "actor__email")
    readonly_fields = [field.name for field in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Company Information", {"fields": ("site_name_en", "site_name_ar", "short_name", "tagline_en", "tagline_ar", "organization_details")}),
        ("Registration Details", {"fields": ("commercial_registration_no", "vat_registration_no", "license_no", "established_year")}),
        ("Contact Information", {"fields": ("contact_email", "support_email", "contact_phone", "secondary_phone", "whatsapp_number", "website")}),
        ("Address", {"fields": ("address_en", "address_ar", "city", "governorate", "country", "po_box", "postal_code")}),
        ("Map Location", {"fields": ("latitude", "longitude", "map_zoom")}),
        ("Branding", {"fields": ("logo", "favicon")}),
        ("Working Hours", {"fields": ("working_hours_en", "working_hours_ar")}),
        ("Social Links", {"fields": ("social_links",)}),
        ("Public Website Settings", {"fields": ("public_registration_enabled", "public_theme_switcher_enabled")}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name_en", "name_ar")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title_en", "category", "is_featured", "order", "is_active")
    list_filter = ("category", "is_featured", "is_active")
    list_editable = ("is_featured", "order", "is_active")
    search_fields = ("title_en", "title_ar", "summary_en", "summary_ar")


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("title_en", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("title_en", "title_ar")


@admin.register(Statistic)
class StatisticAdmin(admin.ModelAdmin):
    list_display = ("value", "suffix", "label_en", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(ProcessStep)
class ProcessStepAdmin(admin.ModelAdmin):
    list_display = ("step_number", "title_en", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "role_en", "rating", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question_en", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("question_en", "question_ar")


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(HomeSection)
class HomeSectionAdmin(admin.ModelAdmin):
    list_display = ("section", "title_en", "is_active")
    list_editable = ("is_active",)


admin.site.register(HeroSection)