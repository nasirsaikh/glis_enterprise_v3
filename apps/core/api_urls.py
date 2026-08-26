from django.urls import path
from . import api_views

urlpatterns = [
    path("tickets/", api_views.tickets_api, name="tickets"),
    path("tickets/<str:reference>/", api_views.ticket_api, name="ticket"),
    path("tickets/<str:reference>/comments/", api_views.comments_api, name="ticket_comments"),
    path("forms/<slug:form_key>/schema/", api_views.form_schema_api, name="form_schema"),
    path("forms/<slug:form_key>/validate/", api_views.form_validate_api, name="form_validate"),
    path("ai/tickets/analyze/", api_views.ai_analyze_api, name="ai_analyze"),
    path("cms/site-settings/", api_views.cms_settings_api, name="cms_settings"),
]
