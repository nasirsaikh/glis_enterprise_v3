from django.urls import path
from . import views
from . import document_views

urlpatterns = [
    path("", views.article_list, name="list"),
    path("<slug:slug>/", views.article_detail, name="detail"),
    path("<slug:slug>/feedback/", views.article_feedback, name="feedback"),
    path("<slug:slug>/documents/", document_views.article_documents, name="documents"),
    path("<slug:slug>/documents/upload/", document_views.article_document_upload, name="document_upload"),
]
