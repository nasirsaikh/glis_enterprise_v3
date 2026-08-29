from django.contrib import admin, messages
from django.utils import timezone
from .models import (
    ModuleRegistry,
    ConfigurationVersion,
    AuditLog,
    SiteSettings,
    ServiceCategory,
    Service,
    Feature,
    Statistic,
    ProcessStep,
    Testimonial,
    FAQ,
    Partner,
    HomeSection,
    HeroSection,
    ManagementMember,
    InsurancePartner,
    ProviderType,
    Governorate,
    City,
    MedicalSpecialty,
    NetworkProvider,
    TPAService,
    MedicalProcessStep,
    MedicalContact,
    DownloadCategory,
    DownloadDocument,
)


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


@admin.register(HeroSection)
class HeroSectionAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not HeroSection.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================
# MANAGEMENT / LEADERSHIP ADMIN
# ============================================================

@admin.register(ManagementMember)
class ManagementMemberAdmin(admin.ModelAdmin):
    list_display = ("name_en", "designation_en", "department_en", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name_en", "name_ar", "designation_en", "department_en")
    list_filter = ("is_active", "department_en")


# ============================================================
# HEALTH INSURANCE PARTNERS ADMIN
# ============================================================

@admin.register(InsurancePartner)
class InsurancePartnerAdmin(admin.ModelAdmin):
    list_display = ("name_en", "short_name", "sort_order", "is_featured", "is_active")
    list_editable = ("sort_order", "is_featured", "is_active")
    search_fields = ("name_en", "name_ar", "short_name")
    list_filter = ("is_featured", "is_active")


# ============================================================
# NETWORK PROVIDER TYPES ADMIN
# ============================================================

@admin.register(ProviderType)
class ProviderTypeAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name_en", "name_ar")


# ============================================================
# LOCATION / GOVERNORATE ADMIN
# ============================================================

@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "code", "is_active")
    list_editable = ("code", "is_active")
    search_fields = ("name_en", "name_ar", "code")


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name_en", "governorate", "name_ar", "is_active")
    list_editable = ("is_active",)
    list_filter = ("governorate", "is_active")
    search_fields = ("name_en", "name_ar")


# ============================================================
# MEDICAL SPECIALTIES ADMIN
# ============================================================

