from django.contrib import admin, messages
from django.utils import timezone
from apps.core.models import AuditLog
from .models import (
    AnimationPreset, ContentVersion, HeroSection, NavigationItem, Page, PageSection,
    Service, ServiceCategory, SiteSettings, Statistic, Testimonial, ThemeSettings,
)


class SingletonAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    fieldsets = (("Identity", {"fields": ("site_name_en", "site_name_ar", "short_name", "tagline_en", "tagline_ar", "logo", "favicon")}),
                 ("Contact", {"fields": ("contact_email", "contact_phone", "address_en", "address_ar", "organization_details", "social_links")}),
                 ("Public access", {"fields": ("public_registration_enabled", "public_theme_switcher_enabled")}))


@admin.register(ThemeSettings)
class ThemeSettingsAdmin(SingletonAdmin):
    fieldsets = (("Palette", {"fields": ("primary", "primary_dark", "secondary", "accent", "background", "surface", "text", "muted_text", "warning", "danger", "information")}),
                 ("Shape and type", {"fields": ("radius_px", "shadow_intensity", "font_family")}),
                 ("Preferences", {"fields": ("default_theme", "users_may_choose_theme", "animations_enabled")}),
                 ("Advanced", {"fields": ("custom_css",), "description": "Restricted to trusted Super Admins. Content Security Policy remains active."}))

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm("cms.manage_theme")

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        return fields if request.user.is_superuser else [field for field in fields if field != "custom_css"]


class PageSectionInline(admin.StackedInline):
    model = PageSection
    extra = 0
    fields = ("section_type", "title_en", "title_ar", "content_en", "content_ar", "order", "is_visible", "animation", "animation_duration_ms", "animation_delay_ms", "animate_once")


@admin.action(description="Publish selected pages")
def publish_pages(modeladmin, request, queryset):
    if not request.user.has_perm("cms.publish_page") and not request.user.is_superuser:
        modeladmin.message_user(request, "You do not have permission to publish pages.", messages.ERROR)
        return
    for page in queryset:
        version = page.versions.count() + 1
        ContentVersion.objects.create(page=page, version=version, created_by=request.user, change_note="Snapshot before publish", snapshot={
            "title_en": page.title_en, "title_ar": page.title_ar, "body_en": page.body_en, "body_ar": page.body_ar,
        })
        page.state, page.publication_date, page.updated_by = Page.State.PUBLISHED, timezone.now(), request.user
        page.save(update_fields=["state", "publication_date", "updated_by", "updated_at"])
        AuditLog.record(request=request, action="cms.publish", instance=page, summary=f"Published page {page.slug}")


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title_en", "slug", "audience", "state", "is_visible", "publication_date", "updated_at")
    list_filter = ("audience", "state", "is_visible", "layout")
    search_fields = ("title_en", "title_ar", "slug")
    prepopulated_fields = {"slug": ("title_en",)}
    filter_horizontal = ("allowed_groups",)
    fieldsets = (
        ("Page identity", {"fields": ("slug", "title_en", "title_ar", "summary_en", "summary_ar")}),
        ("Page content", {"fields": ("body_en", "body_ar", "layout", "portal_icon", "disable_animations")}),
        ("Publication & access", {"fields": ("audience", "state", "is_visible", "publication_date", "allowed_groups", "updated_by")}),
        ("Search metadata", {"fields": ("seo_title_en", "seo_title_ar", "seo_description_en", "seo_description_ar"), "classes": ("collapse",)}),
    )
    inlines = [PageSectionInline]
    actions = [publish_pages]


@admin.register(NavigationItem)
class NavigationItemAdmin(admin.ModelAdmin):
    list_display = ("label_en", "location", "section", "route_name", "url", "linked_page", "order", "is_visible")
    list_editable = ("order", "is_visible")
    list_filter = ("location", "section", "is_visible", "staff_only", "emphasized")
    search_fields = ("label_en", "label_ar", "route_name", "url", "required_permission")
    filter_horizontal = ("allowed_groups",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title_en", "category", "is_featured", "is_active", "order")
    list_editable = ("is_featured", "is_active", "order")
    list_filter = ("category", "is_active", "is_featured")


admin.site.register(ServiceCategory)
admin.site.register(Statistic)
admin.site.register(Testimonial)
admin.site.register(HeroSection, SingletonAdmin)
admin.site.register(AnimationPreset)


@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    list_display = ("page", "version", "created_by", "created_at", "change_note")
    actions = ("restore_selected",)

    @admin.action(description="Restore selected snapshot as a new draft")
    def restore_selected(self, request, queryset):
        if not request.user.is_superuser and not request.user.has_perm("cms.publish_page"):
            self.message_user(request, "You do not have permission to restore content.", messages.ERROR)
            return
        for version in queryset.select_related("page"):
            page = version.page
            for field in ("title_en", "title_ar", "body_en", "body_ar"):
                if field in version.snapshot:
                    setattr(page, field, version.snapshot[field])
            page.state, page.updated_by = Page.State.DRAFT, request.user
            page.save()
            AuditLog.record(request=request, action="cms.restore", instance=page, summary=f"Restored page from version {version.version}")
admin.site.site_header = "GLIS Administration"
admin.site.site_title = "GLIS Admin"
admin.site.index_title = "Enterprise platform control center"
