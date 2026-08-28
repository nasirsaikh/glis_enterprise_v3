from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import HomeCTAPlugin, HomeContentPlugin, HomeFAQPlugin, HomeFeaturePlugin, HomeHeroPlugin, HomeImagePlugin, HomePartnerPlugin, HomeProcessPlugin, HomeSectionHeaderPlugin, HomeServicePlugin, HomeStatisticPlugin, HomeTestimonialPlugin,DownloadDocument,DownloadCategory

admin.site.register(HomeHeroPlugin)
admin.site.register(HomeImagePlugin)
admin.site.register(HomeSectionHeaderPlugin)
admin.site.register(HomeContentPlugin)
admin.site.register(HomeServicePlugin)
admin.site.register(HomeFeaturePlugin)
admin.site.register(HomeProcessPlugin)
admin.site.register(HomeStatisticPlugin)
admin.site.register(HomeTestimonialPlugin)
admin.site.register(HomeFAQPlugin)
admin.site.register(HomePartnerPlugin)
admin.site.register(HomeCTAPlugin)

@admin.register(DownloadCategory)
class DownloadCategoryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "icon", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name_en", "name_ar")

@admin.register(DownloadDocument)
class DownloadDocumentAdmin(admin.ModelAdmin):
    list_display = ("title_en", "category", "version", "extension_display", "file_size", "is_featured", "is_active", "updated_at")
    list_filter = ("category", "is_featured", "is_active", "created_at")
    list_editable = ("is_featured", "is_active")
    search_fields = ("title_en", "title_ar", "description_en", "description_ar", "reference")
    readonly_fields = ("download_count", "created_at", "updated_at")
    fieldsets = (
        (_("Document"), {"fields": ("category", "file")}),
        (_("English"), {"fields": ("title_en", "description_en")}),
        (_("Arabic"), {"fields": ("title_ar", "description_ar")}),
        (_("Additional Information"), {"fields": ("version", "reference", "order")}),
        (_("Publishing"), {"fields": ("is_featured", "is_active")}),
        (_("Statistics"), {"fields": ("download_count", "created_at", "updated_at")}),
    )

    @admin.display(description="Type")
    def extension_display(self, obj):
        return obj.extension.upper()

    @admin.display(description="Size")
    def file_size(self, obj):
        return obj.file_size_display
