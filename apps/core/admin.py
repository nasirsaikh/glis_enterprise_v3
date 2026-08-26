from django.contrib import admin, messages
from django.utils import timezone
from .models import AuditLog, ConfigurationVersion, ModuleRegistry


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
