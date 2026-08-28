from django.urls import path

from . import views

app_name = "job_center"

urlpatterns = [
    path("api/dashboard/", views.dashboard_api, name="dashboard_api"),
    path("api/jobs/<int:pk>/run/", views.run_now_api, name="run_now_api"),
]
