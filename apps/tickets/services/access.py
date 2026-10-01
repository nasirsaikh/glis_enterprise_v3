from ..models import Category, Product, Project
from django.db.models import Q
from services.tenancy import organization_ids


def accessible_categories(user):
    """
    Strict role-based category access.

    Normal users see only categories explicitly assigned
    to one of their Django groups.

    Superusers see everything.
    """

    qs = Category.objects.filter(
        is_active=True,
        product__is_active=True,
        product__project__is_active=True,
    )

    if not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs.distinct()

    return (
        qs.filter(
            Q(allowed_groups__isnull=True) | Q(allowed_groups__in=user.groups.all())
        )
        .filter(Q(product__project__organizations__isnull=True) | Q(product__project__organizations__pk__in=organization_ids(user)))
        .filter(Q(product__project__organization_types__isnull=True) | Q(product__project__organization_types__organizations__pk__in=organization_ids(user)))
        .distinct()
    )


def accessible_products(user):
    """
    Show only products having at least one category
    accessible to the current user.
    """

    accessible_product_ids = (
        accessible_categories(user)
        .values_list("product_id", flat=True)
    )

    return (
        Product.objects
        .filter(
            is_active=True,
            project__is_active=True,
            id__in=accessible_product_ids,
        )
        .distinct()
    )


def accessible_projects(user):
    """
    Show only projects having at least one accessible product.
    """

    accessible_project_ids = (
        accessible_products(user)
        .values_list("project_id", flat=True)
    )

    return (
        Project.objects
        .filter(
            is_active=True,
            id__in=accessible_project_ids,
        )
        .distinct()
    )