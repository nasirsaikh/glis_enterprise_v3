from django.urls import path

from . import views

app_name = "tpa"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("guide/", views.user_guide, name="user_guide"),

    path("policy-enrollment/", views.policy_enrollment_list, name="policy_enrollment_list"),
    path("policy-enrollment/new/", views.policy_enrollment_create, name="policy_enrollment_create"),

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
        "transactions/<str:reference>/plans/add/",
        views.policy_plan_add,
        name="policy_plan_add",
    ),
    path(
        "transactions/<str:reference>/sources/upload/",
        views.transaction_upload_sources,
        name="transaction_upload_sources",
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
        "transactions/<str:reference>/members/<int:action_id>/edit/",
        views.transaction_edit_member,
        name="transaction_edit_member",
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
        "transactions/<str:reference>/tpa/start/",
        views.transaction_tpa_start,
        name="transaction_tpa_start",
    ),
    path(
        "transactions/<str:reference>/tpa/items/<int:action_id>/",
        views.transaction_tpa_action,
        name="transaction_tpa_action",
    ),
    path(
        "transactions/<str:reference>/tpa/query/",
        views.transaction_raise_query,
        name="transaction_raise_query",
    ),
    path(
        "transactions/<str:reference>/tpa/query/<int:query_id>/message/",
        views.transaction_query_message,
        name="transaction_query_message",
    ),
    path(
        "transactions/<str:reference>/tpa/query/<int:query_id>/resolve/",
        views.transaction_resolve_query,
        name="transaction_resolve_query",
    ),
    path(
        "transactions/<str:reference>/tpa/complete/",
        views.transaction_tpa_complete,
        name="transaction_tpa_complete",
    ),

    # Legacy/direct processing endpoint retained for backward compatibility.
    path(
        "transactions/<str:reference>/process/",
        views.transaction_process,
        name="transaction_process",
    ),
]
