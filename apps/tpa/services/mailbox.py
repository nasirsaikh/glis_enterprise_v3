import base64
import hashlib
import imaplib
import json
import os
import time
from datetime import datetime
from email import policy as email_policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from urllib.parse import quote

import bleach
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.html import strip_tags

from ..models import InboundEmail, InboundEmailAttachment, TPAMailboxSyncState
from .ai_intake import process_inbound_email


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_PROVIDER = "office365_graph"


def _setting(name, default=""):
    value = getattr(settings, name, None)
    return value if value not in (None, "") else os.getenv(name, default)


def _bool_setting(name, default=True):
    value = str(_setting(name, "1" if default else "0")).strip().lower()
    return value not in {"0", "false", "no", "off", ""}


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
                    parts.append(
                        payload.decode(
                            part.get_content_charset() or "utf-8",
                            errors="replace",
                        )
                    )
        if parts:
            return "\n\n".join(
                value.strip() for value in parts if value and value.strip()
            )
        for part in message.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_content()
                except Exception:
                    html = ""
                if html:
                    return strip_tags(html)
        return ""

    try:
        return message.get_content()
    except Exception:
        payload = message.get_payload(decode=True) or b""
        return payload.decode(
            message.get_content_charset() or "utf-8",
            errors="replace",
        )


def _attachments(message):
    for part in message.iter_attachments():
        filename = _decode(part.get_filename()) or "attachment"
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        yield filename, part.get_content_type() or "application/octet-stream", payload


