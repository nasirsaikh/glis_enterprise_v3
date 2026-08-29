from django.urls import path
from . import views
from . import document_views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tickets/", views.ticket_list, name="ticket_list"),
    path("tickets/export.csv", views.export_tickets, name="export_tickets"),
    path("tickets/create/<int:step>/", views.create_ticket, name="create_ticket"),
    path("tickets/<str:reference>/", views.ticket_detail, name="ticket_detail"),
    path("tickets/<str:reference>/edit/", views.edit_ticket, name="edit_ticket"),
    path("tickets/<str:reference>/assign/", views.assign_ticket, name="assign_ticket"),
    path("tickets/<str:reference>/unassign/", views.unassign_ticket, name="unassign_ticket"),
    path("tickets/<str:reference>/take-over/", views.take_over_ticket, name="take_over_ticket"),
    path("tickets/<str:reference>/share/", views.share_ticket, name="share_ticket"),
    path("tickets/<str:reference>/approvals/<int:approval_id>/decide/", views.decide_ticket_approval, name="decide_ticket_approval"),
    path("tickets/<str:reference>/attachments/upload/", views.upload_attachments, name="upload_attachments"),
    path("tickets/<str:reference>/documents/", document_views.ticket_documents, name="ticket_documents"),
    path("tickets/<str:reference>/documents/upload/", document_views.ticket_document_upload, name="ticket_document_upload"),
    path("tickets/<str:reference>/documents/<int:document_id>/download/", document_views.ticket_document_download, name="ticket_document_download"),
    path("tickets/<str:reference>/comments/", views.add_comment, name="add_comment"),
    path("attachments/<int:pk>/download/", views.download_attachment, name="download_attachment"),
    path("lookups/products/", views.product_options, name="product_options"),
    path("lookups/categories/", views.category_options, name="category_options"),
    path("search/", views.global_search, name="global_search"),
    path("shared/<uuid:token>/", views.shared_ticket, name="shared_ticket"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/feed/", views.notification_feed, name="notification_feed"),
    path("notifications/read/", views.mark_notifications_read, name="mark_notifications_read"),
]
