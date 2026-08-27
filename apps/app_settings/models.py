from django.conf import settings
from django.db import models
from django.urls import NoReverseMatch, reverse
from apps.core.models import LocalizedModelMixin, TimeStampedModel


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
    contact_phone = models.CharField(max_length=30, default="+968 2400 0000")
    address_en = models.CharField(max_length=255, default="Muscat, Sultanate of Oman")
    address_ar = models.CharField(max_length=255, default="مسقط، سلطنة عُمان")
    logo = models.ImageField(upload_to="branding/", blank=True)
    favicon = models.ImageField(upload_to="branding/", blank=True)
    public_registration_enabled = models.BooleanField(default=True)
    public_theme_switcher_enabled = models.BooleanField(default=True)
    organization_details = models.TextField(blank=True)
    social_links = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name_plural = "Site settings"


class ThemeSettings(SingletonModel, TimeStampedModel):
    primary = models.CharField(max_length=20, default="#147A50")
    primary_dark = models.CharField(max_length=20, default="#0D5F3D")
    secondary = models.CharField(max_length=20, default="#DDF3E8")
    accent = models.CharField(max_length=20, default="#7ACFA5")
    background = models.CharField(max_length=20, default="#F6F8F7")
    surface = models.CharField(max_length=20, default="#FFFFFF")
    text = models.CharField(max_length=20, default="#1F2933")
    muted_text = models.CharField(max_length=20, default="#64748B")
    warning = models.CharField(max_length=20, default="#D99400")
    danger = models.CharField(max_length=20, default="#C2413B")
    information = models.CharField(max_length=20, default="#2563EB")
    radius_px = models.PositiveSmallIntegerField(default=12)
    shadow_intensity = models.PositiveSmallIntegerField(default=9)
    font_family = models.CharField(max_length=80, default="Inter")
    default_theme = models.CharField(max_length=10, default="system", choices=[("system", "System"), ("light", "Light"), ("dark", "Dark")])
    users_may_choose_theme = models.BooleanField(default=True)
    animations_enabled = models.BooleanField(default=True)
    custom_css = models.TextField(blank=True, help_text="Super Admin only. CSS is rendered as style content; never place secrets here.")

    class Meta:
        verbose_name_plural = "Theme settings"
        permissions = [("manage_theme", "Can manage site theme")]


class AnimationPreset(TimeStampedModel):
    key = models.SlugField(unique=True)
    label = models.CharField(max_length=80)
    css_class = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.label