def _sanitize_html(value):
    return bleach.clean(
        value or "",
        tags=[
            "p", "br", "strong", "b", "em", "i", "u", "ol", "ul", "li",
            "blockquote", "a", "table", "thead", "tbody", "tr", "th", "td",
            "span", "div",
        ],
        attributes={"a": ["href", "title"], "td": ["colspan", "rowspan"], "th": ["colspan", "rowspan"]},
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def _graph_config():
    return {
        "tenant_id": _setting("TPA_O365_TENANT_ID"),
        "client_id": _setting("TPA_O365_CLIENT_ID"),
        "client_secret": _setting("TPA_O365_CLIENT_SECRET"),
        "mailbox": _setting("TPA_O365_MAILBOX"),
        "folder": _setting("TPA_O365_FOLDER", "Inbox"),
        "received_after": _setting("TPA_O365_RECEIVED_AFTER"),
        "enabled": _bool_setting("TPA_MAIL_ENABLED", True),
        "process_ai": _bool_setting("TPA_MAIL_AUTO_PROCESS_AI", True),
        "max_messages": int(_setting("TPA_MAIL_MAX_MESSAGES_PER_RUN", "50") or 50),
        "timeout": int(_setting("TPA_O365_TIMEOUT_SECONDS", "60") or 60),
    }


def _graph_token(config):
    missing = [
        key
        for key in ("tenant_id", "client_id", "client_secret", "mailbox")
        if not config.get(key)
    ]
    if missing:
        raise RuntimeError(
            "Office365 Graph mailbox configuration is incomplete: "
            + ", ".join(missing)
        )
    response = requests.post(
        f"https://login.microsoftonline.com/{quote(config['tenant_id'])}/oauth2/v2.0/token",
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "scope": GRAPH_SCOPE,
            "grant_type": "client_credentials",
        },
        timeout=config["timeout"],
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Microsoft identity platform did not return an access token.")
    return token


def _graph_get(url, token, *, timeout=60, max_page_size=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if max_page_size:
        headers["Prefer"] = f"odata.maxpagesize={max_page_size}"

    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(max(float(retry_after or attempt), 0.1), 10.0)
                    except (TypeError, ValueError):
                        delay = float(attempt)
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= 3:
                raise
            time.sleep(min(float(attempt), 3.0))
    raise last_error or RuntimeError("Microsoft Graph request failed.")


def _graph_email_address(value):
    address = ((value or {}).get("emailAddress") or {})
    return (address.get("name") or "").strip(), (address.get("address") or "").strip()


def _graph_recipient_addresses(values):
    result = []
    for item in values or []:
        name, address = _graph_email_address(item)
        if address:
            result.append({"name": name, "address": address})
    return result


def _graph_received(value):
    if not value:
        return timezone.now()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _graph_attachment_payload(config, token, message_id):
    mailbox = quote(config["mailbox"], safe="@.")
    url = f"{GRAPH_BASE}/users/{mailbox}/messages/{quote(message_id, safe='')}/attachments"
    payload = _graph_get(url, token, timeout=config["timeout"])
    return payload.get("value") or []


def _graph_attachment_bytes(config, token, message_id, attachment):
    encoded = attachment.get("contentBytes")
    if encoded:
        return base64.b64decode(encoded)
    attachment_id = attachment.get("id")
    if not attachment_id:
        return b""
    mailbox = quote(config["mailbox"], safe="@.")
    url = (
        f"{GRAPH_BASE}/users/{mailbox}/messages/{quote(message_id, safe='')}"
        f"/attachments/{quote(attachment_id, safe='')}"
    )
    detail = _graph_get(url, token, timeout=config["timeout"])
    encoded = detail.get("contentBytes")
    return base64.b64decode(encoded) if encoded else b""


def _initial_delta_url(config):
    mailbox = quote(config["mailbox"], safe="@.")
    folder = quote(config["folder"], safe="")
    select = (
        "id,internetMessageId,conversationId,subject,receivedDateTime,"
        "from,toRecipients,ccRecipients,body,bodyPreview,hasAttachments"
    )
    return (
        f"{GRAPH_BASE}/users/{mailbox}/mailFolders/{folder}/messages/delta"
        f"?changeType=created&$select={select}"
    )


def _store_graph_message(message, config, token, actor):
    graph_id = str(message.get("id") or "").strip()
    if not graph_id:
        return None, False

    mailbox = config["mailbox"].lower()
    provider_message_id = f"{mailbox}:{graph_id}"
    internet_message_id = str(message.get("internetMessageId") or "").strip()

    existing = InboundEmail.objects.filter(
        provider=GRAPH_PROVIDER,
        provider_message_id=provider_message_id,
    ).first()
    if not existing and internet_message_id:
        existing = InboundEmail.objects.filter(
            provider=GRAPH_PROVIDER,
            mailbox__iexact=mailbox,
            internet_message_id=internet_message_id,
        ).first()
    if existing:
        return existing, False

    sender_name, sender_address = _graph_email_address(message.get("from"))
    to_addresses = _graph_recipient_addresses(message.get("toRecipients"))
    cc_addresses = _graph_recipient_addresses(message.get("ccRecipients"))
    body = message.get("body") or {}
    body_content = body.get("content") or ""
    body_type = str(body.get("contentType") or "").lower()
    body_html = _sanitize_html(body_content) if body_type == "html" else ""
    body_text = strip_tags(body_html) if body_html else body_content

    received_at = _graph_received(message.get("receivedDateTime"))
    received_after = config.get("received_after")
    if received_after:
        try:
            threshold = datetime.fromisoformat(received_after.replace("Z", "+00:00"))
            if timezone.is_naive(threshold):
                threshold = timezone.make_aware(threshold)
            if received_at < threshold:
                return None, False
        except ValueError:
            pass

    attachment_rows = []
    if message.get("hasAttachments"):
        attachment_rows = _graph_attachment_payload(config, token, graph_id)

    email = InboundEmail.objects.create(
        provider=GRAPH_PROVIDER,
        provider_message_id=provider_message_id,
        graph_message_id=graph_id,
        internet_message_id=internet_message_id,
        conversation_id=str(message.get("conversationId") or ""),
        mailbox=mailbox,
        sender_name=sender_name,
        sender=sender_address or "unknown@example.invalid",
        recipient=(to_addresses[0]["address"] if to_addresses else mailbox),
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        subject=str(message.get("subject") or ""),
        received_at=received_at,
        body_text=body_text,
        body_html=body_html,
        attachment_metadata=[],
        processing_hints={},
        processing_stage="RECEIVED",
        created_by=actor,
    )

    metadata = []
    digest = hashlib.sha256()
    digest.update(graph_id.encode("utf-8"))
    digest.update(internet_message_id.encode("utf-8"))
    digest.update(body_text.encode("utf-8", errors="ignore"))

    for attachment in attachment_rows:
        name = str(attachment.get("name") or "attachment")
        content_type = str(attachment.get("contentType") or "application/octet-stream")
        odata_type = str(attachment.get("@odata.type") or "")
        if "fileAttachment" not in odata_type:
            metadata.append(
                {
                    "name": name,
                    "content_type": content_type,
                    "size": int(attachment.get("size") or 0),
                    "graph_attachment_id": attachment.get("id"),
                    "unsupported_type": odata_type,
                }
            )
            continue
        raw = _graph_attachment_bytes(config, token, graph_id, attachment)
        if not raw:
            continue
        sha256 = hashlib.sha256(raw).hexdigest()
        digest.update(sha256.encode("ascii"))
        metadata.append(
            {
                "name": name,
                "content_type": content_type,
                "size": len(raw),
                "sha256": sha256,
                "graph_attachment_id": attachment.get("id"),
            }
        )
        if not email.attachments.filter(sha256=sha256).exists():
            InboundEmailAttachment.objects.create(
                inbound_email=email,
                file=ContentFile(raw, name=name),
                original_name=name,
                content_type=content_type,
                size=len(raw),
                sha256=sha256,
            )

    email.attachment_metadata = metadata
    email.source_hash = digest.hexdigest()
    email.save(update_fields=["attachment_metadata", "source_hash", "updated_at"])
    return email, True


def poll_office365_graph(*, actor, limit=None, process_ai=None):
    config = _graph_config()
    if not config["enabled"]:
        return {
            "created": 0,
            "processed": 0,
            "review": 0,
            "ignored": 0,
            "failed": 0,
            "skipped": 0,
            "disabled": True,
        }

    limit = max(1, int(limit or config["max_messages"] or 50))
    process_ai = config["process_ai"] if process_ai is None else bool(process_ai)
    state, _ = TPAMailboxSyncState.objects.get_or_create(
        provider=GRAPH_PROVIDER,
        mailbox=config["mailbox"].lower(),
        folder=config["folder"],
    )
    state.last_attempted_at = timezone.now()
    state.scheduler_enabled = True
    state.save(update_fields=["last_attempted_at", "scheduler_enabled", "updated_at"])

    stats = {
        "created": 0,
        "processed": 0,
        "review": 0,
        "ignored": 0,
        "failed": 0,
        "skipped": 0,
    }

    try:
        token = _graph_token(config)
        url = state.delta_link or _initial_delta_url(config)
        retrieved = 0
        latest_state_link = state.delta_link

        while url and retrieved < limit:
            page_size = min(limit - retrieved, 50)
            page = _graph_get(
                url,
                token,
                timeout=config["timeout"],
                max_page_size=max(page_size, 1),
            )
            values = page.get("value") or []
            for message in values:
                if retrieved >= limit:
                    break
                if message.get("@removed"):
                    continue
                retrieved += 1
                email, created = _store_graph_message(
                    message,
                    config,
                    token,
                    actor,
                )
                if not email:
                    continue
                if not created:
                    stats["skipped"] += 1
                    continue
                stats["created"] += 1

                if process_ai:
                    try:
                        process_inbound_email(email, actor)
                    except Exception:
                        # process_inbound_email persists a review-safe state/error.
                        pass
                    email.refresh_from_db(fields=["processing_state"])
                    if email.processing_state == InboundEmail.State.PROCESSED:
                        stats["processed"] += 1
                    elif email.processing_state == InboundEmail.State.IGNORED:
                        stats["ignored"] += 1
                    elif email.processing_state == InboundEmail.State.FAILED:
                        stats["failed"] += 1
                    else:
                        stats["review"] += 1

            latest_state_link = (
                page.get("@odata.nextLink")
                or page.get("@odata.deltaLink")
                or latest_state_link
            )
            if retrieved >= limit:
                url = None
            else:
                url = page.get("@odata.nextLink")
                if not url and page.get("@odata.deltaLink"):
                    latest_state_link = page["@odata.deltaLink"]

        state.delta_link = latest_state_link or state.delta_link
        state.last_successful_at = timezone.now()
        state.last_error = ""
        state.messages_processed += stats["processed"]
        state.messages_review += stats["review"]
        state.messages_ignored += stats["ignored"]
        state.messages_failed += stats["failed"]
        state.save(
            update_fields=[
                "delta_link",
                "last_successful_at",
                "last_error",
                "messages_processed",
                "messages_review",
                "messages_ignored",
                "messages_failed",
                "updated_at",
            ]
        )
        return stats
    except Exception as exc:
        state.last_error = str(exc)
        state.messages_failed += 1
        state.save(
            update_fields=[
                "last_error",
                "messages_failed",
                "updated_at",
            ]
        )
        raise


def poll_imap_mailbox(*, actor, limit=50, process_ai=True):
    host = _setting("TPA_IMAP_HOST")
    username = _setting("TPA_IMAP_USERNAME")
    password = _setting("TPA_IMAP_PASSWORD")
    folder = _setting("TPA_IMAP_FOLDER", "INBOX")
    port = int(_setting("TPA_IMAP_PORT", "993"))
    use_ssl = _bool_setting("TPA_IMAP_USE_SSL", True)

    if not host or not username or not password:
        raise RuntimeError(
            "Configure TPA_IMAP_HOST, TPA_IMAP_USERNAME and TPA_IMAP_PASSWORD "
            "before using the legacy IMAP fallback."
        )

    client_cls = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
    client = client_cls(host, port)
    stats = {
        "created": 0,
        "processed": 0,
        "review": 0,
        "ignored": 0,
        "failed": 0,
        "skipped": 0,
    }
    try:
        client.login(username, password)
        status, _ = client.select(folder)
        if status != "OK":
            raise RuntimeError(f"Could not open IMAP folder {folder!r}.")
        status, data = client.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("IMAP search for unread messages failed.")
        uids = (data[0] or b"").split()[: max(int(limit or 50), 1)]

        for uid in uids:
            status, message_data = client.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not message_data:
                continue
            raw = next(
                (
                    item[1]
                    for item in message_data
                    if isinstance(item, tuple) and len(item) >= 2
                ),
                None,
            )
            if not raw:
                continue
            message = BytesParser(policy=email_policy.default).parsebytes(raw)
            message_id = (message.get("Message-ID") or "").strip()
            provider_message_id = message_id or f"imap:{folder}:{uid.decode()}"
            if InboundEmail.objects.filter(
                provider="imap",
                provider_message_id=provider_message_id,
            ).exists():
                stats["skipped"] += 1
                client.uid("store", uid, "+FLAGS", "(\\Seen)")
                continue

            senders = _addresses(message.get("From"))
            recipients = _addresses(message.get("To"))
            cc = _addresses(message.get("Cc"))
            try:
                received = (
                    parsedate_to_datetime(message.get("Date"))
                    if message.get("Date")
                    else None
                )
                if received and timezone.is_naive(received):
                    received = timezone.make_aware(received)
            except Exception:
                received = None

            files = list(_attachments(message))
            email = InboundEmail.objects.create(
                provider="imap",
                provider_message_id=provider_message_id,
                internet_message_id=message_id,
                mailbox=username,
                created_by=actor,
                sender=(senders[0] if senders else username),
                recipient=(recipients[0] if recipients else username),
                to_addresses=[{"address": value} for value in recipients],
                cc_addresses=[{"address": value} for value in cc],
                subject=_decode(message.get("Subject")),
                received_at=received or timezone.now(),
                body_text=_body_text(message),
                attachment_metadata=[],
                processing_hints={},
                processing_stage="RECEIVED",
            )
            metadata = []
            digest = hashlib.sha256(raw)
            for name, content_type, payload in files:
                sha256 = hashlib.sha256(payload).hexdigest()
                metadata.append(
                    {
                        "name": name,
                        "content_type": content_type,
                        "size": len(payload),
                        "sha256": sha256,
                    }
                )
                InboundEmailAttachment.objects.create(
                    inbound_email=email,
                    file=ContentFile(payload, name=name),
                    original_name=name,
                    content_type=content_type,
                    size=len(payload),
                    sha256=sha256,
                )
            email.attachment_metadata = metadata
            email.source_hash = digest.hexdigest()
            email.save(update_fields=["attachment_metadata", "source_hash", "updated_at"])
            stats["created"] += 1

            if process_ai:
                try:
                    process_inbound_email(email, actor)
                except Exception:
                    pass
                email.refresh_from_db(fields=["processing_state"])
                if email.processing_state == InboundEmail.State.PROCESSED:
                    stats["processed"] += 1
                elif email.processing_state == InboundEmail.State.IGNORED:
                    stats["ignored"] += 1
                else:
                    stats["review"] += 1
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
    return stats


def poll_inbound_mailbox(*, actor, limit=None, process_ai=None):
    provider = str(_setting("TPA_MAIL_PROVIDER", GRAPH_PROVIDER)).strip().lower()
    if provider in {"office365_graph", "graph", "microsoft_graph"}:
        return poll_office365_graph(
            actor=actor,
            limit=limit,
            process_ai=process_ai,
        )
    if provider == "imap":
        return poll_imap_mailbox(
            actor=actor,
            limit=limit or 50,
            process_ai=True if process_ai is None else bool(process_ai),
        )
    raise RuntimeError(f"Unsupported TPA_MAIL_PROVIDER: {provider}")


def mailbox_health():
    provider = str(_setting("TPA_MAIL_PROVIDER", GRAPH_PROVIDER)).strip().lower()
    if provider in {"office365_graph", "graph", "microsoft_graph"}:
        config = _graph_config()
        state = (
            TPAMailboxSyncState.objects.filter(
                provider=GRAPH_PROVIDER,
                mailbox__iexact=config["mailbox"],
                folder=config["folder"],
            )
            .order_by("-updated_at")
            .first()
            if config["mailbox"]
            else None
        )
        configured = all(
            config.get(key)
            for key in ("tenant_id", "client_id", "client_secret", "mailbox")
        )
        try:
            from apps.job_center.models import ScheduledJob
            scheduled_job = ScheduledJob.objects.filter(
                handler="tpa.poll_inbound_mailbox"
            ).order_by("pk").first()
        except Exception:
            scheduled_job = None

        scheduler_enabled = bool(
            config["enabled"]
            and getattr(settings, "JOB_CENTER_ENABLED", True)
            and scheduled_job
            and scheduled_job.enabled
        )
        return {
            "provider": GRAPH_PROVIDER,
            "enabled": config["enabled"],
            "configured": configured,
            "connected": bool(
                configured and state and state.last_successful_at and not state.last_error
            ),
            "mailbox": config["mailbox"],
            "folder": config["folder"],
            "last_attempted_at": getattr(state, "last_attempted_at", None),
            "last_successful_at": getattr(state, "last_successful_at", None),
            "last_error": getattr(state, "last_error", "") if state else "",
            "messages_processed": getattr(state, "messages_processed", 0) if state else 0,
            "messages_review": getattr(state, "messages_review", 0) if state else 0,
            "messages_ignored": getattr(state, "messages_ignored", 0) if state else 0,
            "messages_failed": getattr(state, "messages_failed", 0) if state else 0,
            "scheduler_enabled": scheduler_enabled,
            "scheduler_cron": (
                str(getattr(settings, "TPA_MAIL_SYNC_CRON", "") or "").strip()
                or (getattr(scheduled_job, "cron_expression", "") if scheduled_job else "")
            ),
            "scheduler_last_run_at": getattr(scheduled_job, "last_run_at", None) if scheduled_job else None,
            "scheduler_last_status": getattr(scheduled_job, "last_status", "") if scheduled_job else "",
            "scheduler_next_run_at": getattr(scheduled_job, "next_run_at", None) if scheduled_job else None,
        }

    return {
        "provider": "imap",
        "enabled": _bool_setting("TPA_MAIL_ENABLED", True),
        "configured": bool(_setting("TPA_IMAP_HOST") and _setting("TPA_IMAP_USERNAME")),
        "connected": False,
        "mailbox": _setting("TPA_IMAP_USERNAME"),
        "folder": _setting("TPA_IMAP_FOLDER", "INBOX"),
        "last_attempted_at": None,
        "last_successful_at": None,
        "last_error": "",
        "messages_processed": 0,
        "messages_review": 0,
        "messages_ignored": 0,
        "messages_failed": 0,
        "scheduler_enabled": _bool_setting("TPA_MAIL_ENABLED", True),
    }
