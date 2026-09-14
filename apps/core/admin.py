from django.contrib import admin
from .models import SiteSettings, ServiceCategory, Service, Feature, Statistic, ProcessStep, Testimonial, FAQ, Partner, AuditLog, ManagementMember, InsurancePartner, ProviderType, Governorate, City, MedicalSpecialty, NetworkProvider, TPAService, MedicalContact, MedicalDownload, DownloadCategory, DownloadDocument

class ServiceInline(admin.StackedInline):
    model = Service
    extra = 0
    fields = ("category", ("title_en", "title_ar"), ("summary_en", "summary_ar"), ("icon", "image"), "link", ("button_text_en", "button_text_ar"), ("order", "is_featured", "is_active"))

class FeatureInline(admin.StackedInline):
    model = Feature
    extra = 0
    fields = (("title_en", "title_ar"), ("description_en", "description_ar"), ("icon", "image"), ("order", "is_active"))

class StatisticInline(admin.TabularInline):
    model = Statistic
    extra = 0
    fields = ("value", "suffix", "label_en", "label_ar", "icon", "order", "is_active")

class ProcessStepInline(admin.StackedInline):
    model = ProcessStep
    extra = 0
    fields = (("process_type", "step_number", "order"), ("title_en", "title_ar"), ("description_en", "description_ar"), "icon", "is_active")

class TestimonialInline(admin.StackedInline):
    model = Testimonial
    extra = 0
    fields = ("name", ("role_en", "role_ar"), ("quote_en", "quote_ar"), "photo", ("rating", "order", "is_active"))

class FAQInline(admin.StackedInline):
    model = FAQ
    extra = 0
    fields = (("question_en", "question_ar"), ("answer_en", "answer_ar"), ("order", "is_active"))

class PartnerInline(admin.TabularInline):
    model = Partner
    extra = 0
    fields = ("name", "logo", "website", "order", "is_active")

class ManagementMemberInline(admin.StackedInline):
    model = ManagementMember
    extra = 0
    fields = (("name_en", "name_ar"), ("designation_en", "designation_ar"), ("department_en", "department_ar"), ("profile_en", "profile_ar"), ("qualification_en", "qualification_ar"), "experience_years", "image", ("linkedin_url", "email"), ("sort_order", "is_active"))

class InsurancePartnerInline(admin.StackedInline):
    model = InsurancePartner
    extra = 0
    fields = (("name_en", "name_ar"), "short_name", "logo", "website_url", ("description_en", "description_ar"), ("contact_phone", "contact_email"), ("sort_order", "is_featured", "is_active"))

class ProviderTypeInline(admin.TabularInline):
    model = ProviderType
    extra = 0
    fields = ("name_en", "name_ar", "icon", "sort_order", "is_active")

@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    inlines = [ServiceInline, FeatureInline, StatisticInline, ProcessStepInline, TestimonialInline, FAQInline, PartnerInline, ManagementMemberInline, InsurancePartnerInline, ProviderTypeInline]
    fieldsets = (
        ("General", {"fields": (("site_name_en", "site_name_ar"), "short_name", ("tagline_en", "tagline_ar"), "organization_details")}),
        ("Contact", {"fields": (("contact_email", "support_email"), ("contact_phone", "secondary_phone"), "whatsapp_number", ("working_hours_en", "working_hours_ar"))}),
        ("Address & Map", {"fields": (("address_en", "address_ar"), ("city", "governorate"), ("country", "po_box", "postal_code"), ("latitude", "longitude", "map_zoom"))}),
        ("Registration", {"fields": (("commercial_registration_no", "vat_registration_no"), ("license_no", "established_year"), "website")}),
        ("Branding", {"fields": ("logo", "favicon", "social_links")}),
        ("Public Site", {"fields": ("public_registration_enabled", "public_theme_switcher_enabled")}),
        ("Hero", {"fields": (("hero_eyebrow_en", "hero_eyebrow_ar"), ("hero_title_en", "hero_title_ar"), ("hero_subtitle_en", "hero_subtitle_ar"), ("hero_primary_cta_en", "hero_primary_cta_ar"), "hero_primary_cta_url", ("hero_secondary_cta_en", "hero_secondary_cta_ar"), "hero_secondary_cta_url", "hero_image")}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_en", "name_ar")

class CityInline(admin.TabularInline):
    model = City
    extra = 0
    fields = ("name_en", "name_ar", "is_active")


@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_ar", "code", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("name_en", "name_ar", "code")
    inlines = (CityInline,)

@admin.register(MedicalSpecialty)
class MedicalSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("name_en", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_en", "name_ar", "description_en", "description_ar")


@admin.register(NetworkProvider)
class NetworkProviderAdmin(admin.ModelAdmin):
    list_display = ("provider_code", "name_en", "provider_type", "city", "network_level", "is_24_hours", "is_featured", "is_active")
    list_editable = ("is_featured", "is_active")
    list_filter = ("provider_type", "governorate", "city", "network_level", "is_24_hours", "has_emergency", "has_pharmacy", "has_dental", "has_optical", "is_featured", "is_active")
    search_fields = ("provider_code", "name_en", "name_ar", "address_en", "address_ar", "area_en", "area_ar", "phone", "email")
    filter_horizontal = ("specialties", "insurance_partners")
    ordering = ("sort_order", "name_en")

@admin.register(TPAService)
class TPAServiceAdmin(admin.ModelAdmin):
    list_display = ("title_en", "sort_order", "is_featured", "is_active")
    list_editable = ("sort_order", "is_featured", "is_active")
    list_filter = ("is_featured", "is_active")
    search_fields = ("title_en", "title_ar", "short_description_en", "description_en")


@admin.register(MedicalContact)
class MedicalContactAdmin(admin.ModelAdmin):
    list_display = ("title_en", "contact_type", "phone", "is_24_hours", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("contact_type", "is_24_hours", "is_active")
    search_fields = ("title_en", "title_ar", "phone", "whatsapp", "email")


@admin.register(MedicalDownload)
class MedicalDownloadAdmin(admin.ModelAdmin):
    list_display = ("title_en", "document_type", "sort_order", "is_active", "created_at")
    list_editable = ("sort_order", "is_active")
    list_filter = ("document_type", "is_active")
    search_fields = ("title_en", "title_ar", "description_en", "description_ar")
    readonly_fields = ("created_at",)

class DownloadDocumentInline(admin.StackedInline):
    model = DownloadDocument
    extra = 0
    fields = (("title_en", "title_ar"), ("description_en", "description_ar"), ("reference", "version"), "file", ("publication_date", "expiry_date"), ("order", "is_featured", "is_active"), "download_count")
    readonly_fields = ("download_count",)


@admin.register(DownloadCategory)
class DownloadCategoryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "order", "is_active", "updated_at")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_en", "name_ar", "description_en", "description_ar")
    inlines = (DownloadDocumentInline,)
    readonly_fields = ("created_at", "updated_at")

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "sensitivity", "summary")
    list_filter = ("action", "object_type", "sensitivity", "created_at")
    search_fields = ("summary", "object_type", "object_id", "actor__username", "actor__email")
    readonly_fields = ("created_at", "actor", "action", "object_type", "object_id", "summary", "changes", "ip_address", "user_agent", "sensitivity")
    ordering = ("-created_at",)
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False