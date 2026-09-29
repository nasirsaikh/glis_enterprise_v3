from django.urls import path

from . import views

app_name = "tpa"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("guide/", views.user_guide, name="user_guide"),
    path("inbound-emails/", views.inbound_email_list, name="inbound_email_list"),
    path("inbound-emails/new/", views.inbound_email_create, name="inbound_email_create"),
    path(
        "inbound-emails/<int:email_id>/",
        views.inbound_email_detail,
        name="inbound_email_detail",
    ),
    path(
        "inbound-emails/<int:email_id>/process/",
        views.inbound_email_process,
        name="inbound_email_process",
    ),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/new/", views.transaction_create, name="transaction_create"),
    path(
        "transactions/<str:reference>/",
        views.transaction_detail,
        name="transaction_detail",
    ),
    path(
        "transactions/<str:reference>/sample/<str:kind>/<str:file_format>/",
        views.transaction_sample_file,
        name="transaction_sample_file",
    ),
    path(
        "transactions/<str:reference>/members/add/",
        views.transaction_add_member,
        name="transaction_add_member",
    ),
    path(
        "transactions/<str:reference>/members/upload/",
        views.transaction_upload_members,
        name="transaction_upload_members",
    ),
    path(
        "transactions/<str:reference>/members/<int:action_id>/remove/",
        views.transaction_remove_member,
        name="transaction_remove_member",
    ),
    path(
        "transactions/<str:reference>/submit/",
        views.transaction_submit,
        name="transaction_submit",
    ),
    path(
        "transactions/<str:reference>/validate/",
        views.transaction_validate,
        name="transaction_validate",
    ),
    path(
        "transactions/<str:reference>/approve/",
        views.transaction_approve,
        name="transaction_approve",
    ),
    path(
        "transactions/<str:reference>/process/",
        views.transaction_process,
        name="transaction_process",
    ),
]
