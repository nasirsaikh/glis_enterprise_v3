from django.urls import path

from . import document_views as views

app_name = "documents"

urlpatterns = [
    path("", views.document_center, name="center"),
    path("upload/", views.document_upload, name="upload"),
    path("<int:document_id>/download/", views.mayan_document_download, name="download"),
    path("<int:document_id>/open/", views.mayan_document_open, name="open"),
    path("mayan/", views.mayan_admin, name="mayan_admin"),
]
