from django.contrib import admin
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
    fieldsets = (
        ("Identity", {"fields": ("site_name_en", "site_name_ar", "short_name", "tagline_en", "tagline_ar", "logo", "favicon")}),
        ("Contact", {"fields": ("contact_email", "contact_phone", "address_en", "address_ar", "organization_details", "social_links")}),
        ("Public access", {"fields": ("public_registration_enabled", "public_theme_switcher_enabled")}),
    )


@admin.register(ThemeSettings)
class ThemeSettingsAdmin(SingletonAdmin):
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm("app_settings.manage_theme")


class PageSectionInline(admin.StackedInline):
    model = PageSection
    extra = 0


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title_en", "slug", "audience", "state", "is_visible", "publication_date", "updated_at")
    list_filter = ("audience", "state", "is_visible", "layout")
    search_fields = ("title_en", "title_ar", "slug")
    prepopulated_fields = {"slug": ("title_en",)}
    filter_horizontal = ("allowed_groups",)
    inlines = [PageSectionInline]


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
admin.site.register(ContentVersion)
