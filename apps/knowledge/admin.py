from django.contrib import admin
from django.utils import timezone
from .models import Article, ArticleFeedback, KnowledgeCategory


@admin.action(description="Publish selected articles")
def publish_articles(modeladmin, request, queryset):
    queryset.update(state="published", published_at=timezone.now())


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title_en", "category", "state", "is_public", "is_featured", "published_at")
    list_filter = ("state", "is_public", "is_featured", "category")
    search_fields = ("title_en", "title_ar", "summary_en", "summary_ar")
    prepopulated_fields = {"slug": ("title_en",)}
    actions = [publish_articles]
    filter_horizontal = ("projects", "products", "categories")


admin.site.register(KnowledgeCategory)
admin.site.register(ArticleFeedback)