@admin.register(MedicalSpecialty)
class MedicalSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("name_en", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name_en", "name_ar")


# ============================================================
# NETWORK PROVIDERS ADMIN
# ============================================================

@admin.register(NetworkProvider)
class NetworkProviderAdmin(admin.ModelAdmin):
    list_display = (
        "provider_code",
        "name_en",
        "provider_type",
        "governorate",
        "city",
        "network_level",
        "is_featured",
        "is_active",
    )
    list_filter = (
        "provider_type",
        "governorate",
        "city",
        "network_level",
        "is_featured",
        "is_active",
        "has_emergency",
        "has_pharmacy",
    )
    search_fields = ("provider_code", "name_en", "name_ar", "phone", "email")
    list_editable = ("is_featured", "is_active")
    filter_horizontal = ("specialties", "insurance_partners")
    fieldsets = (
        ("Basic Information", {"fields": ("provider_code", "name_en", "name_ar", "provider_type", "network_level", "logo")}),
        ("Associations", {"fields": ("specialties", "insurance_partners")}),
        ("Location & Address", {"fields": ("address_en", "address_ar", "governorate", "city", "area_en", "area_ar", "postal_code")}),
        ("Map Coordinates", {"fields": ("latitude", "longitude", "google_maps_url")}),
        ("Contact Details", {"fields": ("phone", "emergency_phone", "email", "website_url")}),
        ("Facilities & Hours", {"fields": ("working_hours_en", "working_hours_ar", "is_24_hours", "has_emergency", "has_pharmacy", "has_dental", "has_optical")}),
        ("Status & Ordering", {"fields": ("is_featured", "is_active", "sort_order")}),
    )


# ============================================================
# TPA / MEDICAL SERVICES ADMIN
# ============================================================

@admin.register(TPAService)
class TPAServiceAdmin(admin.ModelAdmin):
    list_display = ("title_en", "sort_order", "is_featured", "is_active")
    list_editable = ("sort_order", "is_featured", "is_active")
    search_fields = ("title_en", "title_ar")
    list_filter = ("is_featured", "is_active")


# ============================================================
# CLAIM / PRE-AUTH PROCESS ADMIN
# ============================================================

@admin.register(MedicalProcessStep)
class MedicalProcessStepAdmin(admin.ModelAdmin):
    list_display = ("process_type", "step_number", "title_en", "is_active")
    list_editable = ("is_active",)
    list_filter = ("process_type", "is_active")
    search_fields = ("title_en", "title_ar")


# ============================================================
# EMERGENCY / IMPORTANT CONTACTS ADMIN
# ============================================================

@admin.register(MedicalContact)
class MedicalContactAdmin(admin.ModelAdmin):
    list_display = ("contact_type", "title_en", "phone", "is_active")
    list_editable = ("is_active",)
    list_filter = ("contact_type", "is_active")
    search_fields = ("title_en", "title_ar", "phone", "email")


# ============================================================
# DOWNLOAD CATEGORIES
# ============================================================

@admin.register(DownloadCategory)
class DownloadCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name_en",
        "name_ar",
        "icon",
        "order",
        "is_active",
    )

    list_editable = (
        "order",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name_en",
        "name_ar",
        "description_en",
        "description_ar",
    )

    ordering = (
        "order",
        "name_en",
    )

    fieldsets = (

        (
            "Category",
            {
                "fields": (
                    "name_en",
                    "name_ar",
                    "icon",
                )
            },
        ),

        (
            "Description",
            {
                "fields": (
                    "description_en",
                    "description_ar",
                )
            },
        ),

        (
            "Publishing",
            {
                "fields": (
                    "order",
                    "is_active",
                )
            },
        ),

        (
            "System Information",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


# ============================================================
# DOWNLOAD DOCUMENTS
# ============================================================

@admin.register(DownloadDocument)
class DownloadDocumentAdmin(admin.ModelAdmin):

    list_display = (
        "title_en",
        "category",
        "reference",
        "file_type",
        "file_size_admin",
        "download_count",
        "is_featured",
        "order",
        "is_active",
        "updated_at",
    )

    list_editable = (
        "is_featured",
        "order",
        "is_active",
    )

    list_filter = (
        "category",
        "is_featured",
        "is_active",
        "publication_date",
        "created_at",
    )

    search_fields = (
        "title_en",
        "title_ar",
        "description_en",
        "description_ar",
        "reference",
        "version",
    )

    autocomplete_fields = (
        "category",
    )

    ordering = (
        "order",
        "-updated_at",
    )

    readonly_fields = (
        "download_count",
        "filename_admin",
        "extension_admin",
        "file_size_admin",
        "created_at",
        "updated_at",
    )

    fieldsets = (

        (
            "Document Information",
            {
                "fields": (
                    "category",
                    "title_en",
                    "title_ar",
                    "reference",
                    "version",
                )
            },
        ),

        (
            "Description",
            {
                "fields": (
                    "description_en",
                    "description_ar",
                )
            },
        ),

        (
            "File",
            {
                "fields": (
                    "file",
                    "filename_admin",
                    "extension_admin",
                    "file_size_admin",
                )
            },
        ),

        (
            "Dates",
            {
                "fields": (
                    "publication_date",
                    "expiry_date",
                )
            },
        ),

        (
            "Publishing",
            {
                "fields": (
                    "order",
                    "is_featured",
                    "is_active",
                )
            },
        ),

        (
            "Download Statistics",
            {
                "fields": (
                    "download_count",
                )
            },
        ),

        (
            "System Information",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    @admin.display(
        description="File Type"
    )
    def file_type(
        self,
        obj,
    ):
        return (
            obj.extension.upper()
            if obj.extension
            else "-"
        )

    @admin.display(
        description="Filename"
    )
    def filename_admin(
        self,
        obj,
    ):
        return (
            obj.filename
            if obj and obj.filename
            else "-"
        )

    @admin.display(
        description="Extension"
    )
    def extension_admin(
        self,
        obj,
    ):
        return (
            obj.extension.upper()
            if obj and obj.extension
            else "-"
        )

    @admin.display(
        description="File Size"
    )
    def file_size_admin(
        self,
        obj,
    ):
        return (
            obj.file_size_display
            if obj
            else "-"
        )