class NavigationItem(TimeStampedModel, LocalizedModelMixin):
    class Section(models.TextChoices):
        WORKSPACE = "workspace", "Workspace"
        INTELLIGENCE = "intelligence", "Intelligence"
        RESOURCES = "resources", "Resources"
        ADMINISTRATION = "administration", "Administration"

    label_en = models.CharField(max_length=80)
    label_ar = models.CharField(max_length=80, blank=True)
    url = models.CharField(max_length=255, blank=True, help_text="Use a local path or external URL. A linked page takes precedence.")
    route_name = models.CharField(max_length=150, blank=True, help_text="Optional Django route, for example portal:dashboard.")
    route_arguments = models.JSONField(default=list, blank=True, help_text="Optional positional arguments for the Django route.")
    location = models.CharField(max_length=20, default="header", choices=[("header", "Header"), ("footer", "Footer"), ("portal", "Portal")])
    section = models.CharField(max_length=30, choices=Section.choices, default=Section.WORKSPACE)
    icon = models.CharField(max_length=80, default="bi-circle", help_text="Bootstrap Icons class, for example bi-grid-1x2.")
    linked_page = models.ForeignKey("Page", related_name="navigation_items", null=True, blank=True, on_delete=models.SET_NULL)
    allowed_groups = models.ManyToManyField("auth.Group", related_name="app_settings_navigation_items", blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    opens_new_window = models.BooleanField(default=False)
    required_permission = models.CharField(max_length=150, blank=True)
    staff_only = models.BooleanField(default=False)
    emphasized = models.BooleanField(default=False)

    class Meta:
        ordering = ["location", "section", "order", "label_en"]

    def __str__(self):
        return self.label_en

    @property
    def resolved_url(self):
        if self.linked_page_id:
            if self.location == "portal":
                return reverse("portal:managed_page", args=[self.linked_page.slug])
            return self.linked_page.get_absolute_url()
        if self.route_name:
            try:
                route = reverse(self.route_name, args=self.route_arguments or None)
                return route + self.url if self.url.startswith(("#", "?")) else route
            except NoReverseMatch:
                pass
        return self.url or "#"


class Page(TimeStampedModel, LocalizedModelMixin):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class Audience(models.TextChoices):
        PUBLIC = "public", "Public website"
        PORTAL = "portal", "Authenticated portal"
        BOTH = "both", "Public website and portal"

    slug = models.SlugField(unique=True)
    title_en = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    summary_en = models.TextField(blank=True)
    summary_ar = models.TextField(blank=True)
    body_en = models.TextField(blank=True)
    body_ar = models.TextField(blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.DRAFT)
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.PUBLIC)
    portal_icon = models.CharField(max_length=80, default="bi-file-earmark-text")
    allowed_groups = models.ManyToManyField("auth.Group", related_name="app_settings_pages", blank=True)
    layout = models.CharField(max_length=30, default="standard", choices=[("standard", "Standard"), ("wide", "Wide"), ("landing", "Landing")])
    is_visible = models.BooleanField(default=True)
    disable_animations = models.BooleanField(default=False)
    publication_date = models.DateTimeField(null=True, blank=True)
    seo_title_en = models.CharField(max_length=160, blank=True)
    seo_title_ar = models.CharField(max_length=160, blank=True)
    seo_description_en = models.CharField(max_length=320, blank=True)
    seo_description_ar = models.CharField(max_length=320, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        permissions = [("publish_page", "Can publish legacy GLIS pages")]

    def __str__(self):
        return self.title_en

    def get_absolute_url(self):
        return reverse("public:page", args=[self.slug])

    def get_portal_url(self):
        return reverse("portal:managed_page", args=[self.slug])


class PageSection(TimeStampedModel, LocalizedModelMixin):
    page = models.ForeignKey(Page, related_name="sections", on_delete=models.CASCADE)
    section_type = models.CharField(max_length=30, default="content", choices=[("content", "Content"), ("features", "Features"), ("statistics", "Statistics"), ("cta", "Call to action")])
    title_en = models.CharField(max_length=160, blank=True)
    title_ar = models.CharField(max_length=160, blank=True)
    content_en = models.TextField(blank=True)
    content_ar = models.TextField(blank=True)
    settings = models.JSONField(default=dict, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    animation = models.ForeignKey(AnimationPreset, null=True, blank=True, on_delete=models.SET_NULL)
    animation_duration_ms = models.PositiveIntegerField(default=500)
    animation_delay_ms = models.PositiveIntegerField(default=0)
    animate_once = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]


class HeroSection(SingletonModel, TimeStampedModel, LocalizedModelMixin):
    eyebrow_en = models.CharField(max_length=120, default="Insurance service orchestration")
    eyebrow_ar = models.CharField(max_length=120, default="تنسيق خدمات التأمين")
    title_en = models.CharField(max_length=220, default="One clear path through every insurance request")
    title_ar = models.CharField(max_length=220, default="مسار واضح لكل طلب تأميني")
    subtitle_en = models.TextField(default="Submit, track and resolve service requests with secure collaboration across customers, providers and insurance teams.")
    subtitle_ar = models.TextField(default="قدّم طلبات الخدمة وتابعها وأنجزها بتعاون آمن بين العملاء ومقدمي الخدمة وفرق التأمين.")
    primary_cta_en = models.CharField(max_length=60, default="Submit a request")
    primary_cta_ar = models.CharField(max_length=60, default="تقديم طلب")
    primary_cta_url = models.CharField(max_length=255, default="/portal/tickets/create/1/")
    secondary_cta_en = models.CharField(max_length=60, default="Explore services")
    secondary_cta_ar = models.CharField(max_length=60, default="استكشف الخدمات")
    secondary_cta_url = models.CharField(max_length=255, default="#services")
    hero_image = models.ImageField(upload_to="cms/hero/", blank=True)


class ServiceCategory(TimeStampedModel, LocalizedModelMixin):
    name_en = models.CharField(max_length=120)
    name_ar = models.CharField(max_length=120, blank=True)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, default="bi-shield-check")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name_en"]

    def __str__(self):
        return self.name_en


class Service(TimeStampedModel, LocalizedModelMixin):
    category = models.ForeignKey(ServiceCategory, related_name="services", on_delete=models.CASCADE)
    title_en = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    summary_en = models.TextField()
    summary_ar = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default="bi-clipboard2-pulse")
    link = models.CharField(max_length=255, blank=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "title_en"]

    def __str__(self):
        return self.title_en


class Statistic(TimeStampedModel, LocalizedModelMixin):
    label_en = models.CharField(max_length=100)
    label_ar = models.CharField(max_length=100, blank=True)
    value = models.CharField(max_length=30)
    suffix = models.CharField(max_length=15, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]


class Testimonial(TimeStampedModel, LocalizedModelMixin):
    name = models.CharField(max_length=100)
    role_en = models.CharField(max_length=100, blank=True)
    role_ar = models.CharField(max_length=100, blank=True)
    quote_en = models.TextField()
    quote_ar = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)


class ContentVersion(TimeStampedModel):
    page = models.ForeignKey(Page, related_name="versions", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    change_note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["page", "version"], name="app_settings_unique_page_version")]
