import imaplib
import os
from email import policy as email_policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from ..models import InboundEmail, InboundEmailAttachment
from .ai_intake import process_inbound_email


def _setting(name, default=""):
    value = getattr(settings, name, None)
    return value if value not in (None, "") else os.getenv(name, default)


def _decode(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _addresses(value):
    return [address for _, address in getaddresses([value or ""]) if address]


def _body_text(message):
    if message.is_multipart():
        parts = []
        for part in message.walk():
            disposition = (part.get_content_disposition() or "").lower()
            content_type = part.get_content_type()
            if disposition == "attachment":
                continue
            if content_type == "text/plain":
                try:
                    parts.append(part.get_content())
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        if parts:
            return "\n\n".join(value.strip() for value in parts if value and value.strip())
        for part in message.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_content()
                except Exception:
                    html = ""
                if html:
                    try:
                        from django.utils.html import strip_tags
                        return strip_tags(html)
                    except Exception:
                        return html
        return ""

    try:
        return message.get_content()
    except Exception:
        payload = message.get_payload(decode=True) or b""
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace")


def _attachments(message):
    for part in message.iter_attachments():
        filename = _decode(part.get_filename()) or "attachment"
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        yield filename, part.get_content_type() or "application/octet-stream", payload


def poll_inbound_mailbox(*, actor, limit=50, process_ai=True):
    host = _setting("TPA_IMAP_HOST")
    username = _setting("TPA_IMAP_USERNAME")
    password = _setting("TPA_IMAP_PASSWORD")
    folder = _setting("TPA_IMAP_FOLDER", "INBOX")
    port = int(_setting("TPA_IMAP_PORT", "993"))
    use_ssl = str(_setting("TPA_IMAP_USE_SSL", "1")).lower() not in {"0", "false", "no"}

    if not host or not username or not password:
        raise RuntimeError(
            "Configure TPA_IMAP_HOST, TPA_IMAP_USERNAME and TPA_IMAP_PASSWORD before polling inbound email."
        )

    client_cls = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
    client = client_cls(host, port)
    created_count = 0
    processed_count = 0
    review_count = 0
    skipped_count = 0

    try:
        client.login(username, password)
        status, _ = client.select(folder)
        if status != "OK":
            raise RuntimeError(f"Could not open IMAP folder {folder!r}.")

        status, data = client.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("IMAP search for unread messages failed.")

        uids = (data[0] or b"").split()
        if limit:
            uids = uids[: int(limit)]

        for uid in uids:
            status, message_data = client.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not message_data:
                continue

            raw = None
            for item in message_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw = item[1]
                    break
            if not raw:
                continue

            message = BytesParser(policy=email_policy.default).parsebytes(raw)
            message_id = (message.get("Message-ID") or "").strip()
            provider_message_id = message_id or f"imap:{folder}:{uid.decode()}"

            existing = InboundEmail.objects.filter(
                provider="imap",
                provider_message_id=provider_message_id,
            ).first()
            if existing:
                skipped_count += 1
                client.uid("store", uid, "+FLAGS", "(\\Seen)")
                continue

            senders = _addresses(message.get("From"))
            recipients = _addresses(message.get("To"))
            received = None
            try:
                received = parsedate_to_datetime(message.get("Date")) if message.get("Date") else None
                if received and timezone.is_naive(received):
                    received = timezone.make_aware(received)
            except Exception:
                received = None

            files = list(_attachments(message))
            email = InboundEmail.objects.create(
                provider="imap",
                provider_message_id=provider_message_id,
                created_by=actor,
                sender=(senders[0] if senders else username),
                recipient=(recipients[0] if recipients else username),
                subject=_decode(message.get("Subject")),
                received_at=received or timezone.now(),
                body_text=_body_text(message),
                attachment_metadata=[
                    {
                        "name": name,
                        "content_type": content_type,
                        "size": len(payload),
                    }
                    for name, content_type, payload in files
                ],
                processing_hints={},
            )
            created_count += 1

            import hashlib
            for name, content_type, payload in files:
                InboundEmailAttachment.objects.create(
                    inbound_email=email,
                    file=ContentFile(payload, name=name),
                    original_name=name,
                    content_type=content_type,
                    size=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                )

            if process_ai:
                try:
                    process_inbound_email(email, actor)
                    email.refresh_from_db(fields=["processing_state"])
                    if email.processing_state == InboundEmail.State.PROCESSED:
                        processed_count += 1
                    else:
                        review_count += 1
                except Exception:
                    review_count += 1

            client.uid("store", uid, "+FLAGS", "(\\Seen)")

    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass

    return {
        "created": created_count,
        "processed": processed_count,
        "review": review_count,
        "skipped": skipped_count,
    }
