from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from .models import HeroSection, Page, Service, ServiceCategory, SiteSettings, Statistic, Testimonial, ThemeSettings


def home(request):
    services_qs = (
        Service.objects
        .filter(is_active=True)
        .select_related("category")
    )

    services = services_qs[:9]

    context = {
        "hero": HeroSection.load(),

        "services": services,

        "service_categories": (
            ServiceCategory.objects
            .prefetch_related(
                Prefetch(
                    "services",
                    queryset=services_qs,
                )
            )[:6]
        ),

        "statistics": Statistic.objects.filter(
            is_active=True
        )[:4],

        "testimonials": Testimonial.objects.filter(
            is_active=True
        )[:3],
    }

    try:
        from apps.knowledge.models import Article

        context["featured_articles"] = (
            Article.objects
            .filter(
                state="published",
                is_public=True,
                is_featured=True,
            )[:3]
        )
    except Exception:
        context["featured_articles"] = []

    return render(request, "public/home.html", context)


def page_detail(request, slug):
    filters = {"slug": slug, "is_visible": True, "audience__in": [Page.Audience.PUBLIC, Page.Audience.BOTH]}
    if not (request.user.is_authenticated and request.user.is_staff and request.GET.get("preview") == "1"):
        filters.update(state=Page.State.PUBLISHED, publication_date__lte=timezone.now())
    try:
        page = Page.objects.prefetch_related("sections").get(**filters)
    except Page.DoesNotExist as exc:
        raise Http404 from exc
    return render(request, "public/page.html", {"page": page})


@login_required
def portal_page_detail(request, slug):
    filters = {
        "slug": slug,
        "is_visible": True,
        "state": Page.State.PUBLISHED,
        "publication_date__lte": timezone.now(),
        "audience__in": [Page.Audience.PORTAL, Page.Audience.BOTH],
    }
    try:
        page = Page.objects.prefetch_related("sections", "allowed_groups").get(**filters)
    except Page.DoesNotExist as exc:
        raise Http404 from exc
    allowed_groups = page.allowed_groups.all()
    if allowed_groups.exists() and not request.user.is_superuser and not allowed_groups.filter(user=request.user).exists():
        raise Http404
    return render(request, "cms/portal_page.html", {"page": page})


@staff_member_required
def page_preview(request, pk):
    page = Page.objects.prefetch_related("sections").get(pk=pk)
    template = "cms/portal_page.html" if page.audience == Page.Audience.PORTAL else "public/page.html"
    return render(request, template, {"page": page, "preview": True})


def theme_css(request):
    theme = ThemeSettings.load()
    css = f""":root{{--glis-primary:{theme.primary};--glis-primary-dark:{theme.primary_dark};--glis-secondary:{theme.secondary};--glis-accent:{theme.accent};--glis-bg:{theme.background};--glis-surface:{theme.surface};--glis-text:{theme.text};--glis-muted:{theme.muted_text};--glis-warning:{theme.warning};--glis-danger:{theme.danger};--glis-info:{theme.information};--glis-radius:{theme.radius_px}px;--glis-shadow:0 10px 30px rgba(20,122,80,{theme.shadow_intensity/100:.2f});}}{theme.custom_css}"""
    return HttpResponse(css, content_type="text/css")
