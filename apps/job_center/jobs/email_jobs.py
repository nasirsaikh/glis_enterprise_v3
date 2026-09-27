import os
from email.mime.image import MIMEImage

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.job_center.registry import register_job
from apps.tickets.models import Ticket, TicketComment


User = get_user_model()

LOGO_CID = "glis-logo"
LOGO_HEIGHT = 46  # px, must match the template


# Colour + label per notification kind (anything else falls back to "info").
KIND_STYLES = {
    "info":       {"kind_label": "Update",      "kind_color": "#1D9E75", "kind_bg": "#E6F5F0"},
    "assignment": {"kind_label": "Assigned",    "kind_color": "#1D9E75", "kind_bg": "#E6F5F0"},
    "success":    {"kind_label": "Resolved",    "kind_color": "#1D9E75", "kind_bg": "#E6F5F0"},
    "approval":   {"kind_label": "Approval",    "kind_color": "#146E52", "kind_bg": "#E3F1EC"},
    "warning":    {"kind_label": "Attention",   "kind_color": "#D4537E", "kind_bg": "#FCEBF0"},
    "sla":        {"kind_label": "SLA alert",   "kind_color": "#D4537E", "kind_bg": "#FCEBF0"},
    "escalation": {"kind_label": "Escalated",   "kind_color": "#D4537E", "kind_bg": "#FCEBF0"},
    "danger":     {"kind_label": "Urgent",      "kind_color": "#D4537E", "kind_bg": "#FCEBF0"},
}


def _logo_path():
    default = os.path.join(settings.MEDIA_ROOT, "branding", "logo-18-7-2023-10-01-36.png")
    return getattr(settings, "EMAIL_LOGO_PATH", default)


def _load_logo():
    """Read the logo once per job run. Returns (bytes, width_px) or (None, None)."""
    path = _logo_path()
    if not path or not os.path.exists(path):
        return None, None
    with open(path, "rb") as fh:
        data = fh.read()
    width = None
    try:
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
            width = round(w * LOGO_HEIGHT / h)
    except Exception:
        pass
    return data, width


def _absolute_url(link):
    """Turn '/portal/tickets/GLIS-2026-00029/' into a full clickable URL."""
    if not link or link.startswith(("http://", "https://")):
        return link
    base = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/{link.lstrip('/')}"


def _display(obj, field):
    if obj is None:
        return ""
    getter = getattr(obj, f"get_{field}_display", None)
    if callable(getter):
        return getter()
    value = getattr(obj, field, "")
    return "" if value is None else str(value)


def _ticket_context(ticket_id):
    if not ticket_id:
        return {}
    ticket = Ticket.objects.filter(pk=ticket_id).first()
    if ticket is None:
        return {}
    requester = getattr(ticket, "created_by", None) or getattr(ticket, "requester", None)
    priority = _display(ticket, "priority")
    return {
        "ticket": ticket,
        "ticket_ref": (getattr(ticket, "number", None) or getattr(ticket, "reference", None)
                       or getattr(ticket, "code", None) or f"#{ticket.pk}"),
        "ticket_subject": getattr(ticket, "subject", None) or getattr(ticket, "title", ""),
        "ticket_priority": priority,
        "priority_high": priority.lower() in {"high", "urgent", "critical"},
        "ticket_status": _display(ticket, "status"),
        "ticket_created": getattr(ticket, "created_at", None),
        "requester_name": (requester.get_full_name() or requester.get_username()) if requester else "",
    }


@register_job("email.ticket_notification")
def send_ticket_notification(recipient_ids, title, body="", ticket_id=None, kind="info", link=""):
    users = User.objects.filter(pk__in=recipient_ids, is_active=True).exclude(email="")
    users = [u for u in users if getattr(u, "profile", None) is None or u.profile.email_notifications]
    if not users:
        return {"success": True, "sent": 0}

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@glis.local")
    logo_bytes, logo_width = _load_logo()

    base_context = {
        "title": title,
        "body": body,
        "kind": kind,
        "link": _absolute_url(link),
        "logo_cid": LOGO_CID if logo_bytes else "",
        "logo_width": logo_width,
        **KIND_STYLES.get(kind, KIND_STYLES["info"]),
        **_ticket_context(ticket_id),
    }

    sent, emails = 0, []
    for user in users:
        context = {**base_context, "recipient_name": user.get_full_name() or user.get_username()}
        text_body = render_to_string("emails/ticket_notification.txt", context)
        html_body = render_to_string("emails/ticket_notification.html", context)

        msg = EmailMultiAlternatives(title, text_body, from_email, [user.email])
        msg.attach_alternative(html_body, "text/html")

        if logo_bytes:
            # Embed the logo inside the email so it shows without a public URL.
            msg.mixed_subtype = "related"
            image = MIMEImage(logo_bytes, _subtype="png")
            image.add_header("Content-ID", f"<{LOGO_CID}>")
            image.add_header("Content-Disposition", "inline", filename="glis-logo.png")
            msg.attach(image)

        sent += msg.send(fail_silently=False)
        emails.append(user.email)

    return {"success": True, "sent": sent, "recipients": emails, "ticket_id": ticket_id, "kind": kind}
