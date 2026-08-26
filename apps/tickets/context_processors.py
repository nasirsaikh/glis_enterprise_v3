from django.db import OperationalError, ProgrammingError
from .models import Notification


def notification_context(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0, "header_notifications": []}
    try:
        queryset = Notification.objects.filter(user=request.user)
        return {"unread_notification_count": queryset.filter(read_at__isnull=True).count(), "header_notifications": queryset[:6]}
    except (OperationalError, ProgrammingError):
        return {"unread_notification_count": 0, "header_notifications": []}
