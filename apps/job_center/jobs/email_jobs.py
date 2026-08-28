from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from apps.job_center.registry import register_job
from apps.tickets.models import Ticket, TicketComment


User = get_user_model()

@register_job("email.ticket_notification")
def send_ticket_notification(recipient_ids, title, body="", ticket_id=None, kind="info", link=""):
    users = User.objects.filter(pk__in=recipient_ids, is_active=True).exclude(email="")
    emails = [user.email for user in users if getattr(user, "profile", None) is None or user.profile.email_notifications]
    if not emails: return {"success": True, "sent": 0}
    message = f"{body}\n\n{link}" if link else body
    sent = send_mail(title, message, getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@glis.local"), emails, fail_silently=False)
    return {"success": True, "sent": sent, "recipients": emails, "ticket_id": ticket_id, "kind": kind}