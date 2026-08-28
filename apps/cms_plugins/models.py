from cms.models.pluginmodel import CMSPlugin
from django.db import models
from django.utils.translation import gettext_lazy as _

class HomeHeroPlugin(CMSPlugin):
    eyebrow = models.CharField(_("Eyebrow"), max_length=200, blank=True)
    title = models.CharField(_("Title"), max_length=300)
    subtitle = models.TextField(_("Subtitle"), blank=True)
    primary_button_text = models.CharField(_("Primary button text"), max_length=100, blank=True)
    primary_button_url = models.CharField(_("Primary button URL"), max_length=500, blank=True)
    secondary_button_text = models.CharField(_("Secondary button text"), max_length=100, blank=True)
    secondary_button_url = models.CharField(_("Secondary button URL"), max_length=500, blank=True)
    def __str__(self):
        return self.title

class HomeImagePlugin(CMSPlugin):
    title = models.CharField(_("Title"), max_length=200, blank=True)
    image = models.ImageField(_("Image"), upload_to="cms/home/")
    alt_text = models.CharField(_("Alternative text"), max_length=250, blank=True)
    link = models.CharField(_("Link"), max_length=500, blank=True)
    open_new_window = models.BooleanField(_("Open in new window"), default=False)
    def __str__(self):
        return self.title or self.alt_text or "Home Image"

class HomeSectionHeaderPlugin(CMSPlugin):
    eyebrow = models.CharField(_("Eyebrow"), max_length=200, blank=True)
    title = models.CharField(_("Title"), max_length=300)
    description = models.TextField(_("Description"), blank=True)
    alignment = models.CharField(_("Alignment"), max_length=20, choices=(("start", _("Start")), ("center", _("Center")), ("end", _("End"))), default="center")
    def __str__(self):
        return self.title

class HomeContentPlugin(CMSPlugin):
    eyebrow = models.CharField(_("Eyebrow"), max_length=200, blank=True)
    title = models.CharField(_("Title"), max_length=300)
    content = models.TextField(_("Content"), blank=True)
    button_text = models.CharField(_("Button text"), max_length=100, blank=True)
    button_url = models.CharField(_("Button URL"), max_length=500, blank=True)
    def __str__(self):
        return self.title

class HomeServicePlugin(CMSPlugin):
    icon = models.CharField(_("Bootstrap icon"), max_length=100, default="bi-shield-check")
    title = models.CharField(_("Title"), max_length=200)
    summary = models.TextField(_("Summary"), blank=True)
    button_text = models.CharField(_("Button text"), max_length=100, blank=True)
    button_url = models.CharField(_("Button URL"), max_length=500, blank=True)
    featured = models.BooleanField(_("Featured"), default=False)
    def __str__(self):
        return self.title

class HomeFeaturePlugin(CMSPlugin):
    icon = models.CharField(_("Bootstrap icon"), max_length=100, default="bi-check-circle")
    title = models.CharField(_("Title"), max_length=200)
    description = models.TextField(_("Description"), blank=True)
    def __str__(self):
        return self.title

class HomeProcessPlugin(CMSPlugin):
    step_number = models.PositiveIntegerField(_("Step number"), default=1)
    icon = models.CharField(_("Bootstrap icon"), max_length=100, default="bi-check2-circle")
    title = models.CharField(_("Title"), max_length=200)
    description = models.TextField(_("Description"), blank=True)
    def __str__(self):
        return f"{self.step_number}. {self.title}"

class HomeStatisticPlugin(CMSPlugin):
    icon = models.CharField(_("Bootstrap icon"), max_length=100, blank=True)
    value = models.CharField(_("Value"), max_length=50)
    suffix = models.CharField(_("Suffix"), max_length=20, blank=True)
    label = models.CharField(_("Label"), max_length=200)
    def __str__(self):
        return f"{self.value}{self.suffix} {self.label}"

