from django.conf import settings
from django.db import models
from django.urls import reverse
from apps.core.models import LocalizedModelMixin, TimeStampedModel


class KnowledgeCategory(TimeStampedModel, LocalizedModelMixin):
    name_en = models.CharField(max_length=120)
    name_ar = models.CharField(max_length=120, blank=True)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, default="bi-journal-text")

    class Meta:
        verbose_name_plural = "Knowledge categories"

    def __str__(self):
        return self.name_en


class Article(TimeStampedModel, LocalizedModelMixin):
    category = models.ForeignKey(KnowledgeCategory, related_name="articles", on_delete=models.PROTECT)
    slug = models.SlugField(unique=True)
    title_en = models.CharField(max_length=180)
    title_ar = models.CharField(max_length=180, blank=True)
    summary_en = models.TextField(blank=True)
    summary_ar = models.TextField(blank=True)
    body_en = models.TextField()
    body_ar = models.TextField(blank=True)
    state = models.CharField(max_length=20, default="draft", choices=[("draft", "Draft"), ("review", "In review"), ("published", "Published")])
    is_public = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    projects = models.ManyToManyField("tickets.Project", blank=True)
    products = models.ManyToManyField("tickets.Product", blank=True)
    categories = models.ManyToManyField("tickets.Category", blank=True)
    seo_title_en = models.CharField(max_length=160, blank=True)
    seo_title_ar = models.CharField(max_length=160, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-is_featured", "-published_at", "title_en"]

    def __str__(self):
        return self.title_en

    def get_absolute_url(self):
        return reverse("knowledge:detail", args=[self.slug])


class ArticleFeedback(TimeStampedModel):
    article = models.ForeignKey(Article, related_name="feedback", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    helpful = models.BooleanField()
    comment = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["article", "user"], name="unique_user_article_feedback")]
