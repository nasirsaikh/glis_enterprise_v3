from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from . import views

urlpatterns = [
    path("health/", views.health, name="api-health"),
    path("auth/token/", TokenObtainPairView.as_view(), name="api-token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="api-token-refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="api-token-verify"),
    path("auth/me/", views.current_user, name="api-current-user"),
    path("users/", views.users, name="api-users"),
    path("projects/", views.projects, name="api-projects"),
    path("projects/<int:project_id>/", views.project_detail, name="api-project-detail"),
    path("products/", views.products, name="api-products"),
    path("categories/", views.categories, name="api-categories"),
    path("support-groups/", views.support_groups, name="api-support-groups"),
    path("cms/hero-sections/", views.hero_sections, name="api-hero-sections"),
    path("forms/", views.dynamic_forms, name="api-forms"),
    path("forms/<str:form_key>/schema/", views.dynamic_form_schema, name="api-form-schema"),
    path("forms/<str:form_key>/validate/", views.dynamic_form_validate, name="api-form-validate"),
    path("tickets/", views.tickets, name="api-tickets"),
    path("tickets/<int:ticket_id>/", views.ticket_detail, name="api-ticket-detail"),
    path("tickets/<int:ticket_id>/comments/", views.ticket_comments, name="api-ticket-comments"),
    path("tickets/<int:ticket_id>/attachments/", views.ticket_attachments, name="api-ticket-attachments"),
    path("tickets/<int:ticket_id>/events/", views.ticket_events, name="api-ticket-events"),
    path("tickets/<int:ticket_id>/assign/", views.ticket_assign, name="api-ticket-assign"),
    path("tickets/<int:ticket_id>/status/", views.ticket_status, name="api-ticket-status"),
    path("notifications/", views.notifications, name="api-notifications"),
    path("notifications/<int:notification_id>/read/", views.notification_read, name="api-notification-read"),
    path("notifications/read-all/", views.notifications_read_all, name="api-notifications-read-all"),
    path("sla-policies/", views.sla_policies, name="api-sla-policies"),
    path("dashboard/", views.dashboard, name="api-dashboard"),
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="api-schema"), name="redoc"),
    path("hero-image/<int:pk>/",views.hero_image,name="hero_image",),
]