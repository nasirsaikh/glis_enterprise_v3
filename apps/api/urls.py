from django.urls import path

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from . import views


urlpatterns = [

    # ========================================================
    # HEALTH
    # ========================================================

    path(
        "health/",
        views.health,
        name="api-health",
    ),

    # ========================================================
    # AUTH
    # ========================================================

    path(
        "auth/token/",
        TokenObtainPairView.as_view(),
        name="api-token",
    ),

    path(
        "auth/token/refresh/",
        TokenRefreshView.as_view(),
        name="api-token-refresh",
    ),

    path(
        "auth/token/verify/",
        TokenVerifyView.as_view(),
        name="api-token-verify",
    ),

    path(
        "auth/me/",
        views.current_user,
        name="api-current-user",
    ),

    # ========================================================
    # USERS
    # ========================================================

    path(
        "users/",
        views.users,
        name="api-users",
    ),

    # ========================================================
    # PROJECTS
    # ========================================================

    path(
        "projects/",
        views.projects,
        name="api-projects",
    ),

    path(
        "projects/<int:project_id>/",
        views.project_detail,
        name="api-project-detail",
    ),

    # ========================================================
    # PRODUCTS
    # ========================================================

    path(
        "products/",
        views.products,
        name="api-products",
    ),

    # ========================================================
    # CATEGORIES
    # ========================================================

    path(
        "categories/",
        views.categories,
        name="api-categories",
    ),

    # ========================================================
    # SUPPORT GROUPS
    # ========================================================

    path(
        "support-groups/",
        views.support_groups,
        name="api-support-groups",
    ),

    # ========================================================
    # CMS
    # ========================================================

    path(
        "cms/hero-sections/",
        views.hero_sections,
        name="api-hero-sections",
    ),

    # ========================================================
    # DYNAMIC FORMS
    # ========================================================

    path(
        "forms/",
        views.dynamic_forms,
        name="api-forms",
    ),

    path(
        "forms/<str:form_key>/schema/",
        views.dynamic_form_schema,
        name="api-form-schema",
    ),

    path(
        "forms/<str:form_key>/validate/",
        views.dynamic_form_validate,
        name="api-form-validate",
    ),

    # ========================================================
    # TICKETS
    # ========================================================

    path(
        "tickets/",
        views.tickets,
        name="api-tickets",
    ),

    path(
        "tickets/<int:ticket_id>/",
        views.ticket_detail,
        name="api-ticket-detail",
    ),

    path(
        "tickets/<int:ticket_id>/comments/",
        views.ticket_comments,
        name="api-ticket-comments",
    ),

    path(
        "tickets/<int:ticket_id>/attachments/",
        views.ticket_attachments,
        name="api-ticket-attachments",
    ),

    path(
        "tickets/<int:ticket_id>/events/",
        views.ticket_events,
        name="api-ticket-events",
    ),

    path(
        "tickets/<int:ticket_id>/assign/",
        views.ticket_assign,
        name="api-ticket-assign",
    ),

    path(
        "tickets/<int:ticket_id>/status/",
        views.ticket_status,
        name="api-ticket-status",
    ),

    # ========================================================
    # NOTIFICATIONS
    # ========================================================

    path(
        "notifications/",
        views.notifications,
        name="api-notifications",
    ),

    path(
        "notifications/<int:notification_id>/read/",
        views.notification_read,
        name="api-notification-read",
    ),

    path(
        "notifications/read-all/",
        views.notifications_read_all,
        name="api-notifications-read-all",
    ),

    # ========================================================
    # SLA
    # ========================================================

    path(
        "sla-policies/",
        views.sla_policies,
        name="api-sla-policies",
    ),

    # ========================================================
    # DASHBOARD
    # ========================================================

    path(
        "dashboard/",
        views.dashboard,
        name="api-dashboard",
    ),

    # ========================================================
    # OPENAPI / SWAGGER
    # ========================================================

    path(
        "schema/",
        SpectacularAPIView.as_view(),
        name="api-schema",
    ),

    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="api-schema"
        ),
        name="swagger-ui",
    ),

    path(
        "redoc/",
        SpectacularRedocView.as_view(
            url_name="api-schema"
        ),
        name="redoc",
    ),
]