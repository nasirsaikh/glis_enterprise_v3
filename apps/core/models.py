from django.conf import settings
from django.db import models
#from apps.core.models import LocalizedModelMixin, TimeStampedModel
from django.utils.translation import get_language

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class LocalizedModelMixin:
    def localized(self, field: str) -> str:
        language = (get_language() or "en").split("-")[0]
        value = getattr(self, f"{field}_{language}", "")
        return value or getattr(self, f"{field}_en", "")


class SingletonModel(models.Model):
    class Meta:
        abstract = True
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SiteSettings(SingletonModel, TimeStampedModel):
    site_name_en = models.CharField(max_length=150, default="Greenline Insurance Services")
    site_name_ar = models.CharField(max_length=150, default="جرين لاين لخدمات التأمين")
    short_name = models.CharField(max_length=30, default="GLIS")
    tagline_en = models.CharField(max_length=180, default="Insurance service, made clear")
    tagline_ar = models.CharField(max_length=180, default="خدمات التأمين، بوضوح وسهولة")

    contact_email = models.EmailField(default="care@glis.example")
    support_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, default="+968 2400 0000")
    secondary_phone = models.CharField(max_length=30, blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)

    address_en = models.CharField(max_length=255, default="Muscat, Sultanate of Oman")
    address_ar = models.CharField(max_length=255, default="مسقط، سلطنة عُمان")
    city = models.CharField(max_length=100, blank=True, default="Muscat")
    governorate = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default="Oman")
    po_box = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)

    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    map_zoom = models.PositiveSmallIntegerField(default=15)

    commercial_registration_no = models.CharField(max_length=100, blank=True)
    vat_registration_no = models.CharField(max_length=100, blank=True)
    license_no = models.CharField(max_length=100, blank=True)
    established_year = models.PositiveSmallIntegerField(null=True, blank=True)

    website = models.URLField(blank=True)
    working_hours_en = models.CharField(max_length=255, blank=True)
    working_hours_ar = models.CharField(max_length=255, blank=True)

    logo = models.ImageField(upload_to="branding/", blank=True)
    favicon = models.ImageField(upload_to="branding/", blank=True)

    public_registration_enabled = models.BooleanField(default=True)
    public_theme_switcher_enabled = models.BooleanField(default=True)
    organization_details = models.TextField(blank=True)
    social_links = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name_plural = "Site settings"

    def __str__(self):
        return self.site_name_en        


class ServiceCategory(TimeStampedModel):
    name_en = models.CharField(max_length=120)
    name_ar = models.CharField(max_length=120, blank=True)
    icon = models.CharField(max_length=80, default="bi-grid")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name_en"]
        verbose_name_plural = "Service Categories"

    def __str__(self):
        return self.name_en


class Service(TimeStampedModel):
    category = models.ForeignKey(ServiceCategory, related_name="services", on_delete=models.CASCADE, null=True, blank=True)
    title_en = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    summary_en = models.TextField(blank=True)
    summary_ar = models.TextField(blank=True)
    icon = models.CharField(max_length=80, default="bi-shield-check")
    image = models.ImageField(upload_to="cms/services/", blank=True)
    link = models.CharField(max_length=255, blank=True)
    button_text_en = models.CharField(max_length=80, blank=True)
    button_text_ar = models.CharField(max_length=80, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "title_en"]

    def __str__(self):
        return self.title_en


class Feature(TimeStampedModel):
    title_en = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    icon = models.CharField(max_length=80, default="bi-check-circle")
    image = models.ImageField(upload_to="cms/features/", blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title_en


class Statistic(TimeStampedModel):
    value = models.CharField(max_length=50)
    suffix = models.CharField(max_length=20, blank=True)
    label_en = models.CharField(max_length=120)
    label_ar = models.CharField(max_length=120, blank=True)
    icon = models.CharField(max_length=80, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.value}{self.suffix} - {self.label_en}"


class ProcessStep(TimeStampedModel):
    step_number = models.PositiveSmallIntegerField(default=1)
    title_en = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    icon = models.CharField(max_length=80, default="bi-check2-circle")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "step_number"]

    def __str__(self):
        return self.title_en


