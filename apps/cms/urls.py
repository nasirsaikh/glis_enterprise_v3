from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("theme.css", views.theme_css, name="theme_css"),
    path("preview/page/<int:pk>/", views.page_preview, name="page_preview"),
    path("pages/<slug:slug>/", views.page_detail, name="page"),
]
