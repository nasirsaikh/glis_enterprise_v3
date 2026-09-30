"""Public articles are shared; internal articles follow their author's tenant."""
from django.db.models import Q

from services.tenancy import visible_users
from .models import Article


def visible_articles(user):
    qs = Article.objects.filter(state="published")
    if not user or not user.is_authenticated:
        return qs.filter(is_public=True)
    if user.is_superuser:
        return qs
    return qs.filter(Q(is_public=True) | Q(author__in=visible_users(user))).distinct()