class Testimonial(TimeStampedModel):
    name = models.CharField(max_length=120)
    role_en = models.CharField(max_length=120, blank=True)
    role_ar = models.CharField(max_length=120, blank=True)
    quote_en = models.TextField()
    quote_ar = models.TextField(blank=True)
    photo = models.ImageField(upload_to="cms/testimonials/", blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class FAQ(TimeStampedModel):
    question_en = models.CharField(max_length=255)
    question_ar = models.CharField(max_length=255, blank=True)
    answer_en = models.TextField()
    answer_ar = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.question_en


class Partner(TimeStampedModel):
    name = models.CharField(max_length=160)
    logo = models.ImageField(upload_to="cms/partners/")
    website = models.URLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class HomeSection(TimeStampedModel):
    SECTION_CHOICES = [
        ("about", "About"),
        ("services", "Services"),
        ("why_us", "Why Choose Us"),
        ("process", "Process"),
        ("statistics", "Statistics"),
        ("features", "Features"),
        ("testimonials", "Testimonials"),
        ("faq", "FAQ"),
        ("contact", "Contact"),
        ("cta", "Call To Action"),
    ]

    section = models.CharField(max_length=30, choices=SECTION_CHOICES, unique=True)
    eyebrow_en = models.CharField(max_length=120, blank=True)
    eyebrow_ar = models.CharField(max_length=120, blank=True)
    title_en = models.CharField(max_length=200, blank=True)
    title_ar = models.CharField(max_length=200, blank=True)
    content_en = models.TextField(blank=True)
    content_ar = models.TextField(blank=True)
    image = models.ImageField(upload_to="cms/sections/", blank=True)
    button_text_en = models.CharField(max_length=80, blank=True)
    button_text_ar = models.CharField(max_length=80, blank=True)
    button_url = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.get_section_display()


class HeroSection(SingletonModel, TimeStampedModel, LocalizedModelMixin):
    eyebrow_en = models.CharField(max_length=120, default="Insurance service orchestration")
    eyebrow_ar = models.CharField(max_length=120, default="تنسيق خدمات التأمين")
    title_en = models.CharField(max_length=220, default="One clear path through every insurance request")
    title_ar = models.CharField(max_length=220, default="مسار واضح لكل طلب تأميني")
    subtitle_en = models.TextField(default="Submit, track and resolve service requests with secure collaboration across customers, providers and insurance teams.")
    subtitle_ar = models.TextField(default="قدّم طلبات الخدمة وتابعها وأنجزها بتعاون آمن بين العملاء ومقدمي الخدمة وفرق التأمين.")
    primary_cta_en = models.CharField(max_length=60, default="Submit a request")
    primary_cta_ar = models.CharField(max_length=60, default="تقديم طلب")
    primary_ctta_url = models.CharField(max_length=255, default="/portal/tickets/create/1/")
    secondary_cta_en = models.CharField(max_length=60, default="Explore services")
    secondary_cta_ar = models.CharField(max_length=60, default="استكشف الخدمات")
    secondary_cta_url = models.CharField(max_length=255, default="#services")
    hero_image = models.ImageField(upload_to="cms/hero/", blank=True)




class ModuleRegistry(TimeStampedModel, LocalizedModelMixin):
    key = models.SlugField(unique=True)
    name_en = models.CharField(max_length=120)
    name_ar = models.CharField(max_length=120, blank=True)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default="bi-grid")
    route_name = models.CharField(max_length=120, blank=True)
    is_enabled = models.BooleanField(default=True)
    show_in_navigation = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    required_permission = models.CharField(max_length=150, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order", "name_en"]
        permissions = [("manage_modules", "Can manage module registry")]

    def __str__(self):
        return self.name_en


class ConfigurationVersion(TimeStampedModel):
    key = models.CharField(max_length=120)
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=20, choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")])
    payload = models.JSONField(default=dict)
    validation_errors = models.JSONField(default=list, blank=True)
    change_note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["key", "version"], name="unique_configuration_version")]
        permissions = [("manage_json_config", "Can manage JSON configuration")]


class AuditLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    sensitivity = models.CharField(max_length=20, default="normal", choices=[("normal", "Normal"), ("sensitive", "Sensitive"), ("security", "Security")])

    class Meta:
        ordering = ["-created_at"]
        permissions = [("view_audit", "Can view audit logs")]

    @classmethod
    def record(cls, *, request=None, actor=None, action, instance=None, summary, changes=None, sensitivity="normal"):
        if request:
            actor = actor or (request.user if request.user.is_authenticated else None)
        return cls.objects.create(
            actor=actor, action=action,
            object_type=instance._meta.label if instance else "",
            object_id=str(instance.pk) if instance and instance.pk else "",
            summary=summary, changes=changes or {}, sensitivity=sensitivity,
            ip_address=(request.META.get("REMOTE_ADDR") if request else None),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
        )
