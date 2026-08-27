from django.db import OperationalError, ProgrammingError
from urllib.parse import urlsplit
from .models import NavigationItem, SiteSettings, ThemeSettings


def site_context(request):
    try:
        site_settings = SiteSettings.load()
        theme_settings = ThemeSettings.load()
        navigation = NavigationItem.objects.filter(is_visible=True).select_related("linked_page")
        public_header_navigation = []
        for item in navigation.filter(location="header").order_by("order", "label_en"):
            if item.staff_only and not (request.user.is_authenticated and request.user.is_staff):
                continue
            if item.required_permission and not (request.user.is_authenticated and (request.user.is_superuser or request.user.has_perm(item.required_permission))):
                continue
            public_header_navigation.append({"label": item.localized("label"), "url": item.resolved_url, "new_window": item.opens_new_window})
        portal_items = list(navigation.filter(location="portal").prefetch_related("allowed_groups").order_by("order", "label_en")) if request.user.is_authenticated else []
        section_rank = {value: index for index, (value, _label) in enumerate(NavigationItem.Section.choices)}
        portal_items.sort(key=lambda item: (section_rank.get(item.section, 999), item.order, item.label_en))
        user_group_ids = set(request.user.groups.values_list("pk", flat=True)) if request.user.is_authenticated else set()
        sections, section_map = [], {}
        for item in portal_items:
            if item.staff_only and not request.user.is_staff:
                continue
            if item.required_permission and not (request.user.is_superuser or request.user.has_perm(item.required_permission)):
                continue
            allowed_group_ids = {group.pk for group in item.allowed_groups.all()}
            if allowed_group_ids and not request.user.is_superuser and not (allowed_group_ids & user_group_ids):
                continue
            url = item.resolved_url
            path = urlsplit(url).path.rstrip("/") or "/"
            current_path = request.path.rstrip("/") or "/"
            entry = {"label": item.localized("label"), "url": url, "icon": item.icon, "active": current_path == path, "new_window": item.opens_new_window, "emphasized": item.emphasized}
            if item.section not in section_map:
                section = {"key": item.section, "label": item.get_section_display(), "items": []}
                section_map[item.section] = section
                sections.append(section)
            section_map[item.section]["items"].append(entry)
    except (OperationalError, ProgrammingError):
        site_settings, theme_settings, navigation, sections, public_header_navigation = None, None, [], [], []
    return {"glis_site": site_settings, "glis_theme": theme_settings, "glis_navigation": navigation, "public_header_navigation": public_header_navigation, "portal_navigation_sections": sections}
