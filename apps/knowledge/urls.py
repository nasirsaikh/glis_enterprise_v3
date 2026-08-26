from django.urls import path
from . import views

urlpatterns = [
    path("", views.article_list, name="list"),
    path("<slug:slug>/", views.article_detail, name="detail"),
    path("<slug:slug>/feedback/", views.article_feedback, name="feedback"),
]
