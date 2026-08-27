"""Compatibility imports for the former local ``apps.cms`` application.

The real django CMS owns the top-level ``cms`` application namespace now.
GLIS application settings/content models live in ``apps.app_settings``.

This module intentionally defines no Django models. It remains temporarily so
older GLIS modules importing ``apps.cms.models`` continue to work while those
imports are migrated incrementally.
"""

from apps.app_settings.models import (  # noqa: F401
    AnimationPreset,
    ContentVersion,
    HeroSection,
    NavigationItem,
    Page,
    PageSection,
    Service,
    ServiceCategory,
    SiteSettings,
    Statistic,
    Testimonial,
    ThemeSettings,
)

__all__ = [
    "AnimationPreset",
    "ContentVersion",
    "HeroSection",
    "NavigationItem",
    "Page",
    "PageSection",
    "Service",
    "ServiceCategory",
    "SiteSettings",
    "Statistic",
    "Testimonial",
    "ThemeSettings",
]
