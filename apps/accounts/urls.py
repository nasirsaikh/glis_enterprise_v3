from django.urls import path
from . import views

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("profile/password/", views.change_password, name="change_password"),
    path("profile/sidebar/", views.sidebar_preference, name="sidebar_preference"),
]
