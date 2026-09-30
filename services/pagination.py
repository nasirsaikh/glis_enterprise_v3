from django.core.paginator import Paginator


def table_page(request, queryset):
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    parameters = request.GET.copy()
    parameters.pop("page", None)
    return {
        "page_obj": page,
        "pagination_query": parameters.urlencode(),
        "query": request.GET.get("q", "").strip(),
    }
