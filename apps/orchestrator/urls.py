from django.urls import path
from . import views

urlpatterns = [
    path("", views.console, name="console"),
    path("ask/", views.ask, name="ask"),
    path("sessions/", views.session_list, name="session_list"),
    path("sessions/<uuid:session_id>/", views.session_detail, name="session_detail"),
    path("sessions/<uuid:session_id>/export/", views.export_result, name="export_result"),
    path("queries/<int:query_id>/export/", views.export_query, name="export_query"),
]