class HomeTestimonialPlugin(CMSPlugin):
    name = models.CharField(_("Name"), max_length=200)
    role = models.CharField(_("Role"), max_length=200, blank=True)
    quote = models.TextField(_("Quote"))
    photo = models.ImageField(_("Photo"), upload_to="cms/testimonials/", blank=True, null=True)
    rating = models.PositiveSmallIntegerField(_("Rating"), choices=((1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")), default=5)
    def __str__(self):
        return self.name

class HomeFAQPlugin(CMSPlugin):
    question = models.CharField(_("Question"), max_length=500)
    answer = models.TextField(_("Answer"))
    def __str__(self):
        return self.question

class HomePartnerPlugin(CMSPlugin):
    name = models.CharField(_("Name"), max_length=200)
    logo = models.ImageField(_("Logo"), upload_to="cms/partners/")
    website = models.URLField(_("Website"), blank=True)
    def __str__(self):
        return self.name

class HomeCTAPlugin(CMSPlugin):
    eyebrow = models.CharField(_("Eyebrow"), max_length=200, blank=True)
    title = models.CharField(_("Title"), max_length=300)
    content = models.TextField(_("Content"), blank=True)
    button_text = models.CharField(_("Button text"), max_length=100, blank=True)
    button_url = models.CharField(_("Button URL"), max_length=500, blank=True)
    def __str__(self):
        return self.title


class DownloadCategory(models.Model):
    name_en = models.CharField(_("Name English"), max_length=100)
    name_ar = models.CharField(_("Name Arabic"), max_length=100)
    icon = models.CharField(_("Bootstrap Icon"), max_length=100, default="bi-folder")
    order = models.PositiveIntegerField(_("Order"), default=0)
    is_active = models.BooleanField(_("Active"), default=True)
    class Meta:
        ordering = ["order", "name_en"]
        verbose_name = _("Download Category")
        verbose_name_plural = _("Download Categories")
    def __str__(self):
        return self.name_en

class DownloadDocument(models.Model):
    category = models.ForeignKey(DownloadCategory, on_delete=models.PROTECT, related_name="documents", verbose_name=_("Category"))
    title_en = models.CharField(_("Title English"), max_length=250)
    title_ar = models.CharField(_("Title Arabic"), max_length=250, blank=True)
    description_en = models.TextField(_("Description English"), blank=True)
    description_ar = models.TextField(_("Description Arabic"), blank=True)
    file = models.FileField(_("File"), upload_to="downloads/%Y/%m/")
    version = models.CharField(_("Version"), max_length=50, blank=True)
    reference = models.CharField(_("Reference"), max_length=100, blank=True)
    order = models.PositiveIntegerField(_("Order"), default=0)
    is_featured = models.BooleanField(_("Featured"), default=False)
    is_active = models.BooleanField(_("Active"), default=True)
    download_count = models.PositiveIntegerField(_("Download Count"), default=0)
    created_at = models.DateTimeField(_("Created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated"), auto_now=True)
    class Meta:
        ordering = ["order", "-updated_at"]
        verbose_name = _("Download Document")
        verbose_name_plural = _("Download Documents")
    def __str__(self):
        return self.title_en
    @property
    def extension(self):
        return self.file.name.rsplit(".", 1)[-1].lower() if "." in self.file.name else ""
    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]
    @property
    def file_size_display(self):
        if not self.file:
            return ""
        size = self.file.size
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


class CustomWebSection(CMSPlugin):
    title = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Section name",
        help_text="Internal name used to identify this CMS section.",
    )

    html_content = models.TextField(
        blank=True,
        verbose_name="HTML content",
        help_text="Create content using the visual editor or HTML source mode.",
    )

    css_content = models.TextField(
        blank=True,
        verbose_name="Custom CSS",
    )

    javascript_content = models.TextField(
        blank=True,
        verbose_name="Custom JavaScript",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
    )

    def __str__(self):
        return self.title or f"Custom Web Section #{self.pk}"