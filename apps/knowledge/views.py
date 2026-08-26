from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from .models import Article, ArticleFeedback, KnowledgeCategory


def article_list(request):
    articles = Article.objects.filter(state="published")
    if not request.user.is_authenticated:
        articles = articles.filter(is_public=True)
    term = request.GET.get("q", "").strip()
    category = request.GET.get("category")
    if term:
        articles = articles.filter(Q(title_en__icontains=term) | Q(title_ar__icontains=term) | Q(summary_en__icontains=term) | Q(summary_ar__icontains=term))
    if category:
        articles = articles.filter(category__slug=category)
    return render(request, "knowledge/list.html", {"articles": articles.select_related("category"), "categories": KnowledgeCategory.objects.all(), "term": term})


def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug, state="published")
    if not article.is_public and not request.user.is_authenticated:
        return HttpResponse("Sign in to view this internal article.", status=403)
    related = Article.objects.filter(state="published", category=article.category).exclude(pk=article.pk)[:3]
    return render(request, "knowledge/detail.html", {"article": article, "related": related})


@require_POST
def article_feedback(request, slug):
    article = get_object_or_404(Article, slug=slug, state="published")
    helpful = request.POST.get("helpful") == "yes"
    if request.user.is_authenticated:
        ArticleFeedback.objects.update_or_create(article=article, user=request.user, defaults={"helpful": helpful})
    return render(request, "knowledge/feedback_thanks.html", {"helpful": helpful})
